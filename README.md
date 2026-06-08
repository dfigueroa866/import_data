# M8 Connect (v2.0) — Importación de Datos Empresarial

Sistema de ingesta, validación y promoción de datos con **wizard de 4 pasos**, autenticación JWT, catálogos y cola de jobs PostgreSQL.

El código de la aplicación vive en [`m8_connect/`](m8_connect/).

## Características principales

- **Landing `/upload`**: Historia (`/upload/history`) o Catálogos (`/upload/catalog`)
- **Validación estricta** con rechazados exportables (TSV)
- **Archivos temp** (`_valid_records.parquet`) + promoción a producción
- **Workers** asíncronos (`PROCESS_FILE`, `PROMOTE_BATCH`)

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

Ejecutar **3 procesos** en terminales separadas:

```bash
python run_app.py         # API :8000
python run_workers.py     # cola de jobs
cd frontend && npm run dev   # UI :5173
```

Instalación detallada, migraciones y troubleshooting: [`m8_connect/INSTALL.md`](m8_connect/INSTALL.md).

## Flujo wizard (4 pasos)

1. **Upload** — subida y análisis del archivo
2. **Mapping** — mapeo columnas → destino
3. **Preview** — agregación Weekly/Monthly (historia) o vista previa (catálogos)
4. **Process** — validación en worker + promoción a producción

Guía de usuario: [`m8_connect/MANUAL_DE_USO.md`](m8_connect/MANUAL_DE_USO.md).

## Documentación

| Documento | Contenido |
|-----------|-----------|
| [`m8_connect/INSTALL.md`](m8_connect/INSTALL.md) | Instalación detallada, migraciones, troubleshooting |
| [`m8_connect/MANUAL_DE_USO.md`](m8_connect/MANUAL_DE_USO.md) | Guía de usuario (UI y wizard) |
| [`m8_connect/docs/FUNCIONAMIENTO_APLICACION.md`](m8_connect/docs/FUNCIONAMIENTO_APLICACION.md) | **Doc técnica canónica** — arquitectura, API, workers |
| [`m8_connect/docs/MENU_CATALOGOS.md`](m8_connect/docs/MENU_CATALOGOS.md) | Admin catálogos y wizard de catálogos |
| [`m8_connect/docs/CONFIGURACION_POSTGRESQL_TUNEL.md`](m8_connect/docs/CONFIGURACION_POSTGRESQL_TUNEL.md) | Túnel Docker → PostgreSQL remoto |
| Swagger (API en ejecución) | http://localhost:8000/docs |

## Base de datos

```bash
cd m8_connect
alembic upgrade head
```

Requiere `public.users` y tablas de negocio preexistentes para auth y FK (ver [`INSTALL.md`](m8_connect/INSTALL.md)).

## Túnel PostgreSQL (Docker)

Para conectar a PostgreSQL en un servidor remoto vía SSH: [`m8_connect/docs/CONFIGURACION_POSTGRESQL_TUNEL.md`](m8_connect/docs/CONFIGURACION_POSTGRESQL_TUNEL.md).
