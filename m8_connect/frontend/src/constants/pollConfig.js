/** Intervalos de polling para cargas largas (Fase 1 — fiabilidad). */
export const POLL_INTERVAL_PROCESSING_MS = 2500;
export const POLL_INTERVAL_PROMOTION_MS = 6000;
export const POLL_INTERVAL_PREVIEW_MS = 2500;
export const POLL_INTERVAL_MAX_MS = 15000;

/** Errores transitorios (5xx/red) antes de mostrar aviso duro. */
export const MAX_TRANSIENT_POLL_ERRORS = 48;

/** Polls sin cambio antes de considerar el job "stale". */
export const MAX_STALE_POLLS = 400;

/** Promoción: filas por lote UPSERT y tiempo observado por lote (~60s). */
export const PROMOTION_CHUNK_ROWS = 500_000;
export const PROMOTION_MS_PER_CHUNK = 60_000;
export const PROMOTION_BASE_WAIT_MS = 120_000;

export const isPromotionPhase = (progress) =>
    progress?.phase === 'promoting'
    || (progress?.phase === 'queued' && progress?.job_type === 'PROMOTE_BATCH');

export const isPreviewPhase = (progress) =>
    progress?.phase === 'preview_validating'
    || progress?.phase === 'preview_aggregating'
    || progress?.phase === 'preview_done'
    || progress?.phase === 'preview_failed';

export const resolvePollIntervalMs = (progress, { promoting = false, preview = false } = {}) => {
    if (preview || isPreviewPhase(progress)) {
        return POLL_INTERVAL_PREVIEW_MS;
    }
    if (promoting || isPromotionPhase(progress)) {
        return POLL_INTERVAL_PROMOTION_MS;
    }
    return POLL_INTERVAL_PROCESSING_MS;
};

const POOL_EXHAUSTION_PATTERN =
    /QueuePool|too many clients|connection timed out|pool limit/i;

export const isTransientPollError = (err) => {
    const status = err.response?.status;
    const message = String(err.response?.data?.detail || err.message || '');
    if (POOL_EXHAUSTION_PATTERN.test(message)) {
        return true;
    }
    if (!status) return true;
    return status >= 500;
};
