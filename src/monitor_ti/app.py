"""Panel local: python -m monitor_ti. Escucha únicamente en 127.0.0.1."""
import argparse
import json
import logging
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .collector import Collector
from .core import DiskTrend, RuleEngine, Store, load_config

ROOT = Path(__file__).resolve().parent
LOG = logging.getLogger("monitor_ti")


class Application:
    def __init__(self, config, data_dir):
        self.config = config
        data_dir.mkdir(parents=True, exist_ok=True)
        identity_path = data_dir / "device_id.txt"
        if not identity_path.exists():
            identity_path.write_text(str(uuid.uuid4()), encoding="utf-8")
        self.collector = Collector(config, identity_path.read_text(encoding="utf-8").strip())
        self.store = Store(data_dir / "monitor.sqlite3")
        self.engine = RuleEngine(config)
        self.trend = DiskTrend()
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.sample = None
        self.last_read = None
        self.last_error = None

    def collect_forever(self):
        while not self.stop.is_set():
            cycle = time.monotonic()
            try:
                sample = self.collector.read()
                sample["disk_forecast"] = self.trend.update(cycle, sample["disk"].get("free_bytes"))
                with self.lock:
                    changes = self.engine.evaluate(self.engine.observations(sample), cycle, sample["timestamp"])
                    self.store.save(sample, changes, self.config["retention_hours"])
                    self.sample = sample
                    self.last_read = time.monotonic()
                    self.last_error = None
            except Exception:
                LOG.exception("No se pudo completar la lectura")
                with self.lock:
                    self.last_error = "No se completó la última lectura; revisar la consola."
            self.stop.wait(max(0.05, self.config["interval_s"] - (time.monotonic() - cycle)))

    def state(self):
        with self.lock:
            age = None if self.last_read is None else time.monotonic() - self.last_read
            fresh = age is not None and age <= max(15, 3 * self.config["interval_s"]) and self.last_error is None
            active = [dict(i) for i in self.engine.active.values()]
            sample = self.sample
            quality_unknown = any(i["quality"] == "unknown" for i in active)
            mandatory_complete = sample is not None and sample.get("cpu_percent") is not None and sample["ram"].get("percent") is not None and sample["disk"].get("free_bytes") is not None
            if not fresh:
                level = "unknown"
            elif any(i["severity"] == "critical" for i in active):
                level = "critical"
            elif active:
                level = "warning"
            elif not mandatory_complete or quality_unknown:
                level = "unknown"
            else:
                level = "ok"
            return {"sample": sample, "active": active, "incidents": self.store.incidents(),
                    "fresh": fresh, "complete": mandatory_complete, "level": level,
                    "age_seconds": None if age is None else round(age, 1), "error": self.last_error,
                    "config": self.config,
                    "limits": {"scope": "Una computadora local", "temperature_windows": "Requiere un proveedor adicional; esta base sólo usa sensores expuestos por psutil.",
                               "network": "Tráfico observado por interfaz; no es un speedtest.",
                               "effective_action": "Registrar atención no demuestra una solución; comprobar recuperación de la métrica.",
                               "esp32": "Puente serial opcional; hardware no probado en este entorno."}}


def handler_for(app):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            LOG.debug(fmt, *args)

        def respond(self, status, body, mime="application/json; charset=utf-8"):
            if mime.startswith("application/json"):
                body = json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)

        def local_request(self):
            host = self.headers.get("Host", "")
            valid_hosts = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
            if host not in valid_hosts:
                self.respond(403, {"error": "Este panel es local."})
                return False
            origin = self.headers.get("Origin")
            if origin and origin not in {"http://" + h for h in valid_hosts}:
                self.respond(403, {"error": "Origen no permitido."})
                return False
            return True

        def do_GET(self):
            if not self.local_request():
                return
            route = urlparse(self.path).path
            if route == "/":
                self.respond(200, (ROOT / "web" / "index.html").read_bytes(), "text/html; charset=utf-8")
            elif route in ("/api/state", "/health"):
                self.respond(200, app.state())
            elif route == "/api/history":
                self.respond(200, app.store.history())
            elif route == "/api/incidents":
                self.respond(200, app.store.incidents())
            else:
                self.respond(404, {"error": "Ruta no encontrada."})

        def do_POST(self):
            if not self.local_request():
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 16384 or self.headers.get_content_type() != "application/json":
                    raise ValueError("Enviar JSON de hasta 16 KiB.")
                data = json.loads(self.rfile.read(length))
                if not isinstance(data, dict):
                    raise ValueError("Enviar un objeto JSON.")
                parts = urlparse(self.path).path.strip("/").split("/")
                if len(parts) != 4 or parts[:2] != ["api", "incidents"] or parts[3] not in ("ack", "action"):
                    self.respond(404, {"error": "Ruta no encontrada."})
                    return
                action = parts[3] == "action"
                note = data.get("note", "")
                if not isinstance(note, str) or len(note) > 300 or (action and not note.strip()):
                    raise ValueError("Describe la acción en 1–300 caracteres.")
                with app.lock:
                    app.store.mark(parts[2], action, note.strip())
                self.respond(200, {"ok": True})
            except KeyError:
                self.respond(404, {"error": "Incidente no encontrado."})
            except (ValueError, json.JSONDecodeError) as exc:
                self.respond(400, {"error": str(exc)})
    return Handler


def main():
    parser = argparse.ArgumentParser(description="Prototipo de monitoreo preventivo TI")
    parser.add_argument("--config", help="Archivo JSON de configuración")
    parser.add_argument("--data-dir", type=Path, default=Path.cwd() / "data")
    parser.add_argument("--port", type=int, default=8875)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    config = load_config(args.config)
    app = Application(config, args.data_dir)
    worker = threading.Thread(target=app.collect_forever, name="recolector", daemon=True)
    try:
        server = ThreadingHTTPServer(("127.0.0.1", args.port), handler_for(app))
    except OSError as exc:
        app.store.close()
        if getattr(exc, "winerror", None) in (10013, 10048) or getattr(exc, "errno", None) in (13, 48, 98, 10013, 10048):
            parser.error(f"No se pudo usar 127.0.0.1:{args.port}; el puerto está ocupado o reservado. Prueba --port 9876.")
        raise
    server.daemon_threads = True
    worker.start()
    print(f"Monitor TI: http://127.0.0.1:{args.port}", flush=True)
    print("Lecturas de esta computadora; Ctrl+C para detener. ESP32 opcional.", flush=True)
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        print("\nDeteniendo el monitor...", flush=True)
    finally:
        app.stop.set()
        worker.join(timeout=10)
        server.server_close()
        if not worker.is_alive():
            app.collector.close()
            app.store.close()


if __name__ == "__main__":
    main()
