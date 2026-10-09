# Demo de 3 minutos para jueces

## Preparación

Abre dos PowerShell en la carpeta del proyecto. En una ejecuta `.\.venv\Scripts\python.exe tools\demo_service.py`; en otra, `.\.venv\Scripts\python.exe -m monitor_ti --config config\config.demo.json`. Abre `http://127.0.0.1:8875`.

## Guion

**0:00–0:35 — Evidencia real.** Muestra CPU, RAM, disco, red, procesos e I/O. Señala `—` y el motivo si la temperatura no está disponible. Explica que no hay nube ni datos inventados.

**0:35–1:10 — Prevención.** Si preparaste el perfil de latencia, ejecuta el servicio con `--delay-ms 750` y `config.degradation-demo.json`. Enseña que el servicio aún responde, pero la degradación sostenida genera una advertencia. No se llena el disco ni se sobrecalienta el equipo.

**1:10–2:15 — Antes de la llamada.** Con `config/config.demo.json`, detén `tools/demo_service.py`. Tras tres pruebas fallidas aparece un solo incidente con primera señal, detección, evidencia y recomendación. Reconócelo y registra «Reiniciar el servicio de demostración»; aclara que eso todavía no es una reparación.

**2:15–2:45 — Resultado verificable.** Inicia de nuevo `tools/demo_service.py`. El mismo incidente pasa a recuperado sólo cuando la métrica vuelve al rango saludable. Muestra los tiempos de detección, atención y recuperación.

**2:45–3:00 — ESP32 y siguiente fase.** Explica que el ESP32 opcional muestra estado y pérdida de latido con alimentación independiente; no lee RAM ni procesos. La siguiente fase separa agente por PC, servidor en otra PC y sensor ambiental externo.

## Frase de cierre

«No sólo registramos que alguien atendió: comprobamos con la misma señal que el servicio se recuperó, antes de esperar la llamada del usuario».
