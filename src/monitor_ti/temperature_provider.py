"""Proveedores de temperatura opcionales; nunca inventan una lectura."""
from __future__ import annotations

import platform
from pathlib import Path


class LibreHardwareMonitorProvider:
    """Lee LibreHardwareMonitorLib.dll oficial mediante pythonnet, si existe."""

    def __init__(self, configured_path=None):
        self.computer = None
        self.reason = None
        self.dll_path = None
        if platform.system() != "Windows":
            self.reason = "Sólo disponible en Windows"
            return
        candidates = []
        if configured_path:
            candidates.append(Path(configured_path).expanduser())
        candidates.extend([
            Path.cwd() / "providers" / "LibreHardwareMonitorLib.dll",
            Path(r"C:\Program Files\LibreHardwareMonitor\LibreHardwareMonitorLib.dll"),
            Path(r"C:\Program Files (x86)\LibreHardwareMonitor\LibreHardwareMonitorLib.dll"),
        ])
        self.dll_path = next((p.resolve() for p in candidates if p.is_file()), None)
        if self.dll_path is None:
            self.reason = "LibreHardwareMonitorLib.dll no encontrada"
            return
        try:
            import clr
            clr.AddReference(str(self.dll_path))
            from LibreHardwareMonitor.Hardware import Computer
            self.computer = Computer()
            self.computer.IsCpuEnabled = True
            self.computer.Open()
        except (ImportError, OSError, RuntimeError) as exc:
            self.reason = f"{type(exc).__name__}: proveedor o permiso no disponible"
            self.computer = None

    @property
    def available(self):
        return self.computer is not None

    def read(self):
        if not self.available:
            return [], self.reason
        rows = []
        try:
            for hardware in self.computer.Hardware:
                hardware.Update()
                hardware_type = str(hardware.HardwareType)
                if hardware_type != "Cpu":
                    continue
                sensors = list(hardware.Sensors)
                for child in hardware.SubHardware:
                    child.Update()
                    sensors.extend(list(child.Sensors))
                for sensor in sensors:
                    if str(sensor.SensorType) != "Temperature" or sensor.Value is None:
                        continue
                    rows.append({
                        "id": "lhm:" + str(sensor.Identifier),
                        "source": "LibreHardwareMonitor/CPU",
                        "label": str(sensor.Name),
                        "celsius": float(sensor.Value),
                        "warn_c": None,
                        "critical_c": None,
                    })
            return rows, None if rows else "El proveedor no expuso temperaturas de CPU"
        except (OSError, RuntimeError) as exc:
            return [], f"{type(exc).__name__}: lectura del proveedor falló"

    def close(self):
        if self.computer is not None:
            self.computer.Close()
