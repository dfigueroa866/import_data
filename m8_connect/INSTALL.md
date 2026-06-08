# Installation Guide - M8 Connect

## Quick install

```bash
cd m8_connect
make setup          # o: pip install -r requirements.txt && pip install -e .
cp .env.example .env
# Editar DATABASE_URL, SECRET_KEY

alembic upgrade head
python scripts/setup/seed_data.py   # opcional: data_sources demo
```

## Run the system

Three terminals:

```bash
python run_app.py
python run_workers.py
cd frontend && npm run dev
```

## Database migrations (canonical)

```bash
alembic upgrade head
```

Creates `staging_meta.*` (including `batch_control`, `job_queue`) and `staging_data.template_staging`.

**Not managed by Alembic** (must exist in your business DB):

- `public.users`, `public.organizations` — authentication
- `public.skus`, `public.locations`, `public.sales_history` — production targets

Legacy manual SQL in `migrations/*.sql` is superseded by Alembic revision `002_job_queue_and_indexes`.

## Platform notes

### Windows

```powershell
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
pip install -e .
```

### macOS / Linux

```bash
make setup
# or
pip3 install -r requirements.txt && pip3 install -e .
```

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `relation staging_meta.batch_control does not exist` | `alembic upgrade head` |
| Workers idle, jobs stuck | Check `staging_meta.job_queue`; ensure `run_workers.py` running |
| Login fails | Verify `public.users` exists and password hash is bcrypt |
| Import errors | Set `PYTHONPATH=src` or run from project root via `run_app.py` |

## Docs

- [`docs/FUNCIONAMIENTO_APLICACION.md`](docs/FUNCIONAMIENTO_APLICACION.md) — architecture and flows
- [`docs/CONFIGURACION_POSTGRESQL_TUNEL.md`](docs/CONFIGURACION_POSTGRESQL_TUNEL.md) — remote DB tunnel
