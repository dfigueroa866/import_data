# Configuración: PostgreSQL en Ubuntu vía túnel Docker

Este documento describe cómo conectar **M8 Connect** a una base de datos **PostgreSQL** instalada en un **servidor Ubuntu**, accediendo desde tu máquina de desarrollo (Windows) mediante un **túnel SSH en Docker**.

---

## 1. Arquitectura

```
┌─────────────────────┐     SSH      ┌──────────────────────┐
│  Tu PC (Windows)    │ ───────────► │  Servidor Ubuntu     │
│                     │              │                      │
│  App (FastAPI)     │              │  PostgreSQL :5432    │
│       │            │              │  (localhost en VPS)  │
│       ▼            │              └──────────────────────┘
│  127.0.0.1:5433    │
│       ▲            │
│  Docker tunnel     │
│  (puerto publicado)│
└─────────────────────┘
```

La aplicación **solo** habla con `127.0.0.1` y el puerto local del túnel (por ejemplo `5433`). No necesita exponer PostgreSQL a Internet.

---

## 2. Requisitos en el servidor Ubuntu

### 2.1 PostgreSQL instalado y escuchando

```bash
sudo apt update
sudo apt install -y postgresql postgresql-contrib
sudo systemctl enable postgresql
sudo systemctl start postgresql
```

Verificar:

```bash
sudo -u postgres psql -c "SELECT version();"
```

### 2.2 Usuario y base de datos para el proyecto

En el servidor (como `postgres` o con `sudo -u postgres psql`):

```sql
CREATE USER staging_user WITH PASSWORD 'tu_password_seguro';
CREATE DATABASE staging_db OWNER staging_user;
GRANT ALL PRIVILEGES ON DATABASE staging_db TO staging_user;

-- Conectar a staging_db para extensiones y esquemas
\c staging_db
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
```

### 2.3 Acceso SSH

- Tu clave pública debe estar en `~/.ssh/authorized_keys` del usuario SSH (ej. `ubuntu`).
- PostgreSQL suele escuchar solo en `127.0.0.1` en el VPS; el túnel SSH reenvía ese puerto a tu PC.

### 2.4 `pg_hba.conf` (si la app corre en el mismo servidor)

Si más adelante ejecutas la API **en el Ubuntu** sin túnel, ajusta `pg_hba.conf`. Para túnel SSH, basta con que Postgres acepte conexiones locales en el VPS.

---

## 3. Túnel Docker (recomendado en este repo)

### 3.1 Configurar variables del túnel

```powershell
cd m8_connect\docker
copy .env.tunnel.example .env.tunnel
# Editar .env.tunnel con SSH_HOST, SSH_USER, SSH_KEY_PATH, LOCAL_TUNNEL_PORT
```

| Variable | Descripción |
|----------|-------------|
| `SSH_HOST` | IP o hostname del Ubuntu |
| `SSH_USER` | Usuario SSH (ej. `ubuntu`) |
| `SSH_KEY_PATH` | Ruta a clave privada (en Windows puede ser `C:\Users\...\.ssh\id_rsa`) |
| `REMOTE_PG_HOST` | Casi siempre `127.0.0.1` (Postgres en el mismo VPS) |
| `REMOTE_PG_PORT` | `5432` |
| `LOCAL_TUNNEL_PORT` | Puerto en tu PC, ej. `5433` (evita choque con Postgres local) |

### 3.2 Levantar el túnel

Desde `m8_connect`:

```powershell
docker compose -f docker/docker-compose.tunnel.yml --env-file docker/.env.tunnel up -d
docker logs -f data-staging-pg-tunnel
```

Debe mostrar que el túnel está activo. Probar:

```powershell
# Requiere psql en PATH o usar pgAdmin contra 127.0.0.1:5433
psql "postgresql://staging_user:tu_password@127.0.0.1:5433/staging_db" -c "SELECT 1"
```

### 3.3 Detener el túnel

```powershell
docker compose -f docker/docker-compose.tunnel.yml --env-file docker/.env.tunnel down
```

---

## 4. Alternativa: túnel SSH sin Docker

Si ya tienes un contenedor o script propio:

```powershell
ssh -N -L 5433:127.0.0.1:5432 ubuntu@TU_SERVIDOR
```

Misma idea: la app usa `127.0.0.1:5433`.

---

## 5. Configurar la aplicación (`.env`)

En `m8_connect/.env`:

```ini
ENVIRONMENT=development
DEBUG=true

# PostgreSQL vía túnel
DATABASE_URL=postgresql://staging_user:tu_password@127.0.0.1:5433/staging_db
DATABASE_TYPE=postgresql

# Importante para túnel local
SSL_REQUIRE=false
SSL_MODE=prefer
```

**Notas:**

- El puerto en `DATABASE_URL` debe coincidir con `LOCAL_TUNNEL_PORT`.
- Si la contraseña tiene caracteres especiales (`@`, `#`, `%`), codifícala en URL ([percent-encoding](https://en.wikipedia.org/wiki/Percent-encoding)).
- `DATABASE_TYPE=postgresql` evita detección errónea; ClickHouse y Supabase quedan desactivados.

Plantilla sin secretos: `.env.example`.

---

## 6. Inicializar esquema en la nueva base

Con el túnel **activo** y `.env` apuntando a PostgreSQL:

```powershell
cd m8_connect
.\venv\Scripts\activate
pip install -r requirements.txt

# 1) Crear BD si no existe (opcional)
python scripts/setup/init_database.py

# 2) Migraciones Alembic (staging_meta, job_queue, índices — revisión 002)
alembic upgrade head
```

Ya **no** hace falta ejecutar manualmente `migrations/create_job_queue.sql` en instalaciones nuevas (incluido en Alembic 002).

### Verificación rápida

```powershell
python run_app.py
```

En otra terminal:

```powershell
python run_workers.py
```

Abrir `http://localhost:8000/health` — debe indicar `"database": { "status": "connected", "type": "postgresql" }`.

---

## 7. Cambios respecto a ClickHouse / Supabase

| Aspecto | ClickHouse (antes) | PostgreSQL + túnel (ahora) |
|---------|-------------------|----------------------------|
| `DATABASE_URL` | `clickhouse://...` | `postgresql://...@127.0.0.1:PUERTO/...` |
| Workers `job_queue` | No compatible (usa SQL PG) | Compatible vía `alembic upgrade head` |
| `LISTEN/NOTIFY` | N/A | Disponible (workers usan polling por defecto) |
| Esquemas | `databases` CH | `staging_meta`, `staging_data`, producción (`m8_schema`, etc.) |
| Validación FK en worker | Limitada | Completa vía `information_schema` |
| SSL | HTTPS a cloud | `SSL_REQUIRE=false` en túnel local |

El código detecta PostgreSQL automáticamente si la URL empieza por `postgresql://` o `postgres://`.

---

## 8. Orden de arranque diario

1. Levantar túnel Docker (o SSH `-L`).
2. Comprobar conexión (`psql` o `/health`).
3. `python run_workers.py`
4. `python run_app.py`
5. Frontend: `cd frontend && npm run dev`

Si la API arranca **sin** túnel, verás error de conexión en logs y `/health` en `unhealthy`.

---

## 9. Producción en el mismo Ubuntu (sin túnel)

Si la API y los workers corren **en el servidor Ubuntu** junto a PostgreSQL:

```ini
DATABASE_URL=postgresql://staging_user:pass@127.0.0.1:5432/staging_db
DATABASE_TYPE=postgresql
SSL_REQUIRE=false
```

No hace falta Docker tunnel en ese caso.

---

## 10. Solución de problemas

| Síntoma | Causa probable | Acción |
|---------|----------------|--------|
| `Connection refused` en 5433 | Túnel no levantado | `docker logs data-staging-pg-tunnel` |
| `password authentication failed` | Usuario/clave distintos en VPS vs `.env` | Revisar `CREATE USER` y URL |
| `database "staging_db" does not exist` | BD no creada | `init_database.py` o `CREATE DATABASE` |
| `relation staging_meta.batch_control does not exist` | Sin migraciones | `alembic upgrade head` |
| Workers no procesan jobs | Falta `job_queue` | `alembic upgrade head` (incluye job_queue) |
| `SSL connection required` | SSL activo hacia localhost | `SSL_REQUIRE=false` en `.env` |
| Permisos SSH | Clave incorrecta o `chmod` | `chmod 600` en clave; probar `ssh ubuntu@host` |

---

## 11. Seguridad

- No subas `.env` ni `docker/.env.tunnel` al repositorio (deben estar en `.gitignore`).
- Rota contraseñas de `staging_user` periódicamente.
- En producción, usa `SECRET_KEY` fuerte y restringe CORS en `api/main.py`.
- El túnel SSH es preferible a abrir el puerto 5432 de PostgreSQL al público.

---

*Relacionado: [FUNCIONAMIENTO_APLICACION.md](./FUNCIONAMIENTO_APLICACION.md), [ANALISIS_CODIGO.md](./ANALISIS_CODIGO.md)*
