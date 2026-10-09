"""Servicio local real y desechable para demostrar degradación y recuperación."""
import argparse
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    delay_s = 0

    def do_GET(self):
        time.sleep(type(self).delay_s)
        data = b"Servicio de prueba funcionando\n"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Servicio HTTP local para la demostración")
    parser.add_argument("--delay-ms", type=int, default=0, help="Retardo controlado por solicitud (0-5000 ms)")
    args = parser.parse_args()
    if not 0 <= args.delay_ms <= 5000:
        parser.error("--delay-ms debe estar entre 0 y 5000")
    Handler.delay_s = args.delay_ms / 1000
    server = ThreadingHTTPServer(("127.0.0.1", 8766), Handler)
    print(f"Servicio de prueba: http://127.0.0.1:8766 — retardo {args.delay_ms} ms — Ctrl+C para detener", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
