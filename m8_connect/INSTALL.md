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

Creates `staging_meta.*` (including `batch_control`, `job_queue`) and M8 Connect RBAC objects in `m8_schema` (`connect_role`, `connect_user_roles`, `loader_profile`).

**Not managed by Alembic** (must exist in your business DB):

- `public.users`, `public.organizations` — authentication
- `public.skus`, `public.locations`, `public.sales_history` — production targets

SQL en `migrations/*.sql` superseded by Alembic revisions `002_job_queue_and_indexes` and `003_connect_roles`.

## Roles M8 Connect

RBAC de aplicación (solo M8 Connect):

- `admin_m8_connect`
- `loader`

Estas asignaciones viven en `m8_schema.connect_user_roles` y **no modifican** `public."UserRole"`.

Bootstrap de admin inicial:

- La migración `003_connect_roles` intenta asignar `admin_m8_connect` a `david.figueroa@m8solutions.com.mx` si ese usuario existe en `public.users`.
- Si el usuario aún no existe, puede asignarse después manualmente:

```sql
INSERT INTO m8_schema.connect_user_roles (user_id, role, granted_at)
SELECT id, 'admin_m8_connect'::m8_schema.connect_role, now()
FROM public.users
WHERE LOWER(email::text) = LOWER('david.figueroa@m8solutions.com.mx')
ON CONFLICT (user_id) DO UPDATE SET role = EXCLUDED.role;
```

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
