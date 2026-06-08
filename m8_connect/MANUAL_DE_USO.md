# Manual de uso — M8 Connect

## Acceso

1. Abrir la UI (por defecto http://localhost:5173)
2. Iniciar sesión en `/login` con usuario de `public.users`

## Tipos de carga

Desde **`/upload`** elija:

- **Historia** → `/upload/history` — ventas / `sales_history` (agregación Weekly o Monthly)
- **Catálogos** → `/upload/catalog` — SKUs, locations, etc.

## Wizard (4 pasos)

### Paso 1 — Upload

Suba CSV/Excel/Parquet. El sistema detecta encoding, delimitador y columnas.

### Paso 2 — Mapping

Mapee columnas del archivo a la tabla destino. Puede fijar valores por defecto (p. ej. `organization_id` desde sesión).

### Paso 3 — Preview

Para **historia**: agregación semanal/mensual y comprobación de totales. Para **catálogos**: vista previa de filas mapeadas.

### Paso 4 — Process

- Encola job `PROCESS_FILE` (worker valida y escribe `{batch_id}_valid_records.parquet`)
- Promoción manual o automática vía `PROMOTE_BATCH` a la tabla de producción
- Descargue rechazados si los hay: TSV con errores por fila

## Monitoreo

- **`/batches`** — historial de cargas
- **`/batches/{id}`** — progreso detallado
- **`/monitoring`** — salud del sistema

## Integración API (sin UI)

`POST /api/v1/upload/file` — upload directo + job `PROCESS_FILE` (ver Swagger http://localhost:8000/docs).

## Documentación técnica

Ver [`docs/FUNCIONAMIENTO_APLICACION.md`](docs/FUNCIONAMIENTO_APLICACION.md).
