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

Ver [Inicio rápido](../README.md#inicio-rápido) en el README raíz.

## Database migrations (canonical)

```bash
alembic upgrade head
```

Creates `staging_meta.*` (including `batch_control`, `job_queue`, `incremental_*`) and M8 Connect RBAC objects in `m8_schema` (`connect_role`, `connect_user_roles`, `loader_profile`).

## Carga incremental (`m8_incremental`)

Servicio independiente en `../m8_incremental/`:

```bash
pip install -e .
pip install -e ../m8_incremental
pip install apscheduler
cp ../m8_incremental/.env.example ../m8_incremental/.env
```

Procesos adicionales (desde `m8_incremental/`):

```bash
python run_workers.py      # RUN_INCREMENTAL_LOAD
python run_scheduler.py    # cron configurable vía UI /incremental/schedule
```

Archivos de prueba locales: `Data_Examples/Incremental/<organizacion>/catalogos|historia/`.

**Not managed by Alembic** (must exist in your business DB):

- `public.users`, `public.organizations` — authentication
- `public.skus`, `public.locations`, `public.sales_history` — production targets

## Roles M8 Connect

RBAC de aplicación (solo M8 Connect):

- `admin_m8_connect`
- `loader`

Estas asignaciones viven en `m8_schema.connect_user_roles` y **no modifican** `public."UserRole"`.

Bootstrap de admin inicial:

- La migración `005_bootstrap_admin_user` crea (o actualiza) el usuario
  `david.figueroa@m8solutions.com.mx` / `Admin123`, asegura la organización
  `M8 Solutions` y asigna `admin_m8_connect`.
- La migración `003_connect_roles` también intenta asignar el rol si el usuario
  ya existía antes de `005`.
- Cambia la contraseña tras el primer login en entornos compartidos o producción.

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
| CORS errors in production | Configure explicit origins in `src/data_staging/api/main.py` (avoid `allow_origins=["*"]` with credentials) |

## Docs

- [README raíz](../README.md) — overview e inicio rápido
- [`docs/FUNCIONAMIENTO_APLICACION.md`](docs/FUNCIONAMIENTO_APLICACION.md) — architecture and flows
- [`docs/CONFIGURACION_POSTGRESQL_TUNEL.md`](docs/CONFIGURACION_POSTGRESQL_TUNEL.md) — remote DB tunnel
