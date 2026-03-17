# QR Tracker personal

App sencilla en Flask para generar códigos QR privados y medir clics.

## Qué hace

- Crea enlaces cortos para una URL destino.
- Genera imagen QR (`/qr/<codigo>.png`) para cada enlace.
- Registra cada clic cuando se abre el enlace corto (`/r/<codigo>`).
- Muestra métricas por enlace:
  - Total de clics.
  - Clics por hora (UTC).
  - Últimos clics con IP, referer y user-agent.

## Ejecutar localmente

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Abrir: `http://localhost:5000`

## Notas

- La base de datos SQLite se guarda en `qr_tracker.db`.
- Si está detrás de proxy reverso, configura cabeceras para capturar IP real (`X-Forwarded-For`).
