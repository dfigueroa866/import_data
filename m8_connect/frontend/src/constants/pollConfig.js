/** Intervalos de polling para cargas largas (Fase 1 — fiabilidad). */
export const POLL_INTERVAL_PROCESSING_MS = 2500;
export const POLL_INTERVAL_PROMOTION_MS = 6000;
export const POLL_INTERVAL_MAX_MS = 15000;

/** Errores transitorios (5xx/red) antes de mostrar aviso duro. */
export const MAX_TRANSIENT_POLL_ERRORS = 48;

/** Polls sin cambio antes de considerar el job "stale". */
export const MAX_STALE_POLLS = 400;

export const isPromotionPhase = (progress) =>
    progress?.phase === 'promoting'
    || (progress?.phase === 'queued' && progress?.job_type === 'PROMOTE_BATCH');

export const resolvePollIntervalMs = (progress, { promoting = false } = {}) => {
    if (promoting || isPromotionPhase(progress)) {
        return POLL_INTERVAL_PROMOTION_MS;
    }
    return POLL_INTERVAL_PROCESSING_MS;
};

export const isTransientPollError = (err) => {
    const status = err.response?.status;
    if (!status) return true;
    return status >= 500;
};
