"""Reglas e historial del prototipo. Sin acciones sobre otros procesos."""
from __future__ import annotations

import json
import math
import sqlite3
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def rate(current, previous, elapsed):
    """Una primera lectura o un contador reiniciado no es una tasa de cero."""
    if current is None or previous is None or elapsed <= 0 or current < previous:
        return None
    return (current - previous) / elapsed


DEFAULTS = {
    "interval_s": 5,
    "persistence_s": 30,
    "recovery_s": 10,
    "cpu_warn_percent": 90,
    "cpu_clear_percent": 80,
    "ram_warn_percent": 90,
    "ram_clear_percent": 80,
    "disk_path": None,
    "disk_warn_free_percent": 10,
    "disk_clear_free_percent": 12,
    "disk_min_free_gib": 5,
    "disk_clear_min_free_gib": 6,
    "disk_hold_s": 20,
    "disk_forecast_warn_hours": 24,
    "expected_processes": [],
    "process_hold_s": 15,
    "network_interface": None,
    "temperature_sensor": None,
    "temperature_provider": "auto",
    "librehardwaremonitor_path": None,
    "temperature_warn_c": None,
    "service_url": None,
    "service_every_s": 15,
    "service_failures": 3,
    "service_latency_warn_ms": None,
    "service_latency_clear_ms": None,
    "service_latency_hold_s": 15,
    "retention_hours": 24,
    "telegram": {"enabled": False, "bot_token": "", "chat_id": ""},
}


def load_config(path=None):
    cfg = dict(DEFAULTS)
    cfg["telegram"] = dict(DEFAULTS["telegram"])
    if path:
        supplied = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        if not isinstance(supplied, dict):
            raise ValueError("La configuración debe ser un objeto JSON.")
        unknown = set(supplied) - set(DEFAULTS)
        if unknown:
            raise ValueError("Opciones desconocidas: " + ", ".join(sorted(unknown)))
        cfg.update({key: value for key, value in supplied.items() if key != "telegram"})
        if "telegram" in supplied:
            telegram = supplied["telegram"]
            if not isinstance(telegram, dict):
                raise ValueError("telegram debe ser un objeto.")
            unknown_telegram = set(telegram) - set(DEFAULTS["telegram"])
            if unknown_telegram:
                raise ValueError("Opciones de Telegram desconocidas: " + ", ".join(sorted(unknown_telegram)))
            cfg["telegram"].update(telegram)
    for key in ("interval_s", "service_every_s", "retention_hours", "service_failures"):
        if isinstance(cfg[key], bool) or not isinstance(cfg[key], (int, float)) or not math.isfinite(cfg[key]) or cfg[key] <= 0:
            raise ValueError(f"{key} debe ser un número positivo.")
    if cfg["interval_s"] < 1 or cfg["service_every_s"] < 1:
        raise ValueError("Los intervalos deben ser de al menos un segundo.")
    for key in ("persistence_s", "recovery_s", "disk_hold_s", "process_hold_s", "disk_min_free_gib", "disk_clear_min_free_gib", "disk_forecast_warn_hours", "service_latency_hold_s"):
        if isinstance(cfg[key], bool) or not isinstance(cfg[key], (int, float)) or not math.isfinite(cfg[key]) or cfg[key] < 0:
            raise ValueError(f"{key} debe ser un número no negativo.")
    for key in ("cpu_warn_percent", "cpu_clear_percent", "ram_warn_percent", "ram_clear_percent", "disk_warn_free_percent", "disk_clear_free_percent"):
        if isinstance(cfg[key], bool) or not isinstance(cfg[key], (int, float)) or not math.isfinite(cfg[key]) or not 0 <= cfg[key] <= 100:
            raise ValueError(f"{key} debe estar entre 0 y 100.")
    if cfg["cpu_clear_percent"] >= cfg["cpu_warn_percent"] or cfg["ram_clear_percent"] >= cfg["ram_warn_percent"]:
        raise ValueError("CPU/RAM: el umbral de recuperación debe ser menor que el de alerta.")
    if cfg["disk_clear_free_percent"] <= cfg["disk_warn_free_percent"] or cfg["disk_clear_min_free_gib"] < cfg["disk_min_free_gib"]:
        raise ValueError("Disco: la recuperación debe exigir más espacio que la alerta.")
    if not isinstance(cfg["expected_processes"], list) or not all(isinstance(p, str) and p.strip() for p in cfg["expected_processes"]):
        raise ValueError("expected_processes debe ser una lista de nombres de proceso.")
    for key in ("disk_path", "network_interface", "temperature_sensor", "librehardwaremonitor_path", "service_url"):
        if cfg[key] is not None and not isinstance(cfg[key], str):
            raise ValueError(f"{key} debe ser texto o null.")
    if cfg["temperature_warn_c"] is not None and (isinstance(cfg["temperature_warn_c"], bool) or not isinstance(cfg["temperature_warn_c"], (int, float)) or not math.isfinite(cfg["temperature_warn_c"])):
        raise ValueError("temperature_warn_c debe ser un número finito o null.")
    if cfg["temperature_provider"] not in ("auto", "psutil", "librehardwaremonitor"):
        raise ValueError("temperature_provider debe ser auto, psutil o librehardwaremonitor.")
    telegram = cfg["telegram"]
    if not isinstance(telegram["enabled"], bool):
        raise ValueError("telegram.enabled debe ser booleano.")
    for key in ("bot_token", "chat_id"):
        if not isinstance(telegram[key], str):
            raise ValueError(f"telegram.{key} debe ser texto.")
    for key in ("service_latency_warn_ms", "service_latency_clear_ms"):
        value = cfg[key]
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0):
            raise ValueError(f"{key} debe ser un número no negativo o null.")
    if cfg["service_latency_warn_ms"] is not None:
        clear = cfg["service_latency_clear_ms"]
        if clear is None:
            cfg["service_latency_clear_ms"] = cfg["service_latency_warn_ms"] * 0.8
        elif clear >= cfg["service_latency_warn_ms"]:
            raise ValueError("La latencia de recuperación debe ser menor que la de alerta.")
    return cfg


class DiskTrend:
    """Extrapola espacio, nunca fecha de avería. Sólo con tendencia consistente."""
    def __init__(self):
        self.points = deque(maxlen=720)

    def update(self, now, free_bytes):
        if free_bytes is None:
            self.points.clear()
            return {"hours_to_full": None, "reason": "Lectura no disponible"}
        self.points.append((now, free_bytes))
        if len(self.points) < 30 or self.points[-1][0] - self.points[0][0] < 300:
            return {"hours_to_full": None, "reason": "Requiere al menos 30 lecturas y 5 minutos"}
        xs = [x - self.points[0][0] for x, _ in self.points]
        ys = [y for _, y in self.points]
        mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
        xx = sum((x - mx) ** 2 for x in xs)
        if xx <= 0:
            return {"hours_to_full": None, "reason": "Intervalo insuficiente"}
        slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / xx
        variance = sum((y - my) ** 2 for y in ys)
        residual = sum((y - (my + slope * (x - mx))) ** 2 for x, y in zip(xs, ys))
        r2 = 1 - residual / variance if variance else 0
        if slope >= -1024 or r2 < 0.8:
            return {"hours_to_full": None, "reason": "Sin disminución consistente de espacio"}
        return {"hours_to_full": round(max(0, free_bytes) / -slope / 3600, 2),
                "loss_bytes_s": round(-slope, 1), "r_squared": round(r2, 3),
                "reason": "Estimación si continúa la misma tendencia; no predice averías"}


@dataclass
class Observation:
    key: str
    triggered: bool | None
    hold_s: float
    title: str
    evidence: dict
    recommendation: str
    severity: str = "warning"
    first_signal_ts: str | None = None


class RuleEngine:
    def __init__(self, config):
        self.config = config
        self.pending = {}
        self.clearing = {}
        self.active = {}

    def observations(self, sample):
        c = self.config
        out = []
        for key, title, value, warn, clear, advice in [
            ("cpu", "CPU alta de forma sostenida", sample.get("cpu_percent"), c["cpu_warn_percent"], c["cpu_clear_percent"], "Revisar los procesos que más CPU usan; comprobar si la carga es esperada."),
            ("ram", "Poca memoria RAM disponible", sample.get("ram", {}).get("percent"), c["ram_warn_percent"], c["ram_clear_percent"], "Revisar los procesos que más RAM usan; guardar trabajo y cerrar aplicaciones prescindibles con autorización."),
        ]:
            threshold = clear if key in self.active else warn
            process_key = "top_cpu_processes" if key == "cpu" else "top_memory_processes"
            out.append(Observation(key, None if value is None else value >= threshold, c["persistence_s"], title,
                                   {"value_percent": value, "trigger_percent": warn, "clear_percent": clear,
                                    "top_processes": sample.get(process_key, [])[:5]}, advice))
        d = sample.get("disk", {})
        free, percent = d.get("free_bytes"), d.get("free_percent")
        active = "disk" in self.active
        gb_limit = c["disk_clear_min_free_gib"] if active else c["disk_min_free_gib"]
        pct_limit = c["disk_clear_free_percent"] if active else c["disk_warn_free_percent"]
        low = None if free is None or percent is None else free < gb_limit * 2 ** 30 or percent < pct_limit
        out.append(Observation("disk", low, c["disk_hold_s"], "Espacio de almacenamiento insuficiente",
                               {"path": d.get("path"), "free_gib": None if free is None else round(free / 2 ** 30, 2), "free_percent": percent},
                               "Revisar crecimiento, respaldos y archivos temporales. No borrar automáticamente.",
                               "critical" if percent is not None and percent < 5 else "warning"))
        forecast = sample.get("disk_forecast", {})
        hours = forecast.get("hours_to_full")
        out.append(Observation("disk_trend", None if hours is None else hours < c["disk_forecast_warn_hours"], c["disk_hold_s"],
                               "El espacio podría agotarse si sigue esta tendencia", forecast,
                               "Revisar qué genera archivos y liberar espacio con autorización. La extrapolación depende del ritmo de crecimiento."))
        t = sample.get("cpu_temperature", {})
        value, limit = t.get("celsius"), t.get("warn_c")
        temp_limit = limit - 5 if limit is not None and "temperature" in self.active else limit
        out.append(Observation("temperature", None if value is None or temp_limit is None else value >= temp_limit, 15,
                               "Temperatura del CPU sobre el límite configurado", t,
                               "Reducir carga y revisar ventilación. Verificar el límite del fabricante y el sensor de origen."))
        for name, status in sample.get("expected_processes", {}).items():
            out.append(Observation("process:" + name, None if status is None else not status, c["process_hold_s"],
                                   "Proceso esperado ausente: " + name, {"process_name": name, "running": status},
                                   "Comprobar si la salida fue planeada; revisar o iniciar manualmente la aplicación.", "critical"))
        service = sample.get("service")
        if service is not None:
            failures = service.get("consecutive_failures", 0)
            triggered = None if service.get("ok") is None else (not service["ok"] if "service" in self.active else failures >= c["service_failures"])
            out.append(Observation("service", triggered, 0, "Servicio HTTP configurado sin respuesta saludable", service,
                                   "Revisar el servicio y la conectividad. Esta prueba no determina por sí sola la causa de la falla.", "critical", service.get("first_failure_ts")))
            latency_warn = c["service_latency_warn_ms"]
            if latency_warn is not None:
                latency = service.get("latency_ms")
                threshold = c["service_latency_clear_ms"] if "service_latency" in self.active else latency_warn
                latency_high = None if latency is None or service.get("ok") is None else service["ok"] and latency >= threshold
                out.append(Observation("service_latency", latency_high, c["service_latency_hold_s"],
                                       "Servicio HTTP degradado, aunque todavía responde",
                                       {"latency_ms": latency, "trigger_ms": latency_warn,
                                        "clear_ms": c["service_latency_clear_ms"], "url_configured": True},
                                       "Revisar carga y dependencias del servicio antes de que deje de responder."))
        b = sample.get("battery")
        if b:
            pct = b.get("percent")
            limit = 20 if "battery" in self.active else 15
            triggered = None if pct is None or b.get("plugged") is None else not b["plugged"] and pct < limit
            out.append(Observation("battery", triggered, 10, "Batería baja sin alimentación", b,
                                   "Conectar alimentación y guardar el trabajo."))
        return out

    def evaluate(self, observations, monotonic_now, timestamp):
        changes = []
        for obs in observations:
            key = obs.key
            if obs.triggered is None:
                self.pending.pop(key, None)
                self.clearing.pop(key, None)
                if key in self.active:
                    self.active[key]["quality"] = "unknown"
                continue
            if obs.triggered:
                self.clearing.pop(key, None)
                first_mono, first_ts = self.pending.setdefault(key, (monotonic_now, timestamp))
                if key not in self.active and monotonic_now - first_mono >= obs.hold_s:
                    incident = {"id": str(uuid.uuid4()), "rule_key": key, "severity": obs.severity,
                                "title": obs.title, "first_signal_ts": obs.first_signal_ts or first_ts, "detected_ts": timestamp,
                                "evidence": obs.evidence, "recommendation": obs.recommendation, "quality": "ok"}
                    self.active[key] = incident
                    changes.append(("opened", dict(incident)))
                elif key in self.active:
                    self.active[key]["quality"] = "ok"
                    self.active[key]["evidence"] = obs.evidence
                    if self.active[key]["severity"] != obs.severity:
                        self.active[key]["severity"] = obs.severity
                        changes.append(("severity", dict(self.active[key])))
            else:
                self.pending.pop(key, None)
                if key in self.active:
                    self.active[key]["quality"] = "ok"
                    start = self.clearing.setdefault(key, monotonic_now)
                    if monotonic_now - start >= self.config["recovery_s"]:
                        incident = self.active.pop(key)
                        incident["recovered_ts"] = timestamp
                        changes.append(("recovered", dict(incident)))
                        self.clearing.pop(key, None)
        return changes


class Store:
    def __init__(self, path):
        self.lock = threading.RLock()
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript("""
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS samples(id INTEGER PRIMARY KEY, ts TEXT, device_id TEXT, payload TEXT);
        CREATE INDEX IF NOT EXISTS samples_ts ON samples(ts);
        CREATE TABLE IF NOT EXISTS incidents(
          id TEXT PRIMARY KEY, rule_key TEXT, severity TEXT, title TEXT, first_signal_ts TEXT, detected_ts TEXT,
          acknowledged_ts TEXT, action_ts TEXT, action_note TEXT, recovered_ts TEXT,
          status TEXT DEFAULT 'open', evidence TEXT, recommendation TEXT);
        """)
        # Un reinicio no demuestra recuperación. Conservamos el registro anterior.
        with self.conn:
            self.conn.execute("UPDATE incidents SET status='interrupted' WHERE status='open'")
        self.last_prune = 0.0

    def save(self, sample, changes, retention_hours):
        with self.lock, self.conn:
            self.conn.execute("INSERT INTO samples(ts,device_id,payload) VALUES(?,?,?)", (sample["timestamp"], sample["device_id"], json.dumps(sample, ensure_ascii=False, allow_nan=False)))
            for event, i in changes:
                if event == "opened":
                    self.conn.execute("INSERT INTO incidents(id,rule_key,severity,title,first_signal_ts,detected_ts,evidence,recommendation) VALUES(?,?,?,?,?,?,?,?)", (i["id"], i["rule_key"], i["severity"], i["title"], i["first_signal_ts"], i["detected_ts"], json.dumps(i["evidence"], ensure_ascii=False), i["recommendation"]))
                elif event == "recovered":
                    self.conn.execute("UPDATE incidents SET recovered_ts=?,status='recovered' WHERE id=?", (i["recovered_ts"], i["id"]))
                elif event == "severity":
                    self.conn.execute("UPDATE incidents SET severity=?,evidence=? WHERE id=?", (i["severity"], json.dumps(i["evidence"], ensure_ascii=False), i["id"]))
            now = time.time()
            if now - self.last_prune > 3600:
                cutoff = datetime.fromtimestamp(now - retention_hours * 3600, timezone.utc).isoformat(timespec="milliseconds")
                self.conn.execute("DELETE FROM samples WHERE ts < ?", (cutoff,))
                self.last_prune = now

    def history(self, limit=120):
        with self.lock:
            rows = self.conn.execute("SELECT payload FROM samples ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [json.loads(r[0]) for r in reversed(rows)]

    def incidents(self, limit=30):
        with self.lock:
            rows = self.conn.execute("SELECT * FROM incidents ORDER BY detected_ts DESC LIMIT ?", (limit,)).fetchall()
        results = []
        for row in rows:
            item = dict(row)
            item["evidence"] = json.loads(item["evidence"])
            start = datetime.fromisoformat(item["first_signal_ts"])
            item["seconds_to_detection"] = round((datetime.fromisoformat(item["detected_ts"]) - start).total_seconds(), 1)
            for field in ("acknowledged_ts", "action_ts", "recovered_ts"):
                value = item[field]
                item["seconds_to_" + field.removesuffix("_ts")] = None if value is None else round((datetime.fromisoformat(value) - start).total_seconds(), 1)
            results.append(item)
        return results

    def mark(self, incident_id, action=False, note=""):
        with self.lock, self.conn:
            row = self.conn.execute("SELECT * FROM incidents WHERE id=?", (incident_id,)).fetchone()
            if row is None:
                raise KeyError(incident_id)
            if row["status"] != "open":
                raise ValueError("El incidente ya no está abierto.")
            ts = utc_now()
            if action:
                self.conn.execute("UPDATE incidents SET action_ts=COALESCE(action_ts,?),action_note=? WHERE id=?", (ts, note, incident_id))
            else:
                self.conn.execute("UPDATE incidents SET acknowledged_ts=COALESCE(acknowledged_ts,?) WHERE id=?", (ts, incident_id))

    def close(self):
        with self.lock:
            self.conn.close()
