# M8 Connect (v2.0) - Importación de Datos Empresarial

Sistema de ingesta, validación y promoción de datos con **wizard de 4 pasos**, autenticación JWT, catálogos y cola de jobs PostgreSQL.

## Características principales

- **Landing `/upload`**: Historia (`/upload/history`) o Catálogos (`/upload/catalog`)
- **Validación estricta** con rechazados exportables (TSV)
- **Archivos temp** (`_valid_records.parquet`) + promoción a producción
- **Workers** asíncronos (`PROCESS_FILE`, `PROMOTE_BATCH`)

## Requisitos

- Python 3.10+
- PostgreSQL 13+ (workers y job queue)
- Node.js 18+

## Instalación rápida

```bash
cd m8_connect
python -m venv venv
.\venv\Scripts\activate   # Windows
pip install -r requirements.txt
cp .env.example .env      # editar DATABASE_URL

alembic upgrade head      # tablas staging_meta + job_queue

cd frontend && npm install
```

## Ejecución (3 procesos)

```bash
python run_app.py       # API :8000
python run_workers.py   # cola de jobs
cd frontend && npm run dev   # UI :5173
```

## Documentación

| Documento | Contenido |
|-----------|-----------|
| [`docs/FUNCIONAMIENTO_APLICACION.md`](docs/FUNCIONAMIENTO_APLICACION.md) | **Doc canónica** — flujo completo |
| [`docs/MENU_CATALOGOS.md`](docs/MENU_CATALOGOS.md) | Catálogos y admin |
| [`docs/CONFIGURACION_POSTGRESQL_TUNEL.md`](docs/CONFIGURACION_POSTGRESQL_TUNEL.md) | Túnel Docker → PostgreSQL |
| [`MANUAL_DE_USO.md`](MANUAL_DE_USO.md) | Guía de usuario |
| [`INSTALL.md`](INSTALL.md) | Instalación detallada |
| Swagger | http://localhost:8000/docs |

## Flujo wizard (4 pasos)

1. **Upload** — subida y análisis del archivo
2. **Mapping** — mapeo columnas → destino
3. **Preview** — agregación Weekly/Monthly (historia) y muestra
4. **Process** — validación en worker + promoción a producción

## Setup BD

```bash
alembic upgrade head
```

Requiere `public.users` y tablas de negocio preexistentes para auth y FK (ver `INSTALL.md`).
