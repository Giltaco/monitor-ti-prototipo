# Prompt para Codex: monitoreo preventivo de computadoras + ESP32

Copia el texto siguiente en Codex, con la carpeta del prototipo abierta.

---

Actúa como ingeniero de software e IoT. Construye y ejecuta un prototipo pequeño, funcional y demostrable para un hackatón. El reto es **«Antes de que suene el teléfono»**: en una PyME, las señales de una falla de TI deben convertirse rápidamente en una acción efectiva antes de que un usuario tenga que reportarla. Queremos monitorear computadoras, detectar degradación o riesgos con evidencia, orientar atención y medir resultados.

El equipo tiene programadores e integrantes de Mecatrónica. La computadora objetivo usa Windows 10/11. El software será Python. El ESP32 debe aportar vigilancia independiente y alertas físicas, y después sensores ambientales; no lo presentes como un dispositivo capaz de leer por sí solo la RAM, el almacenamiento o los procesos de una computadora.

**Trabaja sobre la base adjunta `monitor_ti_prototipo`:** lee primero su README, configuración, recolector, reglas, panel y pruebas. Conserva lo que ya funciona. No te limites a sugerir pasos: crea o modifica los archivos, instala dependencias en un entorno virtual, ejecuta el programa, prueba los flujos y corrige los errores. Antes de asumir una biblioteca, dispositivo o permiso, comprueba si está disponible. Si el ZIP no está extraído, extráelo en una carpeta del proyecto sin sobrescribir trabajo existente.

## 1. Entrega primero una versión usable sin ESP32

Mantén el alcance inicial de una computadora y un panel local. Usa Python 3.10+, psutil, SQLite y la base HTTP existente. No reescribas todo ni introduzcas nube, cuentas, contenedores o frameworks innecesarios. Si una mejora posterior requiere FastAPI, explica el motivo y migra de forma verificable.

Recopila datos **reales** cada 5 segundos, aislando fallas de cada proveedor:

- CPU total y, si está disponible, por núcleo; frecuencia con su limitación por plataforma.
- RAM total, disponible y porcentaje; paginación/intercambio cuando el sistema lo exponga.
- Espacio de las unidades relevantes y tasas de lectura/escritura. Separa capacidad de salud física del disco.
- Procesos: nombre, PID, CPU, RAM y, cuando sea posible, tasas de I/O. Estar en segundo plano es normal: alerta por consumo sostenido o por la ausencia de un proceso crítico configurado.
- Tráfico de entrada/salida por interfaz: deltas de bytes sobre tiempo real, en Mbps. Identifica VPN/loopback y permite elegir interfaz; no confundas tráfico actual, velocidad de enlace ni velocidad máxima de internet.
- Tiempo encendida y batería/alimentación cuando se expongan.
- Sensores internos de temperatura sólo si una fuente válida puede leerlos. En Windows integra **opcionalmente** LibreHardwareMonitor desde su repositorio oficial, vía WMI o su biblioteca con pythonnet. Comprueba el proveedor y los permisos; no uses ACPI genérico ni una lectura externa como supuesto CPU. No descargues drivers o binarios de sitios no oficiales. Si no se puede medir, conserva `null`, origen y motivo.
- Servicio HTTP configurado por el usuario: estado, latencia y fallas consecutivas. No envíes pruebas a internet por defecto.

Usa ventanas temporales, histéresis y agrupación por incidente. Distingue condiciones normales de una carga esperada, anomalía sostenida, dato desconocido y telemetría desactualizada. Ignora el primer CPU y las primeras tasas; maneja reinicio de contadores, permisos denegados y procesos que terminan durante la lectura. Mantén visible qué mediciones están disponibles en ese equipo.

## 2. Prevención y acción verificable

Implementa o conserva reglas explicables y configurables:

- CPU/RAM altas de forma sostenida: mostrar los procesos con mayor consumo y sugerir revisión.
- Espacio insuficiente: alertar antes de agotarse. Conserva estimación hasta disco lleno sólo con historial suficiente y tendencia consistente; muestra supuestos y falta de datos. No la anuncies como fecha de avería.
- Temperatura elevada: umbral por componente y fabricante; ambiente y CPU separados.
- Proceso/servicio crítico ausente o con fallas sostenidas.
- Agente sin latido: debe detectarlo un observador externo, no depender del agente caído.

Cada incidente guarda: equipo, regla, origen de datos, evidencia, severidad, primera señal observada, detección, reconocimiento, inicio de atención, nota de acción y recuperación comprobada en la métrica. Una confirmación del usuario no equivale a una reparación efectiva. Si se pierde una lectura o se reinicia el monitor, no marques automáticamente el incidente como solucionado.

El panel estará en español, con tarjetas de estado, gráficas de historial, tabla de procesos y alertas con recomendaciones. Debe funcionar a 390 px y escritorio, sin cifras inventadas. Evita un «porcentaje de salud» sin definición. Muestra tiempos entre primera señal, detección, atención y recuperación para demostrar el objetivo del reto. No cierres procesos, borres archivos, reinicies equipos ni instales servicios de sistema automáticamente.

## 3. ESP32 útil y opcional

La base incluye un puente serial y un sketch con LEDs y temporizador de latido. Valida primero ese flujo en la placa real: verde sin alertas detectadas, ámbar para advertencia/datos desconocidos, rojo para crítico y rojo intermitente al perder un latido que antes recibía. No envíes latidos como si fueran saludables cuando las lecturas del agente estén vencidas.

Para la siguiente fase, separa estos papeles:

1. **Agente Python por PC:** lee sistema operativo y envía telemetría.
2. **Servidor en otra PC:** historial, reglas, incidentes y panel para varios equipos.
3. **ESP32 con alimentación propia:** recibe latidos/estado, mide ambiente con sensor externo y da alerta física aunque la PC observada se congele o apague.

Selecciona sensores según el material real: DS18B20 para temperatura puntual; DHT22/BME280 para ambiente y humedad. Etiqueta ubicación y unidad. El sensor interno de un ESP32, si su variante lo expone, mide el chip ESP32, no el CPU de la computadora. No conectes medición de corriente/voltaje de red eléctrica sin un dispositivo adecuado; para consumo energético usa después una medición aislada disponible.

Para Wi-Fi, define un protocolo pequeño con versión, equipo/dispositivo, secuencia, fecha de observación, fecha de recepción, fuente, valores, estado de calidad y caducidad. Elige HTTP o MQTT según la red disponible; no implementes ambos a la vez. Conserva el funcionamiento sin ESP32 y el almacenamiento local. Gestiona reconexiones y distingue «PC sin latido», «ESP32 desconectado», «router sin respuesta» y «servidor no disponible»: una sola prueba fallida no demuestra la causa.

## 4. Datos de segunda fase, sólo después del núcleo

Prioriza SMART/NVMe con smartctl en JSON, si está instalado y autorizado: errores, sectores pendientes/reasignados cuando corresponda, desgaste y advertencias NVMe. Documenta unidades, campos por fabricante y permisos. SMART no garantiza anticipar todas las averías. Después considera GPU NVIDIA con NVML, ventiladores mediante proveedor compatible, eventos de Windows, latencia/pérdida ICMP, DNS y comprobación de un respaldo configurado. No afirmes que psutil obtiene todo ni que uso alto de RAM demuestra daño físico. Un speedtest será manual o poco frecuente para no saturar la red.

No introduzcas aprendizaje automático antes de tener historial real y escenarios etiquetados. Primero usa reglas, tendencias y comparación con la línea base por equipo; no anuncies «IA predictiva» si sólo aplicas umbrales.

## 5. Validación y entrega

- Ejecuta las pruebas existentes y agrega pruebas sólo para los nuevos comportamientos relevantes.
- Prueba el ciclo real de `demo_service.py`: funcionando → servicio detenido → incidente → atención registrada → servicio restaurado → recuperación, conservando un solo incidente y sus tiempos.
- Demuestra prevención con una señal de capacidad o degradación **antes** de que el trabajo deje de funcionar, usando una carga pequeña y controlada. No llenes el disco principal ni provoques sobrecalentamiento.
- Si añades escenarios simulados, ejecútalos en un modo separado, con registros e interfaz claramente rotulados; nunca mezclados con telemetría real.
- Verifica el panel en móvil y escritorio, lecturas no disponibles, fallas del proveedor y ausencia del ESP32.
- No recopiles contraseñas, contenido de archivos, teclas, historial de navegación ni argumentos de procesos. Antes de convertir el panel local en uno accesible por red, añade autenticación por dispositivo y comunicaciones protegidas.

Entrega código, dependencias, configuración de ejemplo, pasos exactos de ejecución en Windows, documentación de sensores, pruebas realizadas y una demo de 3 minutos para jueces. Explica qué está implementado, qué es opcional y qué queda por probar físicamente. Presenta primero una versión funcionando y continúa hasta completar ese alcance.

---

El orden recomendado es: verificar la base → ejecutar la demo → probar en Windows → comprobar sensores disponibles → validar ESP32 → añadir servidor separado y varios equipos.
