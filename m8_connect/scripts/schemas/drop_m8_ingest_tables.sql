-- Rollback de tablas creadas por m8_ingest (servicio eliminado).
-- Ejecutar contra la misma BD que usa M8 Connect.
--
-- Uso directo:
--   psql "$DATABASE_URL" -f scripts/schemas/drop_m8_ingest_tables.sql
--
-- O desde m8_connect/:
--   python scripts/drop_m8_ingest_tables.py

BEGIN;

-- Jobs huérfanos del pipeline programado (opcional, no falla si no existen).
DELETE FROM staging_meta.job_queue
WHERE job_type = 'RUN_SCHEDULED_LOAD';

-- Orden: dependientes primero (ingest_deposits → profiles / api_keys).
DROP TABLE IF EXISTS staging_meta.ingest_deposits;
DROP TABLE IF EXISTS staging_meta.organization_api_keys;
DROP TABLE IF EXISTS staging_meta.organization_ingest_profiles;

COMMIT;
