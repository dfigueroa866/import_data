-- SOLUCIÓN INMEDIATA: Prevenir Duplicate Jobs

-- PASO 1: Crear UNIQUE INDEX para prevenir duplicados
-- Este index asegura que solo puede haber 1 job PENDING o PROCESSING por batch_id

CREATE UNIQUE INDEX IF NOT EXISTS idx_job_queue_unique_batch_pending
ON staging_meta.job_queue ((payload->>'batch_id'))
WHERE status IN ('PENDING', 'PROCESSING');

-- PASO 2: Verificar que funcionó
SELECT 
    indexname,
    indexdef
FROM pg_indexes
WHERE tablename = 'job_queue'
AND schemaname = 'staging_meta'
AND indexname = 'idx_job_queue_unique_batch_pending';

-- PASO 3: Limpiar jobs duplicados existentes
-- Mantener solo el job MÁS RECIENTE por batch_id

WITH duplicates AS (
    SELECT 
        job_id,
        payload->>'batch_id' as batch_id,
        ROW_NUMBER() OVER (
            PARTITION BY payload->>'batch_id' 
            ORDER BY created_at DESC
        ) as rn
    FROM staging_meta.job_queue
    WHERE status IN ('PENDING', 'PROCESSING')
)
DELETE FROM staging_meta.job_queue
WHERE job_id IN (
    SELECT job_id 
    FROM duplicates 
    WHERE rn > 1
);

-- PASO 4: Verificar resultado
SELECT 
    payload->>'batch_id' as batch_id,
    COUNT(*) as job_count,
    array_agg(job_id::text) as job_ids,
    array_agg(status) as statuses
FROM staging_meta.job_queue
WHERE status IN ('PENDING', 'PROCESSING')
GROUP BY payload->>'batch_id'
HAVING COUNT(*) > 1;
-- Si esta query NO retorna filas, no hay duplicados

COMMENT ON INDEX staging_meta.idx_job_queue_unique_batch_pending IS 
'Prevents duplicate jobs for the same batch_id when status is PENDING or PROCESSING';
