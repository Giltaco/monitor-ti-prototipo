# Validación del prototipo — 9 de octubre de 2026

Entorno de prueba: Windows, Python 3.13, psutil 7.2.2. **13 pruebas aprobadas** con `.\.venv\Scripts\python.exe -m unittest discover -s tests -v`.

Se verificaron:

- Lecturas reales de CPU total/por núcleo/frecuencia, RAM, disco, red y procesos, sin ESP32 y sin datos inventados.
- Tasas de I/O por proceso cuando Windows concede acceso y clasificación explícita de interfaces.
- Serialización de los campos no disponibles como `null`.
- Tasas con dos lecturas válidas y manejo de reinicio de contadores.
- Persistencia temporal, histéresis y agrupación de un incidente.
- Datos desconocidos sin recuperación falsa.
- Historial suficiente para extrapolar espacio y ausencia de pronóstico con espacio estable.
- Configuración inválida rechazada.
- SQLite, reconocimiento y atención diferenciados de recuperación.
- Reinicio del monitor diferenciado de una solución.
- Prueba integrada de servidor HTTP local real: respuesta 200 → respuesta 503 → un incidente → reconocimiento → atención → respuesta 200 → recuperación confirmada.
- Ciclo manual real con `demo_service.py`: servicio detenido, un incidente en 6.3 s, acción registrada y recuperación del mismo ID en 21.3 s desde la primera señal.
- Demostración preventiva: servicio todavía disponible a 752.1 ms, cero fallos, advertencia sostenida y recuperación del mismo ID a 16.3 ms.
- Conservación del timestamp de la primera comprobación HTTP fallida.
- API sin lecturas recientes marcada como desconocida.
- Rechazo de una acción desde un origen externo.
- Panel renderizado a 390 px sin desbordamiento horizontal y a 1152 px con seis tarjetas y dos columnas de gráficas.

Pendiente en los equipos del concurso:

- Contrastar las cifras con Administrador de tareas/Monitor de recursos en el equipo de la demostración; distintas ventanas de muestreo pueden producir diferencias.
- Instalar y comprobar LibreHardwareMonitor oficial si el jurado requiere temperatura interna. En este equipo no se encontró su DLL, por lo que la lectura permaneció `null` con motivo visible.
- Compilar/cargar el sketch con el modelo real de ESP32 y comprobar GPIO, LEDs, puerto serial, latido y alimentación independiente.
- Instalar y autorizar `smartctl` oficial para la fase SMART/NVMe; no estaba disponible durante esta validación.

No se incluye historial de la computadora de desarrollo en el ZIP. La aplicación sólo observa el equipo donde se ejecute; no accede a la laptop del usuario desde esta conversación.
