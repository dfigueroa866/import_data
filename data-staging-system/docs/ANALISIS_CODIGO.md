# Análisis de código — M8 Connect

**Fecha del análisis:** 27 de mayo de 2026  
**Actualización limpieza:** junio 2026  
**Rama revisada:** MVP2  
**Alcance:** Backend Python (`src/data_staging`), workers, API FastAPI, frontend React (referencia), configuración y migraciones.

### Limpieza aplicada (jun 2026)

| Item | Estado |
|------|--------|
| `process_file_async`, router `/api/v1/staging/*` | Eliminados |
| `Staging.jsx`, `stagingService.js`, `Upload.jsx` huérfanos | Eliminados |
| `create_staging_table` / `insert_records_in_batches` | Eliminados |
| Job queue en Alembic `002_job_queue_and_indexes` | Consolidado |
| Doc canónica | `docs/FUNCIONAMIENTO_APLICACION.md` |

Pendiente backlog: optimización cargas >20M (ver plan separado).

---

## 1. Resumen ejecutivo

El repositorio implementa un **sistema de ingesta, validación y promoción de datos** orientado a archivos CSV/Excel hacia PostgreSQL, Supabase o ClickHouse. La arquitectura principal es sólida: API FastAPI + cola de trabajos en PostgreSQL + workers en segundo plano + wizard React de 4 pasos.

Los riesgos más urgentes son **bugs de runtime** en endpoints de la API, **inconsistencias de configuración** entre entornos, **seguridad CORS** abierta en producción y **múltiples caminos de procesamiento** (legacy vs. actual) que pueden confundir el comportamiento real del sistema.

---

## 2. Arquitectura general

### 2.1 Componentes en ejecución

| Proceso | Comando | Puerto / rol |
|---------|---------|----------------|
| API Backend | `python run_app.py` | `http://localhost:8000` |
| Workers | `python run_workers.py` | Sin HTTP; consume `staging_meta.job_queue` |
| Frontend | `cd frontend && npm run dev` | `http://localhost:5173` (Vite) |

### 2.2 Stack tecnológico

| Capa | Tecnología |
|------|------------|
| API | FastAPI, Uvicorn, Pydantic v2 |
| ORM / DB | SQLAlchemy 2.x, psycopg2 |
| Procesamiento de datos | Polars, NumPy |
| Cola de jobs | PostgreSQL (`staging_meta.job_queue`) + opcional LISTEN/NOTIFY |
| Frontend | React, React Router, Vite |
| Migraciones | Alembic |
| Bases soportadas | PostgreSQL, Supabase (PostgreSQL), ClickHouse |

### 2.3 Estructura de directorios relevante

```
data-staging-system/
├── src/data_staging/
│   ├── api/              # FastAPI (main, v1/upload, routers)
│   ├── workers/          # file_processor, promotion_worker, job_queue
│   ├── core/             # validators, ETL engine
│   ├── models/           # SQLAlchemy (batch, validation, load_history)
│   ├── services/         # aggregation_service
│   ├── config.py         # Settings centralizadas
│   └── database.py       # DatabaseManager (pool, SSL, eventos)
├── frontend/src/         # Wizard y páginas
├── alembic/              # Migraciones de esquema
├── migrations/           # SQL adicional (job_queue, índices)
├── run_app.py            # Arranque API con checks
└── run_workers.py        # Arranque workers (actualmente 1 worker)
```

### 2.4 Esquemas de base de datos

| Esquema | Propósito |
|---------|-----------|
| `staging_meta` | Metadatos: `batch_control`, `job_queue`, `data_sources`, `load_history`, `validation_logs` |
| `staging_data` | Tablas dinámicas `stage_{source_name}` (legacy) y plantilla `template_staging` |
| `m8_schema` / `public` | Esquemas de producción típicos (configurables) |

El `search_path` en conexiones PostgreSQL se fija a:  
`staging_meta, staging_data, m8_schema, public`.

---

## 3. Hallazgos por severidad

### 3.1 Críticos (rompen funcionalidad en runtime)

#### C-01: `delete_batch` sin importar `BatchControl`

**Archivo:** `src/data_staging/api/v1/upload.py` (aprox. líneas 1459–1488)

El endpoint `DELETE /api/v1/upload/batch/{batch_id}` usa:

```python
batch = db.query(BatchControl).filter(BatchControl.batch_id == batch_id).first()
```

`BatchControl` **no está importado** en ese archivo. Al invocar el endpoint desde el wizard (`wizardService.deleteBatch`) o desde la UI, se producirá:

```
NameError: name 'BatchControl' is not defined
```

**Impacto:** El botón "Start Over" / limpieza de batch en Step 4 falla.

**Corrección sugerida:** Añadir `from data_staging.models.batch import BatchControl` o reescribir el endpoint con SQL crudo como el resto del archivo.

---

#### C-02: Atributo incorrecto `settings.upload_path`

**Archivo:** `src/data_staging/api/v1/upload.py` — función `process_batch` (aprox. línea 531)

```python
file_path = str(settings.upload_path / f"{batch_id}_{batch.file_name}")
```

En `config.py` el campo definido es `UPLOAD_PATH` (Pydantic genera `settings.UPLOAD_PATH`, no `upload_path` en minúsculas).

**Impacto:** Si `file_path` no está en metadata y el fallback se ejecuta, `AttributeError` al procesar el batch.

**Corrección sugerida:** Usar `Path(settings.UPLOAD_PATH)` de forma consistente.

---

#### C-03: Desalineación modelo ORM vs. uso en API

**Archivo:** `src/data_staging/models/batch.py` vs. SQL en `upload.py`

| En migración / SQL API | En modelo SQLAlchemy |
|------------------------|----------------------|
| Columna `metadata` (JSONB) | `batch_metadata` |
| Status como string libre (`PENDING_MAPPING`, `PROMOTED`, etc.) | Enum `BatchStatus` limitado (sin `PROMOTED`, `PARTIALLY_PROMOTED`, etc.) |

La API escribe y lee `metadata` y estados extendidos vía SQL directo; el modelo ORM no refleja el esquema real. Esto explica por qué `delete_batch` con ORM es frágil además del import faltante.

---

### 3.2 Altos (seguridad, configuración, integridad)

#### A-01: CORS permisivo con credenciales

**Archivo:** `src/data_staging/api/main.py`

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    ...
)
```

Combinar `allow_origins=["*"]` con `allow_credentials=True` es **incorrecto según especificación CORS** y expone la API si se despliega sin restricción de origen.

**Recomendación:** Lista explícita de orígenes (ej. `http://localhost:5173`) y `allow_credentials` solo si es necesario.

---

#### A-02: `SECRET_KEY` por defecto en desarrollo

**Archivo:** `src/data_staging/config.py`

Valor por defecto: `"development-secret-key-must-be-at-least-32-characters-long"`.

Si en producción no se sobrescribe vía `.env`, cualquier despliegue queda comprometido ante uso futuro de JWT/tokens.

---

#### A-03: Inconsistencia del enum `Environment`

**Archivo:** `src/data_staging/config.py`

```python
class Environment(str, Enum):
  ...
  PRODUCTION = "m8_schema"   # Valor confunde schema con entorno

def get_settings():
    env = os.getenv("ENVIRONMENT", "development").lower()
    if env == "public":
        return ProductionSettings()
```

- `is_production` compara con `Environment.PRODUCTION` cuyo **valor** es `"m8_schema"`, no `"production"`.
- `get_settings()` activa producción cuando `ENVIRONMENT=public`, no cuando es `m8_schema` ni `production`.

**Impacto:** Flags como `DEBUG`, alertas por email y lógica condicional por entorno pueden activarse mal.

---

#### A-04: SQL dinámico en validación de FK

**Archivo:** `src/data_staging/workers/file_processor.py` (aprox. líneas 297–299)

```python
cursor.execute(f"SELECT DISTINCT {f_col} FROM {f_schema}.{f_table} WHERE {f_col} IS NOT NULL")
```

`f_schema`, `f_table` y `f_col` provienen de `information_schema` (menor riesgo que input de usuario), pero el patrón f-string para SQL es peligroso si en el futuro se relajan las fuentes.

---

#### A-05: Sin autenticación en la API

No hay middleware de auth, API keys ni JWT en los endpoints revisados. Cualquier cliente con acceso de red puede subir archivos, promover batches y borrar datos.

---

### 3.3 Medios (mantenibilidad, rendimiento, consistencia)

#### M-01: Múltiples flujos de procesamiento coexistiendo

| Flujo | Entrada | Mecanismo |
|-------|---------|-----------|
| **Wizard (actual)** | `/file-temp` → mapping → preview → `/process` | Job `PROCESS_FILE` + archivos temp en disco |
| **Upload directo** | `POST /file` | Job `PROCESS_FILE` inmediato |
| **Legacy async** | `process_file_async` en `upload.py` | BackgroundTasks / lectura con FileHandler (no encola job completo) |
| **Staging router** | `/staging/process-to-production` | Background task distinto a `promotion_worker` |

La documentación antigua (`system_import_flow_guide.md`) describe COPY a tablas `staging_data.stage_*`; el código actual del worker **prioriza archivos CSV temporales** (`valid_temp_file`) y puede omitir staging en BD.

---

#### M-02: Carga CSV completa en memoria

**Archivo:** `file_processor.py` — `process_file_in_chunks`

Aunque el nombre sugiiere streaming, para CSV hace:

```python
full_df = pl.read_csv(file_path, ...)
for start_idx in range(0, total_rows, CHUNK_SIZE_RECORDS):
    chunk_df = full_df.slice(...)
```

`CHUNK_SIZE_RECORDS = 1_000_000`. Archivos grandes cargan **todo el DataFrame en RAM** antes de trocear.

---

#### M-03: Deduplicación deshabilitada en promoción

**Archivo:** `promotion_worker.py`

Aunque el wizard guarda `dedup_columns`, el worker registra que la verificación de duplicados se **omite por rendimiento**; la deduplicación depende de constraints en BD al insertar.

---

#### M-04: `except:` desnudos

Ubicaciones detectadas:

- `upload.py`: análisis JSON/CSV (líneas ~222, ~265)
- `promotion_worker.py`: manejo de error final (~343)
- `staging.py`, `file_handler.py`

Ocultan `KeyboardInterrupt`, errores de red y bugs reales.

---

#### M-05: Cola de jobs: conexión por operación

**Archivo:** `job_queue.py`

Cada `_fetch_next_job`, `_complete_job`, `_fail_job` y `create_job` abre y cierra una conexión `psycopg2` nueva. Con Supabase/pooler esto puede agotar conexiones bajo carga.

`run_workers.py` fuerza `num_workers = 1` y `use_notify=False` por límites de pool — documentado en comentarios.

---

#### M-06: Recursión en loop NOTIFY

**Archivo:** `job_queue.py` — `_work_loop_with_notify`

En error, llama recursivamente a `self._work_loop_with_notify()` sin límite de reintentos → riesgo de stack overflow en fallos persistentes de conexión.

---

#### M-07: Duplicación de configuración DB

Existen dos sistemas paralelos:

- `data_staging.config.Settings` (`config.py`)
- `data_staging.database.DatabaseConfig` (`database.py`)

Ambos leen `.env`, detectan Supabase/ClickHouse y definen pools. Cambios deben hacerse en dos sitios.

---

#### M-08: Dependencias desalineadas

| Archivo | Observación |
|---------|-------------|
| `pyproject.toml` | Lista `pandas`; `requirements.txt` usa `polars` |
| `pyproject.toml` | No incluye `clickhouse-sqlalchemy` |
| `requirements.txt` | Versiones más nuevas que `pyproject.toml` |
| README | Python 3.10+; `pyproject` permite 3.9 |

---

#### M-09: Frontend: referencia a `onError` no definida en props

**Archivo:** `frontend/src/components/wizard/Step4Process.jsx`

Se usa `if (onError) onError()` pero `UploadWizard` no pasa `onError` en las props de `Step4Process` (solo `onComplete`). En runtime `onError` es `undefined` — no rompe, pero el stepper no marca error visual vía callback.

---

#### M-10: Promoción: `itertools.islice` para reanudar

**Archivo:** `promotion_worker.py` (aprox. línea 187)

```python
next(itertools.islice(f, total_inserted, total_inserted), None)
```

Para reanudar debería consumir `total_inserted` líneas (`islice(f, total_inserted)`), no un rango vacío. Posible bug en reanudación de promoción parcial.

---

### 3.4 Bajos (deuda técnica, documentación)

#### B-01: Código muerto o legacy

- `process_file_async` en `upload.py` (~685 líneas): flujo antiguo con `FileHandler`/`DataValidator` que no integra la cola ni archivos temp.
- `insert_records_in_batches`, `create_staging_table` en `file_processor.py`: usados en diseño anterior con tablas `staging_data.stage_*`.
- `print` de debug en `run_workers.py`: `DEBUG: LOADED FILE_PROCESSOR FROM: ...`

#### B-02: Documentación desactualizada

- `system_import_flow_guide.md` menciona chunks de 100k y COPY a staging; el código usa 1M y archivos en disco.
- `MANUAL_DE_USO.md` habla de "Staging" como destino del paso 4; la UI dice "Process to Production" y el backend escribe a CSV temp.

#### B-03: Tests

`pyproject.toml` define `testpaths = ["tests"]` pero no se encontró suite amplia de tests automatizados en el análisis.

#### B-04: `pyproject.toml` script inexistente

```toml
[project.scripts]
data-staging = "data_staging.cli:main"
```

No se verificó existencia de `cli.py` — posible entry point roto.

---

## 4. Mapa de endpoints API

### 4.1 Upload / Wizard (`/api/v1/upload`)

| Método | Ruta | Función |
|--------|------|---------|
| POST | `/file` | Subida + job `PROCESS_FILE` inmediato |
| POST | `/file-temp` | Wizard paso 1: análisis headers |
| POST | `/batch/{id}/mapping` | Wizard paso 2 |
| POST | `/batch/{id}/preview` | Wizard paso 3 (agregación) |
| POST | `/batch/{id}/process` | Encola procesamiento |
| GET | `/batch/{id}/status` | Estado batch + job |
| GET | `/batch/{id}/progress` | Progreso wizard |
| GET | `/batches` | Listado |
| POST | `/staging/promote/{id}` | Encola `PROMOTE_BATCH` |
| POST | `/staging/promote/{id}/resume` | Reanuda promoción parcial |
| GET | `/staging/batch/{id}/rejected/download` | CSV rechazados |
| DELETE | `/batch/{id}` | Eliminar batch (**roto**) |

### 4.2 System (`/api/v1`)

| Método | Ruta | Función |
|--------|------|---------|
| GET | `/config/database` | Config DB activa |
| POST | `/config/database` | Cambiar conexión |
| GET | `/schemas` | Listar esquemas |
| GET | `/tables` | Tablas por esquema |
| GET | `/table-columns` | Columnas de tabla destino (wizard) |
| GET | `/catalog-tables` | Catálogos disponibles |

### 4.3 Staging (`/api/v1/staging`) — **eliminado (jun 2026)**

Router retirado. Promoción y rechazados vía `/api/v1/upload/staging/*`. Metadatos en `/api/v1/system/*`.

### 4.4 Monitoring, Environments, Core

- `/api/v1/monitoring/*` — métricas y health
- `/api/v1/environments/*` — multi-entorno DB
- `/`, `/health`, `/api/v1/sources` — en `main.py`

---

## 5. Cola de trabajos (`job_queue`)

### 5.1 Tabla `staging_meta.job_queue`

Campos principales: `job_id`, `job_type`, `payload` (JSONB), `status`, `priority`, `retry_count`, `max_retries`, `worker_id`, timestamps.

Estados: `PENDING`, `PROCESSING`, `COMPLETED`, `FAILED`, `CANCELLED`.

### 5.2 Tipos de job registrados en workers

| `job_type` | Handler | Archivo |
|------------|---------|---------|
| `PROCESS_FILE` | `process_file_job` | `file_processor.py` |
| `PROMOTE_BATCH` | `promote_batch_job` | `promotion_worker.py` |

### 5.3 Concurrencia

- Selección con `FOR UPDATE SKIP LOCKED` (correcto para múltiples workers).
- Índice único opcional en `migrations/prevent_duplicate_jobs.sql` para un job pendiente por `batch_id`.

---

## 6. Validaciones implementadas en worker

En `validate_and_prepare_chunk` (`file_processor.py`):

| Regla | Descripción |
|-------|-------------|
| NOT NULL | Columnas obligatorias según `information_schema` |
| Tipos numéricos | Conversión y rechazo de no numéricos |
| Fechas | Múltiples formatos (`%Y-%m-%d`, `%d/%m/%Y`, etc.) |
| Longitud varchar | Regex sobre `character_maximum_length` |
| FK | Lookup en tabla referenciada (set en memoria) |
| Caracteres de control | Regex `[\x00-\x08\x0B\x0C\x0E-\x1F]` |
| Quality score | Penalización por nulls; umbral 80 comentado pero no fuerza FAIL |

Registros **PASSED** → `{batch_id}_valid_records.csv` (TSV).  
Registros **FAILED** → `{batch_id}_rejected_records.csv`.

Modo `direct_load=True`: COPY directo a tabla producción sin archivo intermedio.

---

## 7. Configuración de entorno (`.env`)

Variables clave (no exhaustivo):

| Variable | Uso |
|----------|-----|
| `DATABASE_URL` | Conexión principal (obligatoria) |
| `ENVIRONMENT` | `development`, `testing`, `public` → producción |
| `UPLOAD_PATH`, `TEMP_PATH` | Archivos subidos y temporales |
| `MAX_FILE_SIZE` | Límite 2 GB por defecto |
| `SECRET_KEY` | Seguridad (cambiar en prod) |
| Supabase / AWS / SMTP | Integraciones opcionales |

---

## 8. Puntos fuertes del código

1. **Separación API / workers** — La API responde rápido y delega trabajo pesado.
2. **SKIP LOCKED** en cola — Buen patrón para workers horizontales.
3. **Validación rica pre-carga** — Tipos, FK, NOT NULL antes de tocar producción.
4. **Optimización WAL** — Archivos temp en disco en lugar de staging masivo en BD (comentado explícitamente para Supabase).
5. **Promoción por lotes** — `execute_values` con commits parciales y estado `PARTIALLY_PROMOTED`.
6. **Soporte multi-DB** — PostgreSQL, Supabase, ClickHouse con detección por URL.
7. **Wizard UX** — Flujo guiado con preview y descarga de rechazados.

---

## 9. Plan de remediación sugerido (priorizado)

| Prioridad | Acción |
|-----------|--------|
| P0 | Importar `BatchControl` o reescribir `delete_batch` con SQL |
| P0 | Corregir `settings.upload_path` → `UPLOAD_PATH` |
| P1 | Restringir CORS y rotar `SECRET_KEY` en producción |
| P1 | Unificar `Environment` y `get_settings()` |
| P2 | Alinear modelo `BatchControl` con columna `metadata` y estados reales |
| P2 | Streaming real CSV (`scan_csv` / batched reader) |
| P2 | Revisar `islice` en resume de promoción |
| P3 | Eliminar o aislar `process_file_async` y rutas legacy |
| P3 | Unificar `config.py` y `database.py` |
| P3 | Añadir tests de integración wizard + worker |

---

## 10. Archivos más críticos para revisión futura

| Archivo | Motivo |
|---------|--------|
| `api/v1/upload.py` | Superficie API del wizard; bugs C-01, C-02 |
| `workers/file_processor.py` | Validación e ingesta |
| `workers/promotion_worker.py` | Promoción a producción |
| `workers/job_queue.py` | Concurrencia y conexiones |
| `config.py` / `database.py` | Configuración dual |
| `api/main.py` | CORS y routers |
| `frontend/.../Step4Process.jsx` | Orquestación UI paso final |

---

*Documento generado a partir de revisión estática del código. No sustituye pruebas de integración ni auditoría de seguridad en el entorno desplegado.*
