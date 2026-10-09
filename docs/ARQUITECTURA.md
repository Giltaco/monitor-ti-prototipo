# Arquitectura

```text
Windows / Linux / macOS
        │
        ▼
Collector (psutil + proveedores opcionales)
        │ muestra real cada intervalo
        ▼
RuleEngine ── ventanas, histéresis y calidad desconocida
        │
        ├── Store (SQLite local: muestras e incidentes)
        └── HTTP local (API JSON + panel web)
                         │
                         └── ESP32 serial opcional: estado y watchdog
```

## Directorios

- `src/monitor_ti/`: aplicación, recolección, reglas, persistencia y panel incluido en el paquete.
- `tests/`: pruebas unitarias e integración HTTP real.
- `config/`: perfiles de ejemplo y demostración.
- `tools/`: servicio de demostración y puente serial opcional.
- `firmware/`: sketch del watchdog ESP32.
- `docs/`: validación, sensores y guion para jueces.
- `data/`: estado local ignorado por Git salvo `.gitkeep`.

El alcance actual es una computadora y `127.0.0.1`. La fase multi-equipo debe separar agente, servidor y dispositivo físico, y añadir autenticación y transporte protegido antes de escuchar en la red.
