# Contribuir

1. Usa Python 3.10 o posterior y crea un entorno virtual.
2. Instala el proyecto editable: `python -m pip install -e .`.
3. Ejecuta `python -m unittest discover -s tests -v` antes de proponer cambios.
4. Conserva `null` y el motivo cuando una métrica no esté disponible; no inventes lecturas.
5. Añade pruebas para reglas, transiciones de incidentes y proveedores nuevos.

No incluyas bases SQLite, identificadores locales, credenciales, argumentos de procesos ni contenido de archivos.
