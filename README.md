# Monitor TI: base para el reto «Antes de que suene el teléfono»

Prototipo local en Python, preparado el 9 de octubre de 2026. Obtiene lecturas reales del sistema operativo, guarda historial e incidentes y ofrece un panel en español. Funciona sin ESP32. El módulo ESP32 es opcional y debe validarse en la placa del equipo.

El reto de la imagen pide reducir el tiempo entre la primera señal de una falla de TI y una acción efectiva. El objetivo del proyecto es detectar degradación, priorizar atención y verificar resultados. No garantiza anticipar todas las fallas ni identifica por sí solo la causa de un incidente.

## Inicio en Windows 10/11

Instala Python 3.10 o posterior si todavía no está disponible. Extrae el ZIP y abre PowerShell **dentro de `monitor_ti_prototipo`**:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m monitor_ti
```

Abre **http://127.0.0.1:8875** y deja la consola ejecutándose. Ctrl+C detiene el monitor. No es necesario activar el entorno virtual ni cambiar la política de PowerShell. Si tu instalación no tiene `py`, usa `python` en el primer comando.

El puerto 8875 evita una colisión observada con otro servidor local que ya ocupa 8765. Si tampoco está libre, ejecuta `python -m monitor_ti --port 9876` y abre la misma dirección con ese puerto.

Linux/macOS:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m monitor_ti
```

Las bibliotecas no se presuponen instaladas: `psutil` es la dependencia principal. SQLite, el servidor HTTP y las demás utilidades son de la biblioteca estándar. El panel no utiliza CDNs ni necesita conexión a internet después de instalar dependencias.

## Qué recopila esta base

| Lectura | Fuente y límite |
| --- | --- |
| Uso total y por núcleo de CPU | `psutil`; ignora la primera lectura de calentamiento |
| Frecuencia de CPU | `psutil`; valor promedio/reportado por la plataforma, no garantiza una lectura independiente por núcleo |
| RAM total, disponible y porcentaje | RAM disponible, no sólo RAM libre |
| Memoria de intercambio | Porcentaje expuesto por el sistema; no demuestra daño físico |
| Espacio de una unidad | Unidad del directorio actual, configurable con `disk_path` |
| Lectura/escritura de disco | Tasa derivada de contadores del sistema; no es un benchmark |
| Tráfico por interfaz | Mbps observados de entrada/salida; clasifica loopback, VPN/túnel, Wi-Fi, Ethernet y virtual por nombre, sin afirmar velocidad contratada |
| Estado de interfaz, enlace y contadores de errores | Los contadores no equivalen a pérdida de paquetes de una prueba ICMP |
| Procesos | Nombre, PID, RAM, CPU y tasas de I/O cuando hay permiso; no captura comandos, contenido de archivos o historial de navegación |
| Procesos críticos esperados | Lista configurable; ausencia no confirmada si faltan permisos de lectura |
| Temperatura interna | `psutil` o LibreHardwareMonitor opcional; conserva `null`, fuente y motivo si no hay sensor válido |
| Batería y alimentación | Sólo si el sistema lo expone |
| Tiempo encendida | Desde el arranque según el sistema operativo |
| Servicio HTTP | URL explícita y opcional; código, latencia, degradación sostenida configurable y fallos consecutivos |
| Tendencia de espacio | Estimación lineal hasta disco lleno; al menos 30 lecturas, 5 minutos y tendencia consistente |

CPU de procesos se normaliza respecto a todos los procesadores lógicos; puede diferir de herramientas que muestran 100% por núcleo. La interfaz de red se elige inicialmente por tráfico acumulado entre interfaces activas; selecciona una explícitamente si hay VPN o adaptadores virtuales. Las métricas en un contenedor reflejan lo que su sistema expone y pueden diferir de sus cuotas.

Datos no disponibles se guardan como `null` y aparecen como «—». Temperatura ambiente y temperatura interna del CPU son mediciones distintas. La base no inventa SMART/NVMe, GPU, ventiladores, eventos de Windows, pérdida ICMP, DNS, velocidad máxima de internet, respaldo o estado del antivirus. En la validación de este equipo `smartctl` no estaba instalado; esas integraciones quedan como segunda fase.

## Alertas iniciales y verificación

Los umbrales son valores de prueba configurables, no límites universales del hardware:

- CPU o RAM ≥90% durante 30 segundos. Recuperación bajo 80% durante 10 segundos.
- Disco con menos de 10% libre o menos de 5 GiB durante 20 segundos. Recuperación requiere 12% y 6 GiB libres durante 10 segundos. Vigila una sola unidad para evitar alertas en particiones auxiliares.
- Procesos esperados ausentes durante 15 segundos, si se configuraron y se pudo confirmar su ausencia.
- Servicio HTTP tras 3 comprobaciones fallidas consecutivas; una respuesta saludable sostenida confirma recuperación.
- Servicio HTTP todavía disponible pero con latencia sostenida, sólo si se configura `service_latency_warn_ms`.
- CPU por encima de un límite de temperatura del sensor o uno configurado expresamente. Sin límite ni lectura disponible, no genera esa alerta.
- Batería por debajo de 15%, sin alimentación, durante 10 segundos.
- Espacio con agotamiento extrapolado en menos de 24 horas, sólo con una tendencia consistente y sostenida.

Se agrupan las lecturas de una misma anomalía en un incidente. Un pico aislado no se convierte en múltiples alertas. Una lectura desconocida no cierra una alerta como si estuviera resuelta. Un reinicio del monitor marca los incidentes anteriores como interrumpidos, nunca como recuperados.

Cada incidente guarda primera señal observada, detección, reconocimiento, inicio de atención declarado, recomendación y recuperación observada. Los tiempos son discretos: dependen de la frecuencia de muestreo y del reloj del sistema. «Reconocido» y «atención iniciada» no prueban una acción efectiva; la recuperación confirma que la métrica volvió al rango configurado, no necesariamente que desapareció una causa física.

## Demostración sin estresar ni dañar la computadora

Abre dos consolas con el mismo entorno. En la primera:

```powershell
.\.venv\Scripts\python.exe tools\demo_service.py
```

En la segunda:

```powershell
.\.venv\Scripts\python.exe -m monitor_ti --config config\config.demo.json
```

1. Comprueba que el panel muestra «Servicio supervisado: Responde».
2. En la consola del servicio de prueba, presiona Ctrl+C. El monitor sigue abierto.
3. Espera 3 pruebas fallidas. En este perfil se consulta cada 2 segundos; la conexión fallida puede añadir tiempo.
4. Reconoce la alerta y registra «Volver a iniciar el servicio de prueba».
5. Ejecuta de nuevo `tools\demo_service.py` en la primera consola.
6. Comprueba que el mismo incidente pasa a recuperado y conserva sus tiempos.

La falla del servicio es real y controlada; no se reemplaza la telemetría por números inventados. Esta demo prueba reacción y recuperación. Para demostrar prevención, muestra una advertencia de capacidad antes del disco lleno o de presión de memoria antes de bloquearse, usando una carga acotada y una unidad de prueba; no llenes el disco principal ni provoques sobrecalentamiento.

La demostración preventiva incluida usa latencia controlada, sin llenar el disco ni forzar CPU/RAM:

```powershell
# Consola 1: el servicio sigue respondiendo, pero tarda 750 ms
.\.venv\Scripts\python.exe tools\demo_service.py --delay-ms 750

# Consola 2: advierte por degradación sostenida a partir de 500 ms
.\.venv\Scripts\python.exe -m monitor_ti --config config\config.degradation-demo.json
```

Comprueba la advertencia «Servicio HTTP degradado, aunque todavía responde». Detén la primera consola y vuelve a ejecutar `tools\demo_service.py` sin `--delay-ms`; la recuperación se confirma por la métrica. Es un modo real y separado: no sustituye otras lecturas ni mezcla números simulados.

## Configuración

Copia `config\config.example.json` a `config\config.json`, edítalo y ejecuta:

```powershell
.\.venv\Scripts\python.exe -m monitor_ti --config config\config.json
```

Ejemplos de campos: `expected_processes: ["notepad.exe"]`, `disk_path: "C:\\"`, `network_interface: "Wi-Fi"`. Los nombres reales varían por equipo. `temperature_sensor` selecciona exactamente un ID devuelto por `/api/state`; no uses un sensor ambiental como si fuera de CPU. Define `temperature_warn_c` según el fabricante y el componente. `service_url` queda desactivado por defecto para no generar tráfico externo.

### Temperatura en Windows con LibreHardwareMonitor (opcional)

1. Descarga o compila LibreHardwareMonitor únicamente desde su repositorio oficial.
2. Coloca `LibreHardwareMonitorLib.dll` en `providers\` o indica su ruta exacta en `librehardwaremonitor_path`.
3. Instala el adaptador Python: `.\.venv\Scripts\python.exe -m pip install -r requirements-lhm.txt`.
4. Usa `"temperature_provider": "librehardwaremonitor"` y ejecuta el monitor con los permisos requeridos por el proveedor.
5. Revisa `/api/state`: la lectura conserva el identificador y `source: LibreHardwareMonitor/CPU`. Si falta la DLL, `pythonnet`, un permiso o un sensor CPU válido, el valor sigue siendo `null` y se muestra el motivo.

El proyecto no descarga ni instala drivers o binarios automáticamente. Consulta [Sensores y seguridad](docs/SENSORES.md) antes de conectar sensores externos.

Los datos se generan en `data/monitor.sqlite3`; `data/device_id.txt` conserva la identidad local. Las muestras tienen retención de 24 horas por defecto. Los incidentes se conservan. Ninguna lectura de la máquina de desarrollo está incluida en el ZIP.

## ESP32 con una utilidad concreta

`tools/esp32_bridge.py` envía el estado del monitor por serial. `firmware/esp32_watchdog/esp32_watchdog.ino` enciende LEDs y vigila la pérdida de latido:

- Verde: datos recientes sin alertas detectadas.
- Ámbar: alerta; ámbar intermitente: datos sin confirmar o aún no recibió un latido.
- Rojo: incidente crítico; rojo intermitente: perdió el latido durante más de 15 segundos.

Instala la dependencia opcional y ejecuta, sustituyendo el puerto real:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-esp32.txt
.\.venv\Scripts\python.exe tools\esp32_bridge.py --port COM5
```

Carga el sketch en un ESP32 clásico con Arduino IDE; usa LEDs externos con resistencias y adapta los GPIO a la placa. Cierra el monitor serial de Arduino antes de abrir el puente. El sketch usa sólo `Arduino.h`.

**Independencia:** si alimentas el ESP32 desde la computadora y ésta se apaga, también se apaga el vigilante. Para detectar apagado o corte del PC necesita alimentación independiente y un enlace adecuado. En esta prueba serial se puede comprobar la pérdida del agente mientras el ESP32 permanece encendido. Para un watchdog de una PC apagada, utiliza después Wi-Fi o UART a 3.3 V con alimentación independiente. El siguiente paso recomendado es ESP32 por Wi-Fi, sensor ambiental externo y servidor en otra computadora. El ESP32 no conoce RAM, procesos ni espacio de la PC sin un agente.

## Pruebas y alcance

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Incluye pruebas de persistencia, histéresis, datos desconocidos, cálculos de tasas, tendencia, configuración, clasificación de interfaces, degradación por latencia y un flujo HTTP real de falla → atención → recuperación. La validación más reciente se hizo en Windows con Python 3.13 y psutil 7.2.2; consulta [Resultados de validación](docs/VALIDACION.md). El hardware ESP32 sigue requiriendo comprobación física.

El servidor escucha sólo en localhost. Esta versión monitorea una computadora; un despliegue para una PyME requiere agentes por equipo, servidor separado, identidad, autenticación, comunicaciones protegidas y mantenimiento programado. No cierra aplicaciones, borra archivos, reinicia equipos ni cambia configuración del sistema.

## Referencias técnicas oficiales

- [psutil: API y disponibilidad por plataforma](https://psutil.io/api/).
- [LibreHardwareMonitor: repositorio oficial y permisos de sensores](https://github.com/LibreHardwareMonitor/LibreHardwareMonitor).
- [smartmontools: repositorio oficial](https://github.com/smartmontools/smartmontools).
- [NVIDIA: NVML](https://docs.nvidia.com/deploy/nvml-api/latest/index.html).
- [Espressif: el sensor interno del ESP32-S2 mide su silicio, no el CPU de una PC ni el ambiente con precisión](https://docs.espressif.com/projects/esp-idf/en/stable/esp32s2/api-reference/peripherals/temp_sensor.html).
