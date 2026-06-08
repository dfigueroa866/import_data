# M8 Connect — repositorio

Sistema de ingesta en [`data-staging-system/`](data-staging-system/).

## Inicio rápido

Ver [`data-staging-system/README.md`](data-staging-system/README.md) y [`data-staging-system/docs/FUNCIONAMIENTO_APLICACION.md`](data-staging-system/docs/FUNCIONAMIENTO_APLICACION.md).

```bash
cd data-staging-system
pip install -r requirements.txt
cp .env.example .env
alembic upgrade head
python run_app.py          # terminal 1
python run_workers.py      # terminal 2
cd frontend && npm run dev # terminal 3
```

## Túnel PostgreSQL (Docker)

[`data-staging-system/docs/CONFIGURACION_POSTGRESQL_TUNEL.md`](data-staging-system/docs/CONFIGURACION_POSTGRESQL_TUNEL.md)
