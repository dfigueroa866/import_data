# M8 Connect (v2.0) — Importación de Datos Empresarial

Sistema de ingesta, validación y promoción de datos con **wizard de 4 pasos**, autenticación JWT, **roles y permisos por aplicación**, catálogos y cola de jobs PostgreSQL.

El código de la aplicación vive en [`m8_connect/`](m8_connect/).

## Características principales

- **Landing `/upload`**: Historia (`/upload/history`) o Catálogos (`/upload/catalog`)
- **RBAC M8 Connect**: roles `admin_m8_connect` y `loader`, aislados de `public."UserRole"`
- **Menú Roles** (`/config/roles`): asignación de perfiles y matriz global del loader
- **Configuración**: catálogos (`/config/catalogs`), historia (`/config/history`)
- **Validación estricta** con rechazados exportables (TSV)
- **Archivos temp** (`_valid_records.parquet`) + promoción a producción
- **Workers** asíncronos (`PROCESS_FILE`, `PROMOTE_BATCH`)

## Roles M8 Connect

Los permisos de la UI y del API de M8 Connect **no dependen** del rol de plataforma (`admin`, `manager`, `planner`, `viewer` en `public.users`). Se resuelven con roles propios en `m8_schema`:

| Rol | Alcance |
|-----|---------|
| `admin_m8_connect` | Acceso total: menús, configuración, asignación de roles |
| `loader` | Acceso según matriz global en `m8_schema.loader_profile` |

Reglas:

- Sin fila en `m8_schema.connect_user_roles` → el usuario se trata como **loader** por defecto.
- La migración `005_bootstrap_admin_user` crea el usuario bootstrap
  `david.figueroa@m8solutions.com.mx` (pwd `Admin123`) con rol `admin_m8_connect`.
  Cambia la contraseña tras el primer login en entornos compartidos.

Detalle de instalación y SQL de bootstrap: [`m8_connect/INSTALL.md`](m8_connect/INSTALL.md#roles-m8-connect).

## Requisitos

- Python 3.10+
- PostgreSQL 13+ (workers y job queue)
- Node.js 18+

## Inicio rápido

```bash
cd m8_connect
python -m venv venv
.\venv\Scripts\activate   # Windows; en Linux/macOS: source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # editar DATABASE_URL, SECRET_KEY

alembic upgrade head
cd frontend && npm install
```

Ejecutar **4 procesos** en terminales separadas (carga incremental opcional):

```bash
python run_app.py              # API :8000
python run_workers.py          # cola de jobs wizard
cd ../m8_incremental && python run_workers.py    # workers incremental (opcional)
cd ../m8_incremental && python run_scheduler.py # scheduler domingo 22:00 (opcional)
cd frontend && npm run dev       # UI :5173
```

Carga incremental automatizada: instalar `pip install -e ../m8_incremental` y `alembic upgrade head` (migración `004_incremental_tables`). Configuración en menú **Incremental** (`/incremental`).

Instalación detallada, migraciones y troubleshooting: [`m8_connect/INSTALL.md`](m8_connect/INSTALL.md).

## Flujo wizard (4 pasos)

1. **Upload** — subida y análisis del archivo
2. **Mapping** — mapeo columnas → destino
3. **Preview** — agregación Weekly/Monthly (historia) o vista previa (catálogos)
4. **Process** — validación en worker + promoción a producción

Guía de usuario: [`m8_connect/MANUAL_DE_USO.md`](m8_connect/MANUAL_DE_USO.md).

## Navegación (UI)

| Ruta | Descripción | Permiso típico |
|------|-------------|----------------|
| `/` | Panel | `menus.panel` |
| `/upload` | Elegir tipo de carga | `menus.upload` |
| `/upload/history`, `/upload/catalog` | Wizards de carga | `upload.history` / `upload.catalogs` |
| `/batches` | Historial de cargas | `menus.batches` |
| `/monitoring` | Salud del sistema | `menus.monitoring` |
| `/incremental` | Cargas automáticas semanales/mensuales | `menus.incremental` |
| `/incremental/schedule` | Cron y retención | admin o `config.incremental_view` |
| `/incremental/organizations` | Rutas y tablas por org | admin o `config.incremental_view` |
| `/incremental/runs` | Historial de ejecuciones | `menus.incremental` |
| `/config/catalogs` | Admin catálogos | admin o `config.catalogs_view` |
| `/config/history` | Admin historia | admin o `config.history_view` |
| `/config/roles` | Roles y perfil loader | solo `admin_m8_connect` |

`admin_m8_connect` omite estas restricciones. Ver [`MANUAL_DE_USO.md`](m8_connect/MANUAL_DE_USO.md#configuración-y-permisos).

## Documentación

| Documento | Contenido |
|-----------|-----------|
| [`m8_connect/INSTALL.md`](m8_connect/INSTALL.md) | Instalación detallada, migraciones, troubleshooting |
| [`m8_connect/MANUAL_DE_USO.md`](m8_connect/MANUAL_DE_USO.md) | Guía de usuario (UI y wizard) |
| [`m8_connect/docs/FUNCIONAMIENTO_APLICACION.md`](m8_connect/docs/FUNCIONAMIENTO_APLICACION.md) | **Doc técnica canónica** — arquitectura, API, workers, RBAC |
| [`m8_connect/docs/MENU_CATALOGOS.md`](m8_connect/docs/MENU_CATALOGOS.md) | Admin catálogos y wizard de catálogos |
| [`m8_connect/docs/CONFIGURACION_POSTGRESQL_TUNEL.md`](m8_connect/docs/CONFIGURACION_POSTGRESQL_TUNEL.md) | Túnel Docker → PostgreSQL remoto |
| Swagger (API en ejecución) | http://localhost:8000/docs |

## Base de datos

```bash
cd m8_connect
alembic upgrade head
```

Crea objetos de staging (`staging_meta`, `staging_data`), RBAC de app en `m8_schema`
(`connect_user_roles`, `loader_profile`) y el usuario bootstrap admin
(`005_bootstrap_admin_user`).

Requiere `public.users` y tablas de negocio preexistentes para auth y FK (ver [`INSTALL.md`](m8_connect/INSTALL.md)).

## Túnel PostgreSQL (Docker)

Para conectar a PostgreSQL en un servidor remoto vía SSH: [`m8_connect/docs/CONFIGURACION_POSTGRESQL_TUNEL.md`](m8_connect/docs/CONFIGURACION_POSTGRESQL_TUNEL.md).
