"""Lecturas reales mediante psutil. Lo no expuesto queda como null."""
import os
import platform
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import psutil

from .core import rate, utc_now
from .temperature_provider import LibreHardwareMonitorProvider


class Collector:
    def __init__(self, config, device_id):
        self.config = config
        self.device_id = device_id
        self.previous = {}
        self.previous_processes = {}
        self.previous_time = None
        self.service_last = -float("inf")
        self.service = None
        self.selected_interface = config["network_interface"]
        self.lhm = LibreHardwareMonitorProvider(config["librehardwaremonitor_path"])

    @staticmethod
    def interface_kind(name):
        folded = name.casefold()
        if folded in ("lo", "lo0") or "loopback" in folded:
            return "loopback"
        if any(word in folded for word in ("vpn", "tap", "tun", "wireguard", "openvpn")):
            return "vpn_o_tunel"
        if any(word in folded for word in ("wi-fi", "wifi", "wlan", "wireless")):
            return "wifi"
        if any(word in folded for word in ("ethernet", "eth")):
            return "ethernet"
        if any(word in folded for word in ("virtual", "vmware", "hyper-v", "vethernet")):
            return "virtual"
        return "otro"

    def read(self):
        now = time.monotonic()
        elapsed = 0 if self.previous_time is None else now - self.previous_time
        errors = []

        def attempt(name, fn, default=None):
            try:
                return fn()
            except (OSError, RuntimeError, psutil.Error, AttributeError, NotImplementedError) as exc:
                errors.append({"metric": name, "reason": type(exc).__name__})
                return default

        # Todas las llamadas CPU se hacen en el mismo hilo; primera lectura ignorada.
        cpu = attempt("cpu", lambda: psutil.cpu_percent(interval=None))
        cpu_per_core = attempt("cpu_per_core", lambda: psutil.cpu_percent(interval=None, percpu=True))
        cpu_frequency = attempt("cpu_frequency", psutil.cpu_freq)
        if self.previous_time is None:
            cpu = None
            cpu_per_core = None
        mem = attempt("ram", psutil.virtual_memory)
        swap = attempt("swap", psutil.swap_memory)
        disk_path = self.config["disk_path"] or (Path.cwd().anchor or "/")
        disk = attempt("disk", lambda: psutil.disk_usage(disk_path))
        io = attempt("disk_io", psutil.disk_io_counters)
        previous_io = self.previous.get("io")

        nics = attempt("network", lambda: psutil.net_io_counters(pernic=True), {}) or {}
        nic_stats = attempt("network_state", psutil.net_if_stats, {}) or {}
        previous_nics = self.previous.get("nics", {})
        interfaces = []
        for name, counters in nics.items():
            stats = nic_stats.get(name)
            prev = previous_nics.get(name)
            down = rate(counters.bytes_recv, None if prev is None else prev.bytes_recv, elapsed)
            up = rate(counters.bytes_sent, None if prev is None else prev.bytes_sent, elapsed)
            kind = self.interface_kind(name)
            interfaces.append({"name": name, "kind": kind, "is_loopback": kind == "loopback",
                               "is_vpn_like": kind == "vpn_o_tunel", "up": None if stats is None else stats.isup,
                               "download_mbps": None if down is None else round(down * 8 / 1_000_000, 4),
                               "upload_mbps": None if up is None else round(up * 8 / 1_000_000, 4),
                               "link_mbps": None if stats is None or not stats.speed else stats.speed,
                               "receive_errors": counters.errin, "send_errors": counters.errout})
        if self.selected_interface is None:
            candidates = [n for n in interfaces if n["up"] and not n["is_loopback"] and not n["is_vpn_like"]]
            if not candidates:
                candidates = [n for n in interfaces if n["up"] and not n["is_loopback"]]
            if candidates:
                self.selected_interface = max(candidates, key=lambda n: nics[n["name"]].bytes_recv + nics[n["name"]].bytes_sent)["name"]
        network = next((n for n in interfaces if n["name"] == self.selected_interface), None)

        processes, current_processes, names = [], {}, set()
        scan_complete = True
        try:
            for proc in psutil.process_iter():
                try:
                    with proc.oneshot():
                        name = proc.name()
                        names.add(name.casefold())
                        pid, created = proc.pid, proc.create_time()
                        usage = proc.memory_info().rss
                        times = proc.cpu_times()
                        cpu_seconds = times.user + times.system
                        try:
                            process_io = proc.io_counters()
                            read_bytes, write_bytes = process_io.read_bytes, process_io.write_bytes
                        except (psutil.AccessDenied, AttributeError, NotImplementedError):
                            read_bytes = write_bytes = None
                    key = (pid, created)
                    current_processes[key] = {"cpu": cpu_seconds, "read": read_bytes, "write": write_bytes}
                    previous_process = self.previous_processes.get(key, {})
                    cpu_rate = rate(cpu_seconds, previous_process.get("cpu"), elapsed)
                    read_rate = rate(read_bytes, previous_process.get("read"), elapsed)
                    write_rate = rate(write_bytes, previous_process.get("write"), elapsed)
                    normalized = None if cpu_rate is None else min(100, max(0, 100 * cpu_rate / (os.cpu_count() or 1)))
                    processes.append({"pid": pid, "name": name, "ram_mib": round(usage / 2 ** 20, 1),
                                      "cpu_percent_total": None if normalized is None else round(normalized, 2),
                                      "read_mib_s": None if read_rate is None else round(read_rate / 2 ** 20, 3),
                                      "write_mib_s": None if write_rate is None else round(write_rate / 2 ** 20, 3)})
                except psutil.NoSuchProcess:
                    continue
                except psutil.AccessDenied:
                    # No podemos asegurar la ausencia de un proceso oculto por permisos.
                    scan_complete = False
            processes.sort(key=lambda p: p["ram_mib"], reverse=True)
        except (OSError, psutil.Error) as exc:
            scan_complete = False
            errors.append({"metric": "processes", "reason": type(exc).__name__})
        expected = {name: True if name.casefold() in names else (False if scan_complete else None) for name in self.config["expected_processes"]}

        temperature_rows = []
        temperature_reason = None
        provider = self.config["temperature_provider"]
        if provider in ("auto", "librehardwaremonitor") and self.lhm.available:
            temperature_rows, temperature_reason = self.lhm.read()
        elif provider == "librehardwaremonitor":
            temperature_reason = self.lhm.reason
        if not temperature_rows and provider in ("auto", "psutil") and hasattr(psutil, "sensors_temperatures"):
            temps = attempt("temperature", psutil.sensors_temperatures, {}) or {}
            for group, readings in temps.items():
                for index, t in enumerate(readings):
                    identifier = f"{group}:{t.label or index}"
                    temperature_rows.append({"id": identifier, "source": "psutil/" + group, "label": t.label or str(index),
                                             "celsius": t.current, "warn_c": t.high, "critical_c": t.critical})
        selected_temperature = None
        wanted = self.config["temperature_sensor"]
        if wanted:
            selected_temperature = next((t for t in temperature_rows if t["id"] == wanted), None)
        else:
            # No confundir ACPI, GPU o disco con el sensor del CPU.
            candidates = [t for t in temperature_rows if t["source"].split("/")[-1] in ("coretemp", "k10temp", "zenpower", "cpu_thermal") and t["celsius"] is not None]
            if candidates:
                selected_temperature = max(candidates, key=lambda t: t["celsius"])
        if not temperature_rows and temperature_reason is None:
            temperature_reason = "El sistema operativo/proveedor no expuso un sensor interno válido"
        cpu_temperature = dict(selected_temperature) if selected_temperature else {
            "celsius": None, "warn_c": None, "source": "no_disponible", "reason": temperature_reason}
        if self.config["temperature_warn_c"] is not None:
            cpu_temperature["warn_c"] = self.config["temperature_warn_c"]

        battery = attempt("battery", psutil.sensors_battery)
        service_url = self.config["service_url"]
        if service_url and now - self.service_last >= self.config["service_every_s"]:
            self.service_last = now
            started = time.monotonic()
            status_code = None
            try:
                parsed = urllib.parse.urlparse(service_url)
                if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
                    raise ValueError("Sólo URLs HTTP/HTTPS sin credenciales")
                with urllib.request.urlopen(service_url, timeout=2) as response:
                    status_code = response.status
                    response.read(64)
                ok, reason = 200 <= status_code < 400, None
            except urllib.error.HTTPError as exc:
                ok, status_code, reason = False, exc.code, "HTTPError"
            except (OSError, ValueError, urllib.error.URLError) as exc:
                ok, reason = False, type(exc).__name__
            failures = 0 if ok else (0 if self.service is None else self.service["consecutive_failures"]) + 1
            first_failure = None if ok else ((self.service or {}).get("first_failure_ts") or utc_now())
            self.service = {"ok": ok, "status_code": status_code, "latency_ms": round((time.monotonic() - started) * 1000, 1),
                            "consecutive_failures": failures, "reason": reason, "timestamp": utc_now(), "first_failure_ts": first_failure}

        read_bps = rate(None if io is None else io.read_bytes, None if previous_io is None else previous_io.read_bytes, elapsed)
        write_bps = rate(None if io is None else io.write_bytes, None if previous_io is None else previous_io.write_bytes, elapsed)
        sample = {"timestamp": utc_now(), "device_id": self.device_id, "source": "real/psutil", "psutil_version": psutil.__version__,
                  "os": platform.system(), "hostname": platform.node(),
                  "uptime_s": attempt("uptime", lambda: round(time.time() - psutil.boot_time())),
                  "cpu_percent": cpu, "cpu_per_core_percent": cpu_per_core, "logical_cpus": os.cpu_count(),
                  "cpu_frequency": None if cpu_frequency is None else {
                      "current_mhz": cpu_frequency.current, "min_mhz": cpu_frequency.min, "max_mhz": cpu_frequency.max,
                      "scope": "promedio/reportado por plataforma; puede no reflejar cada núcleo"},
                  "ram": {} if mem is None else {"total_bytes": mem.total, "available_bytes": mem.available, "percent": mem.percent},
                  "swap": None if swap is None else {"total_bytes": swap.total, "used_bytes": swap.used, "percent": swap.percent},
                  "disk": {"path": disk_path} if disk is None else {"path": disk_path, "total_bytes": disk.total, "free_bytes": disk.free,
                           "free_percent": round(100 * disk.free / disk.total, 2) if disk.total else None},
                  "disk_io": {"read_mib_s": None if read_bps is None else round(read_bps / 2 ** 20, 3),
                              "write_mib_s": None if write_bps is None else round(write_bps / 2 ** 20, 3)},
                  "network": network, "interfaces": interfaces,
                  "top_memory_processes": processes[:10],
                  "top_cpu_processes": sorted(processes, key=lambda p: p["cpu_percent_total"] or 0, reverse=True)[:10],
                  "processes_observed": len(names), "process_scan_complete": scan_complete, "expected_processes": expected,
                  "cpu_temperature": cpu_temperature, "temperature_sensors": temperature_rows,
                  "battery": None if battery is None else {"percent": battery.percent, "plugged": battery.power_plugged,
                             "seconds_left": None if battery.secsleft < 0 else battery.secsleft},
                  "service": self.service, "collection_errors": errors,
                  "availability": {
                      "cpu": {"available": cpu is not None, "source": "psutil"},
                      "cpu_per_core": {"available": cpu_per_core is not None, "source": "psutil"},
                      "temperature": {"available": selected_temperature is not None,
                                      "source": cpu_temperature.get("source"), "reason": cpu_temperature.get("reason")},
                      "process_io": {"available": any(p["read_mib_s"] is not None for p in processes), "source": "psutil"},
                  }}
        self.previous = {"io": io, "nics": nics}
        self.previous_processes = current_processes
        self.previous_time = now
        return sample

    def close(self):
        self.lhm.close()
