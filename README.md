# M8 Connect — repositorio

Sistema de ingesta en [`m8_connect/`](m8_connect/).

## Inicio rápido

Ver [`m8_connect/README.md`](m8_connect/README.md) y [`m8_connect/docs/FUNCIONAMIENTO_APLICACION.md`](m8_connect/docs/FUNCIONAMIENTO_APLICACION.md).

```bash
cd m8_connect
pip install -r requirements.txt
cp .env.example .env
alembic upgrade head
python run_app.py          # terminal 1
python run_workers.py      # terminal 2
cd frontend && npm run dev # terminal 3
```

## Túnel PostgreSQL (Docker)

[`m8_connect/docs/CONFIGURACION_POSTGRESQL_TUNEL.md`](m8_connect/docs/CONFIGURACION_POSTGRESQL_TUNEL.md)

