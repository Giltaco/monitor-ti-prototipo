# Sensores y límites físicos

## Roles que no deben mezclarse

- **Agente Python en la PC:** obtiene CPU, RAM, almacenamiento, procesos y red desde Windows.
- **ESP32 con alimentación propia:** recibe estado/latido, mide el ambiente con un sensor externo y enciende alertas físicas.
- **Servidor posterior en otra PC:** mantiene historia, reglas, incidentes y panel de varios equipos.

Un ESP32 no puede leer por sí solo la RAM, los procesos ni la salud física del disco de una PC. Su sensor interno, cuando existe, mide el silicio del propio ESP32.

## Temperatura interna de la computadora

El orden de fuentes es configurable: `psutil` cuando el sistema la expone o LibreHardwareMonitor oficial mediante `pythonnet`. El proveedor conserva fuente, identificador y motivo de ausencia. Selecciona un sensor CPU concreto y configura el límite según el fabricante; ACPI genérico, GPU, disco y ambiente no se renombran como CPU.

## Sensores externos recomendados

| Sensor | Uso | Conexión típica | Nota |
| --- | --- | --- | --- |
| DS18B20 | Temperatura puntual | 1-Wire y resistencia pull-up adecuada | Etiquetar ubicación; no pegar a componentes energizados sin aislamiento y diseño térmico |
| DHT22 | Ambiente y humedad | GPIO digital | Económico, más lento y menos estable |
| BME280 | Ambiente, humedad y presión | I²C | Buena opción general; verificar que el módulo sea BME280 y no BMP280 |

Guarda unidad, ubicación física, modelo, fecha de observación, secuencia, fuente, calidad y caducidad. Temperatura ambiental y temperatura interna del CPU son señales diferentes.

## Energía y seguridad

No conectes tensión de red, entradas de fuentes ATX ni líneas desconocidas directamente al ESP32. Para consumo energético usa un medidor aislado y certificado disponible para el equipo. El prototipo no incluye medición eléctrica.

## Validación física pendiente

En este equipo aparecieron COM12 y COM13, pero Windows los identifica como enlaces serie Bluetooth, no como una placa ESP32. Antes de declarar el ESP32 funcional hay que conectar la placa y confirmar modelo, VID/PID, sketch cargado, pines, resistencias, LEDs, puerto exclusivo, alimentación independiente y pérdida real de latido durante más de 15 s.
