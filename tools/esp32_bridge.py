"""Envía el estado real del agente al ESP32 por puerto serial."""
import argparse
import json
import time
import urllib.request

import serial


def main():
    parser = argparse.ArgumentParser(description="Puente opcional con ESP32")
    parser.add_argument("--port", required=True, help="COM13, COM5 o /dev/ttyUSB0")
    parser.add_argument("--url", default="http://127.0.0.1:8875/api/state")
    args = parser.parse_args()
    sequence = 0
    connection = None
    print("H,<nivel>,<secuencia> sólo con datos recientes. Ctrl+C para detener.")
    try:
        while True:
            try:
                if connection is None:
                    connection = serial.Serial(args.port, 115200, timeout=1, write_timeout=1)
                    time.sleep(2)  # Algunas placas se reinician al abrir el puerto.
                with urllib.request.urlopen(args.url, timeout=2) as response:
                    state = json.load(response)
                if state.get("fresh"):
                    level = {"ok": 0, "warning": 1, "critical": 2, "unknown": 3}[state["level"]]
                    sequence += 1
                    connection.write(f"H,{level},{sequence}\n".encode("ascii"))
                else:
                    print("Agente sin lectura reciente; se deja vencer el latido.")
            except (OSError, ValueError, KeyError, serial.SerialException) as exc:
                print("Sin latido confirmado:", type(exc).__name__)
                if connection is not None:
                    connection.close()
                    connection = None
            time.sleep(3)
    except KeyboardInterrupt:
        pass
    finally:
        if connection is not None:
            connection.close()


if __name__ == "__main__":
    main()
