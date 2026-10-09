"""Prueba integrada: HTTP real, agente, incidente, atención y recuperación."""
import json
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import Mock

from monitor_ti.core import DEFAULTS
from monitor_ti.app import Application, handler_for


class EndToEndTests(unittest.TestCase):
    def test_telegram_incident_dispatch_and_secret_redaction(self):
        with tempfile.TemporaryDirectory() as folder:
            cfg = dict(DEFAULTS, telegram={
                "enabled": True, "bot_token": "private-token", "chat_id": "123"
            })
            app = Application(cfg, Path(folder))
            app.notifier.close()
            app.notifier = Mock()
            try:
                app._notify_changes([("opened", {
                    "title": "CPU alta", "severity": "warning",
                    "recommendation": "Revisar carga",
                })])
                app.notifier.send_alert.assert_called_once()
                self.assertIn("CPU alta", app.notifier.send_alert.call_args.args[0])
                state = app.state()
                self.assertIsInstance(state, dict)
                self.assertFalse(state["config"]["telegram"]["configured"] is False)
                self.assertNotIn("private-token", json.dumps(state))
            finally:
                app.store.close()

    def test_service_failure_attention_and_confirmed_recovery(self):
        class DemoHandler(BaseHTTPRequestHandler):
            healthy = True

            def do_GET(self):
                self.send_response(200 if type(self).healthy else 503)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, *args):
                pass

        with tempfile.TemporaryDirectory() as folder:
            demo = ThreadingHTTPServer(("127.0.0.1", 0), DemoHandler)
            demo_thread = threading.Thread(target=demo.serve_forever, daemon=True)
            demo_thread.start()
            cfg = dict(DEFAULTS, interval_s=1, recovery_s=1, service_every_s=1, service_failures=2,
                       service_url=f"http://127.0.0.1:{demo.server_port}/")
            app = Application(cfg, Path(folder))
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(app))
            server_thread = threading.Thread(target=server.serve_forever, daemon=True)
            worker = threading.Thread(target=app.collect_forever, daemon=True)
            server_thread.start()
            worker.start()
            base = f"http://127.0.0.1:{server.server_port}"

            def request(path, body=None, origin=None):
                headers = {} if body is None else {"Content-Type": "application/json"}
                if origin:
                    headers["Origin"] = origin
                req = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(), headers=headers)
                with urllib.request.urlopen(req, timeout=2) as response:
                    return json.load(response)

            def wait_until(predicate):
                deadline = time.monotonic() + 12
                while time.monotonic() < deadline:
                    state = request("/api/state")
                    if predicate(state):
                        return state
                    time.sleep(0.1)
                self.fail("No se observó la transición esperada.")

            try:
                good = wait_until(lambda s: s["complete"] and s["sample"]["service"]["ok"])
                self.assertTrue(good["fresh"])
                self.assertEqual(good["sample"]["source"], "real/psutil")
                with urllib.request.urlopen(base, timeout=2) as r:
                    self.assertIn("Antes de la llamada".encode(), r.read())
                DemoHandler.healthy = False
                bad = wait_until(lambda s: any(i["rule_key"] == "service" and i["status"] == "open" for i in s["incidents"]))
                incident = next(i for i in bad["incidents"] if i["rule_key"] == "service")
                self.assertGreaterEqual(incident["seconds_to_detection"], 0)
                self.assertEqual(incident["evidence"]["status_code"], 503)
                iid = incident["id"]
                request(f"/api/incidents/{iid}/ack", {})
                request(f"/api/incidents/{iid}/action", {"note": "Restaurar el servicio de prueba"})
                attended = next(i for i in request("/api/incidents") if i["id"] == iid)
                self.assertEqual(attended["status"], "open")
                self.assertIsNotNone(attended["action_ts"])
                self.assertIsNone(attended["recovered_ts"])
                DemoHandler.healthy = True
                restored = wait_until(lambda s: any(i["id"] == iid and i["status"] == "recovered" for i in s["incidents"]))
                matching = [i for i in restored["incidents"] if i["rule_key"] == "service"]
                self.assertEqual(len(matching), 1)
                self.assertIsNotNone(matching[0]["recovered_ts"])
                self.assertGreaterEqual(matching[0]["seconds_to_recovered"], matching[0]["seconds_to_action"])
                self.assertGreater(len(request("/api/history")), 1)
                with self.assertRaises(urllib.error.HTTPError) as blocked:
                    request(f"/api/incidents/{iid}/ack", {}, origin="https://example.com")
                self.assertEqual(blocked.exception.code, 403)
                app.stop.set()
                worker.join(timeout=5)
                with app.lock:
                    app.last_read = time.monotonic() - 30
                stale = request("/api/state")
                self.assertFalse(stale["fresh"])
                self.assertEqual(stale["level"], "unknown")
            finally:
                app.stop.set()
                worker.join(timeout=5)
                server.shutdown()
                demo.shutdown()
                server.server_close()
                demo.server_close()
                server_thread.join(timeout=2)
                demo_thread.join(timeout=2)
                app.store.close()


if __name__ == "__main__":
    unittest.main()
