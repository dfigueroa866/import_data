import React, { useState, useEffect, useRef, useCallback } from 'react';
import { startProcessing, getProcessingProgress, promoteBatch, downloadRejectedRecords, deleteBatch } from '../../services/wizardService';
import { uploadService } from '../../services/uploadService';
import { useNavigate } from 'react-router-dom';
import useSessionLoadGuard from '../../hooks/useSessionLoadGuard';
import {
    MAX_STALE_POLLS,
    MAX_TRANSIENT_POLL_ERRORS,
    POLL_INTERVAL_MAX_MS,
    POLL_INTERVAL_PROCESSING_MS,
    POLL_INTERVAL_PROMOTION_MS,
    isTransientPollError,
    resolvePollIntervalMs,
} from '../../constants/pollConfig';
import { Button, LoadingSpinner, Alert } from '../ui';
import { formatNumber } from '../../lib/format';
import './Step4Process.css';

const resolveApiErrorMessage = (err) => {
    const detail = err?.response?.data?.detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) {
        return detail.map((item) => item?.msg || String(item)).join('; ');
    }
    if (typeof err?.response?.data?.message === 'string') {
        return err.response.data.message;
    }
    if (typeof err?.message === 'string' && err.message !== 'Network Error') {
        return err.message;
    }
    return null;
};

const progressSnapshot = (data) =>
    `${data?.status}|${data?.job_status}|${data?.phase}|${data?.progress_percentage}|${data?.processed_rows}|${data?.loaded_rows}|${data?.rejected_rows}|${data?.promoted_inserted}|${data?.promoted_updated}|${data?.progress_updated_at}`;

const formatPromotionSummary = (progress) => {
    if (progress?.promotion_summary) {
        return progress.promotion_summary;
    }
    const inserted = progress?.promoted_inserted ?? 0;
    const updated = progress?.promoted_updated ?? 0;
    if (inserted <= 0 && updated <= 0) {
        return null;
    }
    if (updated <= 0) {
        return `${inserted.toLocaleString('es-MX')} registro(s) insertado(s) (nuevos).`;
    }
    if (inserted <= 0) {
        return `${updated.toLocaleString('es-MX')} registro(s) actualizado(s) (ya existían en la tabla).`;
    }
    return `${inserted.toLocaleString('es-MX')} insertado(s) y ${updated.toLocaleString('es-MX')} actualizado(s).`;
};

const promotionSuccessTitle = (progress) => {
    const inserted = progress?.promoted_inserted ?? 0;
    const updated = progress?.promoted_updated ?? 0;
    if (updated > 0 && inserted === 0) {
        return 'Actualización completada';
    }
    if (inserted > 0 && updated > 0) {
        return 'Importación completada';
    }
    return 'Importación exitosa';
};

const resolvePromoteTotal = (progress, wizardData) => {
    const summary =
        wizardData?.validationSummary ?? wizardData?.previewData?.validation_summary ?? {};
    const grouped = Number(summary.grouped_rows) || 0;
    if (grouped > 0) return grouped;
    const fromProgress =
        Number(progress?.records_count)
        || Number(progress?.total_rows)
        || 0;
    if (fromProgress > 0) return fromProgress;
    return (
        Number(progress?.promoted_inserted ?? 0) + Number(progress?.promoted_updated ?? 0)
    );
};

const computePromotionBarPct = (promoteTotal, inserted, updated, complete) => {
    if (complete) return 100;
    if (promoteTotal <= 0) return 0;
    const processed = inserted + updated;
    if (processed <= 0) return 0;
    return Math.min(99, (processed / promoteTotal) * 100);
};

const isPromotionLive = (progress, promoting) =>
    promoting
    || progress?.phase === 'promoting'
    || (progress?.phase === 'queued' && progress?.job_type === 'PROMOTE_BATCH');

/** 0–50 %: carga en staging; 50–100 %: inserción/actualización en tabla destino */
const computeRowProgress = (progress, { promoting = false, capAt99 = true } = {}) => {
    const total = Number(progress?.total_rows) || 0;
    const loaded = Number(progress?.loaded_rows) || 0;
    const processed = Number(progress?.processed_rows) || 0;
    const inserted = Number(progress?.promoted_inserted) || 0;
    const updated = Number(progress?.promoted_updated) || 0;
    const promoted = inserted + updated;
    const maxPct = capAt99 ? 99 : 100;

    if (isPromotionLive(progress, promoting)) {
        const promoteTotal = loaded || total;
        let promotionFraction = 0;
        if (promoteTotal > 0) {
            promotionFraction = Math.min(
                1,
                promoted > 0 ? promoted / promoteTotal : processed / promoteTotal
            );
        }
        return Math.min(maxPct, 50 + promotionFraction * 50);
    }

    if (total > 0) {
        const staged = loaded > 0 ? loaded : processed;
        return Math.min(50, Math.max(0, (staged / total) * 50));
    }

    const legacy = Number(progress?.progress_percentage) || 0;
    return Math.min(50, legacy / 2);
};

const ProgressBar = ({ pct, label = 'Avance', complete = false }) => {
    const rounded = Math.round(pct);
    return (
        <div className="step4-live__bar-wrap">
            <div className="step4-live__bar-labels">
                <span className="step4-live__bar-label">{label}</span>
            </div>
            <div
                className="step4-live__bar"
                role="progressbar"
                aria-valuenow={rounded}
                aria-valuemin={0}
                aria-valuemax={100}
            >
                <div
                    className={[
                        'step4-live__bar-fill',
                        'step4-live__bar-fill--rows',
                        complete && 'step4-live__bar-fill--static',
                    ]
                        .filter(Boolean)
                        .join(' ')}
                    style={{ width: `${Math.min(100, Math.max(0, pct))}%` }}
                />
            </div>
        </div>
    );
};

const ReviewStatCell = ({ value, label, variant, onSelect, selectable, active }) => {
    const className = [
        'step4-live__stat',
        variant && `step4-live__stat--${variant}`,
        selectable && 'step4-live__stat--action',
        active && 'step4-live__stat--active',
    ]
        .filter(Boolean)
        .join(' ');

    const content = (
        <>
            <span className="step4-live__stat-value">{formatNumber(value)}</span>
            <span className="step4-live__stat-label">{label}</span>
        </>
    );

    if (selectable && onSelect) {
        return (
            <button
                type="button"
                className={className}
                onClick={onSelect}
                aria-pressed={active}
                title={`Ver ${label.toLowerCase()}`}
            >
                {content}
            </button>
        );
    }

    return <div className={className}>{content}</div>;
};

const PromotionPanel = ({
    progress,
    wizardData,
    mode = 'loading',
    onNewUpload,
    onDashboard,
}) => {
    const complete = mode === 'complete';
    const promoteTotal = resolvePromoteTotal(progress, wizardData);
    const inserted = progress?.promoted_inserted ?? 0;
    const updated = progress?.promoted_updated ?? 0;
    const pct = computePromotionBarPct(promoteTotal, inserted, updated, complete);
    const promotionSummary = formatPromotionSummary(progress);
    const title = complete ? promotionSuccessTitle(progress) : 'Cargando a producción';
    const subtitle = complete
        ? promotionSummary || 'La carga se completó correctamente.'
        : 'Escribiendo en tabla destino…';

    return (
        <div className="step4-live">
            <div className="step4-live__hero">
                <div className="step4-live__hero-text">
                    <h2 className="step4-live__title">{title}</h2>
                    <p className="step4-live__subtitle">{subtitle}</p>
                </div>
                <ProgressBar
                    pct={pct}
                    label={complete ? 'Completo' : 'Progreso de la carga a producción'}
                    complete={complete}
                />
            </div>

            <div className="step4-live__stats step4-live__stats--promotion">
                <div className="step4-live__stat">
                    <span className="step4-live__stat-value">{formatNumber(promoteTotal)}</span>
                    <span className="step4-live__stat-label">Total a procesar</span>
                </div>
                <div className="step4-live__stat step4-live__stat--ok">
                    <span className="step4-live__stat-value">{formatNumber(inserted)}</span>
                    <span className="step4-live__stat-label">Insertados</span>
                </div>
                <div className="step4-live__stat step4-live__stat--update">
                    <span className="step4-live__stat-value">{formatNumber(updated)}</span>
                    <span className="step4-live__stat-label">Actualizados</span>
                </div>
            </div>

            {!complete && progress?.job_status && (
                <div className="step4-live__meta">
                    <span
                        className={`step4-live__job step4-live__job--${(progress.job_status || '').toLowerCase()}`}
                    >
                        Worker:{' '}
                        {progress.job_status === 'PROCESSING'
                            ? 'activo'
                            : progress.job_status === 'PENDING'
                              ? 'en cola'
                              : progress.job_status}
                    </span>
                </div>
            )}

            {complete && (
                <div className="step4-completed__actions step4-completed__actions--success">
                    <Button variant="primary" size="lg" onClick={onNewUpload}>
                        Subir otro archivo
                    </Button>
                    <Button variant="secondary" size="lg" onClick={onDashboard}>
                        Ir al dashboard
                    </Button>
                </div>
            )}
        </div>
    );
};

const ProcessingLiveView = ({ progress, isCatalog, promoting }) => {
    const promotionLive = isPromotionLive(progress, promoting);
    const total = progress?.total_rows || 0;
    const processed = progress?.processed_rows || 0;
    const valid = progress?.loaded_rows || 0;
    const rejected = progress?.rejected_rows || 0;
    const inserted = progress?.promoted_inserted ?? 0;
    const updated = progress?.promoted_updated ?? 0;
    const pct = computeRowProgress(progress, { promoting });
    const showMeta = (progress?.chunks_total > 1 || progress?.job_status)
        && (!promotionLive || progress?.phase === 'promoting' || progress?.phase === 'queued');

    const title = promoting
        ? 'Cargando a producción'
        : isCatalog
          ? 'Validando catálogo'
          : 'Validando archivo';

    const phaseHint = promotionLive
        ? pct < 50
            ? 'Preparando staging…'
            : 'Escribiendo en tabla destino…'
        : pct < 50
          ? 'Cargando en staging…'
          : 'Staging completo';

    return (
        <div className="step4-live">
            <div className="step4-live__hero">
                <div className="step4-live__hero-text">
                    <h2 className="step4-live__title">{title}</h2>
                    <p className="step4-live__subtitle">{phaseHint}</p>
                </div>
                <ProgressBar
                    pct={pct}
                    label={promoting ? 'Progreso de la carga a producción' : 'Progreso del procesamiento'}
                />
            </div>

            <div className={`step4-live__stats${promotionLive ? ' step4-live__stats--promotion' : ''}`}>
                {promotionLive ? (
                    <>
                        <div className="step4-live__stat">
                            <span className="step4-live__stat-value">{formatNumber(total)}</span>
                            <span className="step4-live__stat-label">Total</span>
                        </div>
                        <div className="step4-live__stat step4-live__stat--ok">
                            <span className="step4-live__stat-value">{formatNumber(inserted)}</span>
                            <span className="step4-live__stat-label">Insertados</span>
                        </div>
                        <div className="step4-live__stat step4-live__stat--update">
                            <span className="step4-live__stat-value">{formatNumber(updated)}</span>
                            <span className="step4-live__stat-label">Actualizados</span>
                        </div>
                    </>
                ) : (
                    <>
                        <div className="step4-live__stat">
                            <span className="step4-live__stat-value">{formatNumber(total)}</span>
                            <span className="step4-live__stat-label">Total filas</span>
                        </div>
                        <div className="step4-live__stat">
                            <span className="step4-live__stat-value">{formatNumber(processed)}</span>
                            <span className="step4-live__stat-label">Procesadas</span>
                        </div>
                        <div className="step4-live__stat step4-live__stat--ok">
                            <span className="step4-live__stat-value">{formatNumber(valid)}</span>
                            <span className="step4-live__stat-label">Válidas</span>
                        </div>
                        <div className="step4-live__stat step4-live__stat--err">
                            <span className="step4-live__stat-value">{formatNumber(rejected)}</span>
                            <span className="step4-live__stat-label">Rechazadas</span>
                        </div>
                    </>
                )}
            </div>

            {showMeta && (
                <div className="step4-live__meta">
                    {progress?.chunks_total > 1 && (
                        <span>
                            Bloque {progress.chunks_processed || 0} / {progress.chunks_total}
                        </span>
                    )}
                    {progress?.job_status && (
                        <span className={`step4-live__job step4-live__job--${(progress.job_status || '').toLowerCase()}`}>
                            Worker: {progress.job_status === 'PROCESSING' ? 'activo' : progress.job_status === 'PENDING' ? 'en cola' : progress.job_status}
                        </span>
                    )}
                </div>
            )}
        </div>
    );
};

const isProgressFailure = (progressData) => {
    if (!progressData) return false;
    const status = progressData.status;
    if (status === 'CANCELLED' || status === 'FAILED') return true;
    if (status === 'PROCESSING') return false;
    if (progressData.job_status === 'FAILED') return true;
    if (progressData.is_successful === false) return true;
    return false;
};

const Step4Process = ({
    wizardData,
    updateWizardData,
    resetWizard,
    onComplete,
    onError,
    onProcessingStart,
    monitorMode = false,
}) => {
    const navigate = useNavigate();
    const [status, setStatus] = useState('idle');
    const [processing, setProcessing] = useState(true);
    const [progress, setProgress] = useState(null);
    const [error, setError] = useState(null);
    const [completed, setCompleted] = useState(false);
    const [reviewTab, setReviewTab] = useState('passed');

    const [promoting, setPromoting] = useState(false);
    const [promoteSuccess, setPromoteSuccess] = useState(false);
    const [promoteError, setPromoteError] = useState('');
    const [pollWarning, setPollWarning] = useState('');

    useSessionLoadGuard(processing || promoting);

    const processingStartedForBatchRef = useRef(null);
    const pollIntervalRef = useRef(null);
    const pollDelayRef = useRef(POLL_INTERVAL_PROCESSING_MS);
    const promotePollIntervalRef = useRef(null);
    const stalePollCountRef = useRef(0);
    const lastProgressSnapshotRef = useRef(null);
    const promoteStalePollCountRef = useRef(0);
    const lastPromoteSnapshotRef = useRef(null);
    const pollErrorCountRef = useRef(0);
    const promotePollDelayRef = useRef(POLL_INTERVAL_PROMOTION_MS);
    const promotePollErrorCountRef = useRef(0);
    const promotionEnqueueRef = useRef(null);
    const beginPromotionRef = useRef(null);
    const startPromotionPollingRef = useRef(null);

    const stopPolling = useCallback(() => {
        if (pollIntervalRef.current) {
            clearTimeout(pollIntervalRef.current);
            pollIntervalRef.current = null;
        }
    }, []);

    const stopPromotePolling = useCallback(() => {
        if (promotePollIntervalRef.current) {
            clearTimeout(promotePollIntervalRef.current);
            promotePollIntervalRef.current = null;
        }
    }, []);

    const stopAllPolling = useCallback(() => {
        stopPolling();
        stopPromotePolling();
    }, [stopPolling, stopPromotePolling]);

    const evaluateProgress = useCallback(
        (progressData, { mode = 'processing' } = {}) => {
            const snapshot = progressSnapshot(progressData);
            const isPromote = mode === 'promote';
            const staleRef = isPromote ? promoteStalePollCountRef : stalePollCountRef;
            const lastRef = isPromote ? lastPromoteSnapshotRef : lastProgressSnapshotRef;

            if (lastRef.current === snapshot) {
                const isQueued = progressData.job_status === 'PENDING';
                if (isQueued) {
                    staleRef.current = 0;
                } else {
                    staleRef.current += 1;
                }
            } else {
                staleRef.current = 0;
                lastRef.current = snapshot;
            }

            setProgress(progressData);

            if (progressData.status === 'PROMOTED') {
                return 'promoted';
            }
            if (progressData.status === 'CANCELLED') {
                return 'failed';
            }
            if (mode === 'processing' && !progressData.auto_production && progressData.status === 'COMPLETED') {
                if (isProgressFailure(progressData)) {
                    return 'failed';
                }
                return 'completed';
            }
            if (isProgressFailure(progressData)) {
                return 'failed';
            }
            if (staleRef.current >= MAX_STALE_POLLS) {
                return 'stale';
            }
            return null;
        },
        []
    );

    const tryRecoverPromotedState = useCallback(
        async (batchId) => {
            try {
                const progressData = await getProcessingProgress(batchId);
                if (progressData.status === 'PROMOTED') {
                    stopPromotePolling();
                    setProgress(progressData);
                    setCompleted(true);
                    setPromoteSuccess(true);
                    setPromoting(false);
                    setPromoteError('');
                    onComplete?.();
                    return true;
                }
            } catch {
                // Ignorar: puede ser un fallo transitorio del pool.
            }
            return false;
        },
        [stopPromotePolling, onComplete]
    );

    const startPromotionPolling = useCallback(
        async (batchId) => {
            const pollPromote = async () => {
                try {
                    const progressData = await getProcessingProgress(batchId);
                    promotePollErrorCountRef.current = 0;
                    promotePollDelayRef.current = resolvePollIntervalMs(progressData, {
                        promoting: true,
                    });
                    setPollWarning('');

                    const result = evaluateProgress(progressData, { mode: 'promote' });

                    if (result === 'promoted') {
                        stopPromotePolling();
                        setCompleted(true);
                        setPromoteSuccess(true);
                        setPromoting(false);
                        setPromoteError('');
                        onComplete?.();
                    } else if (result === 'failed') {
                        const recovered = await tryRecoverPromotedState(batchId);
                        if (recovered) return;
                        stopPromotePolling();
                        setPromoteError(
                            progressData?.error_message
                            || progressData?.current_operation
                            || 'La promoción falló.'
                        );
                        setPromoting(false);
                    } else if (result === 'stale') {
                        const recovered = await tryRecoverPromotedState(batchId);
                        if (recovered) return;
                        stopPromotePolling();
                        setPromoteError(
                            'La promoción no avanzó en varios minutos. Verifica que los workers estén activos (python run_workers.py).'
                        );
                        setPromoting(false);
                    }
                } catch (err) {
                    console.error('Promotion polling error', err);
                    if (isTransientPollError(err)) {
                        promotePollErrorCountRef.current += 1;
                        promotePollDelayRef.current = Math.min(
                            POLL_INTERVAL_MAX_MS,
                            Math.round(promotePollDelayRef.current * 1.4)
                        );
                        if (promotePollErrorCountRef.current >= MAX_TRANSIENT_POLL_ERRORS) {
                            setPollWarning(
                                'El servidor está ocupado. La promoción puede continuar en segundo plano; reintentando consulta…'
                            );
                        }
                        const recovered = await tryRecoverPromotedState(batchId);
                        if (recovered) return;
                    } else {
                        const recovered = await tryRecoverPromotedState(batchId);
                        if (recovered) return;
                        stopPromotePolling();
                        setPromoteError(
                            resolveApiErrorMessage(err)
                                || 'No se pudo consultar el progreso de la promoción.'
                        );
                        setPromoting(false);
                    }
                }
            };

            const runPromotePollLoop = async () => {
                if (promotePollIntervalRef.current === null) return;
                await pollPromote();
                if (promotePollIntervalRef.current === null) return;
                promotePollIntervalRef.current = setTimeout(
                    runPromotePollLoop,
                    promotePollDelayRef.current
                );
            };

            promoteStalePollCountRef.current = 0;
            lastPromoteSnapshotRef.current = null;
            stopPromotePolling();
            promotePollDelayRef.current = POLL_INTERVAL_PROMOTION_MS;
            promotePollErrorCountRef.current = 0;
            setPollWarning('');

            await pollPromote();
            promotePollIntervalRef.current = setTimeout(
                runPromotePollLoop,
                promotePollDelayRef.current
            );
        },
        [evaluateProgress, stopPromotePolling, onComplete, tryRecoverPromotedState]
    );
    startPromotionPollingRef.current = startPromotionPolling;

    const beginPromotion = useCallback(
        async (promoteTotalOverride, { skipEnqueue = false } = {}) => {
            const batchId = wizardData.batchId;
            if (!batchId) return;

            const promoteTotal = promoteTotalOverride ?? 0;
            if (promoteTotal <= 0) {
                setPromoteError('No hay registros válidos para cargar a producción.');
                setPromoting(false);
                return;
            }

            try {
                setPromoting(true);
                setPromoteError('');

                if (!skipEnqueue) {
                    if (promotionEnqueueRef.current !== batchId) {
                        await promoteBatch(batchId);
                        promotionEnqueueRef.current = batchId;
                    }
                    setProgress((prev) => ({
                        ...(prev || {}),
                        status: prev?.status || 'COMPLETED',
                        job_type: 'PROMOTE_BATCH',
                        job_status: 'PENDING',
                        phase: 'queued',
                        progress_percentage: 0,
                        total_rows: promoteTotal,
                        processed_rows: 0,
                        loaded_rows: promoteTotal,
                        promoted_inserted: 0,
                        promoted_updated: 0,
                        chunks_processed: 0,
                        chunks_total: Math.max(1, Math.ceil(promoteTotal / 50000)),
                    }));
                }

                await startPromotionPolling(batchId);
            } catch (err) {
                if (isTransientPollError(err)) {
                    await startPromotionPolling(batchId);
                    return;
                }
                const recovered = await tryRecoverPromotedState(batchId);
                if (recovered) return;
                setPromoteError(
                    resolveApiErrorMessage(err) || 'No se pudo iniciar la carga a producción.'
                );
                setPromoting(false);
            }
        },
        [wizardData.batchId, startPromotionPolling, tryRecoverPromotedState]
    );
    beginPromotionRef.current = beginPromotion;

    useEffect(() => {
        const validatedInPreview =
            wizardData.validatedInPreview
            || wizardData.previewData?.validated_in_preview
            || false;

        if (!validatedInPreview || monitorMode || !wizardData.batchId) return undefined;

        const batchId = wizardData.batchId;
        let cancelled = false;

        const initAutoPromotion = async () => {
            setPromoting(true);
            setProcessing(false);
            setPromoteError('');

            try {
                const progressData = await getProcessingProgress(batchId);
                if (cancelled) return;

                if (progressData.status === 'PROMOTED') {
                    setProgress(progressData);
                    setCompleted(true);
                    setPromoteSuccess(true);
                    setProcessing(false);
                    setPromoting(false);
                    setPromoteError('');
                    onComplete?.();
                    return;
                }

                const summary =
                    wizardData.validationSummary || wizardData.previewData?.validation_summary || {};
                const groupedCount = summary.grouped_rows ?? summary.valid_rows ?? 0;
                const rejectedCount = summary.rejected_rows ?? 0;

                setProgress((prev) => ({
                    ...(prev || {}),
                    ...progressData,
                    status: progressData.status || 'COMPLETED',
                    phase: progressData.phase || 'done',
                    total_rows:
                        summary.grouped_rows
                        || progressData.total_rows
                        || groupedCount,
                    loaded_rows:
                        summary.grouped_rows
                        || progressData.loaded_rows
                        || groupedCount,
                    rejected_rows: progressData.rejected_rows ?? rejectedCount,
                    processed_rows:
                        progressData.processed_rows || groupedCount,
                    is_successful: groupedCount > 0,
                }));
                setProcessing(false);
                setError(null);

                if (groupedCount === 0) {
                    setError(
                        'No hay filas válidas para cargar a producción. Revisa los rechazados en el paso 3.'
                    );
                    setStatus('error');
                    onError?.();
                    return;
                }

                if (progressData.status === 'FAILED') {
                    const recovered = await tryRecoverPromotedState(batchId);
                    if (recovered || cancelled) return;
                    setPromoteError(progressData.error_message || 'La promoción falló.');
                    setPromoting(false);
                    return;
                }

                const promoActive =
                    progressData.job_type === 'PROMOTE_BATCH'
                    && ['PENDING', 'PROCESSING'].includes(progressData.job_status);

                await beginPromotionRef.current?.(groupedCount, { skipEnqueue: promoActive });
            } catch (err) {
                if (cancelled) return;
                if (isTransientPollError(err)) {
                    setPromoting(true);
                    setProcessing(false);
                    await startPromotionPollingRef.current?.(batchId);
                    return;
                }
                const recovered = await tryRecoverPromotedState(batchId);
                if (recovered) return;
                setPromoteError(
                    resolveApiErrorMessage(err) || 'No se pudo iniciar la carga a producción.'
                );
                setPromoting(false);
                setProcessing(false);
            }
        };

        initAutoPromotion();

        return () => {
            cancelled = true;
        };
    }, [
        wizardData.batchId,
        wizardData.validatedInPreview,
        wizardData.validationSummary,
        wizardData.previewData,
        monitorMode,
        tryRecoverPromotedState,
        onComplete,
        onError,
    ]);

    useEffect(() => {
        const batchId = wizardData.batchId;
        if (!batchId) return undefined;

        const validatedInPreview =
            wizardData.validatedInPreview
            || wizardData.previewData?.validated_in_preview
            || false;

        if (validatedInPreview && !monitorMode) {
            return undefined;
        }

        let cancelled = false;

        const handleTerminal = (result, progressData) => {
            if (result === 'promoted') {
                setCompleted(true);
                setProcessing(false);
                setPromoteSuccess(true);
                onComplete?.();
            } else if (result === 'completed') {
                setCompleted(true);
                setProcessing(false);
                onComplete?.();
            } else if (result === 'failed') {
                setError(
                    progressData?.status === 'CANCELLED'
                        ? 'Batch cancelado.'
                        : progressData?.error_message
                        || progressData?.current_operation
                        || 'Processing failed'
                );
                setStatus('error');
                setProcessing(false);
                onError?.();
            } else if (result === 'stale') {
                setError(
                    'El procesamiento no avanzó en varios minutos. Verifica que los workers estén activos (python run_workers.py) o revisa el batch en Batches.'
                );
                setStatus('error');
                setProcessing(false);
                onError?.();
            }
        };

        const pollOnce = async () => {
            if (cancelled) return;
            try {
                const progressData = await getProcessingProgress(batchId);
                if (cancelled) return;

                pollErrorCountRef.current = 0;
                pollDelayRef.current = resolvePollIntervalMs(progressData, { promoting: false });
                setPollWarning('');

                const result = evaluateProgress(progressData, { mode: 'processing' });
                if (result) {
                    stopPolling();
                    handleTerminal(result, progressData);
                }
            } catch (err) {
                console.error('Polling error:', err);
                if (isTransientPollError(err)) {
                    pollErrorCountRef.current += 1;
                    pollDelayRef.current = Math.min(
                        POLL_INTERVAL_MAX_MS,
                        Math.round(pollDelayRef.current * 1.4)
                    );
                    if (pollErrorCountRef.current >= MAX_TRANSIENT_POLL_ERRORS) {
                        setPollWarning(
                            'El servidor está ocupado. La carga puede continuar en segundo plano; reintentando consulta…'
                        );
                    }
                    return;
                }
                stopPolling();
                setError(
                    err.response?.data?.detail
                        || 'No se pudo consultar el progreso.'
                );
                setStatus('error');
                setProcessing(false);
                onError?.();
            }
        };

        const runPollLoop = async () => {
            if (cancelled) return;
            await pollOnce();
            if (cancelled) return;
            pollIntervalRef.current = setTimeout(runPollLoop, pollDelayRef.current);
        };

        const initProcessing = async () => {
            try {
                setProcessing(true);
                setError('');
                stalePollCountRef.current = 0;
                lastProgressSnapshotRef.current = null;
                pollErrorCountRef.current = 0;
                pollDelayRef.current = POLL_INTERVAL_PROCESSING_MS;
                setPollWarning('');

                if (processingStartedForBatchRef.current !== batchId) {
                    processingStartedForBatchRef.current = batchId;
                    onProcessingStart?.();
                    if (!monitorMode) {
                        await startProcessing(batchId, { auto_production: false });
                    }
                }

                if (cancelled) return;

                await pollOnce();
                if (cancelled) return;

                pollIntervalRef.current = setTimeout(runPollLoop, pollDelayRef.current);
            } catch (err) {
                if (cancelled) return;
                setError(err.response?.data?.detail || 'Failed to start processing');
                setStatus('error');
                setProcessing(false);
                onError?.();
                console.error(err);
            }
        };

        initProcessing();

        return () => {
            cancelled = true;
            stopPolling();
        };
    }, [
        wizardData.batchId,
        wizardData.validatedInPreview,
        wizardData.validationSummary,
        wizardData.previewData,
        evaluateProgress,
        stopPolling,
        onComplete,
        onError,
        onProcessingStart,
        monitorMode,
    ]);

    useEffect(() => {
        return () => {
            stopAllPolling();
            processingStartedForBatchRef.current = null;
        };
    }, [stopAllPolling]);

    const handleNewUpload = async () => {
        stopAllPolling();
        try {
            if (wizardData.batchId) {
                await deleteBatch(wizardData.batchId);
            }
        } catch (err) {
            console.error('Cleanup failed', err);
        } finally {
            processingStartedForBatchRef.current = null;
            resetWizard();
        }
    };

    const handlePromote = async () => {
        try {
            setPromoteError('');
            const progressData = await getProcessingProgress(wizardData.batchId);
            if (progressData.status === 'PROMOTED') {
                setProgress(progressData);
                setCompleted(true);
                setPromoteSuccess(true);
                setPromoting(false);
                onComplete?.();
                return;
            }
            const promoActive =
                progressData.job_type === 'PROMOTE_BATCH'
                && ['PENDING', 'PROCESSING'].includes(progressData.job_status);
            const summary =
                wizardData.validationSummary || wizardData.previewData?.validation_summary || {};
            const groupedCount =
                summary.grouped_rows
                ?? summary.valid_rows
                ?? progress?.loaded_rows
                ?? progressData.loaded_rows
                ?? 0;
            await beginPromotion(groupedCount, { skipEnqueue: promoActive });
        } catch (err) {
            if (isTransientPollError(err)) {
                setPromoting(true);
                await startPromotionPolling(wizardData.batchId);
                return;
            }
            const recovered = await tryRecoverPromotedState(wizardData.batchId);
            if (recovered) return;
            setPromoteError(
                resolveApiErrorMessage(err) || 'No se pudo reintentar la carga a producción.'
            );
            setPromoting(false);
        }
    };

    const handleDownloadRejected = async () => {
        try {
            await downloadRejectedRecords(wizardData.batchId);
        } catch (err) {
            console.error('Download failed', err);
            alert('No se pudo descargar rechazados: ' + (err.response?.data?.detail || err.message));
        }
    };

    const handleMonitorResume = async () => {
        try {
            setError(null);
            setStatus('idle');
            setProcessing(true);
            setCompleted(false);
            stalePollCountRef.current = 0;
            lastProgressSnapshotRef.current = null;
            await uploadService.resumePromotion(wizardData.batchId);
            const progressData = await getProcessingProgress(wizardData.batchId);
            setProgress(progressData);
            stopPolling();
            pollDelayRef.current = resolvePollIntervalMs(progressData, { promoting: true });
            promotePollDelayRef.current = POLL_INTERVAL_PROMOTION_MS;

            const pollMonitor = async () => {
                try {
                    const data = await getProcessingProgress(wizardData.batchId);
                    pollErrorCountRef.current = 0;
                    pollDelayRef.current = resolvePollIntervalMs(data, { promoting: true });
                    setPollWarning('');

                    const result = evaluateProgress(data, { mode: 'processing' });
                    if (result === 'promoted') {
                        stopPolling();
                        setCompleted(true);
                        setProcessing(false);
                        setPromoteSuccess(true);
                    } else if (result === 'completed') {
                        stopPolling();
                        setCompleted(true);
                        setProcessing(false);
                    } else if (result === 'failed' || result === 'stale') {
                        stopPolling();
                        setError(
                            data?.error_message || data?.current_operation || 'La promoción falló'
                        );
                        setProcessing(false);
                    }
                } catch (err) {
                    console.error('Polling error:', err);
                    if (isTransientPollError(err)) {
                        pollErrorCountRef.current += 1;
                        pollDelayRef.current = Math.min(
                            POLL_INTERVAL_MAX_MS,
                            Math.round(pollDelayRef.current * 1.4)
                        );
                        if (pollErrorCountRef.current >= MAX_TRANSIENT_POLL_ERRORS) {
                            setPollWarning(
                                'El servidor está ocupado. La promoción puede continuar en segundo plano; reintentando consulta…'
                            );
                        }
                    }
                }
            };

            const runMonitorPollLoop = async () => {
                await pollMonitor();
                if (pollIntervalRef.current === null) return;
                pollIntervalRef.current = setTimeout(runMonitorPollLoop, pollDelayRef.current);
            };

            pollIntervalRef.current = setTimeout(runMonitorPollLoop, pollDelayRef.current);
        } catch (err) {
            setError(err.response?.data?.detail || 'No se pudo reanudar la promoción.');
            setProcessing(false);
        }
    };

    if (error && !processing) {
        return (
            <div className="step4-error">
                <div className="error-icon">✕</div>
                <h3>Carga no exitosa</h3>
                <Alert variant="error">{error}</Alert>
                <div className="error-actions">
                    {monitorMode ? (
                        <>
                            <Button variant="secondary" onClick={() => navigate('/batches')}>
                                Volver a batches
                            </Button>
                            <Button variant="primary" onClick={handleMonitorResume}>
                                Reanudar promoción
                            </Button>
                        </>
                    ) : (
                        <>
                            <Button variant="secondary" onClick={() => navigate('/batches')}>
                                View Batches
                            </Button>
                            <Button variant="primary" onClick={handleNewUpload}>
                                Start Over (Reset)
                            </Button>
                        </>
                    )}
                </div>
            </div>
        );
    }

    const isCatalog = wizardData?.loadMode === 'catalog';
    const validatedInPreview =
        wizardData.validatedInPreview
        || wizardData.previewData?.validated_in_preview
        || false;

    if (promoteError && !promoting && !promoteSuccess) {
        return (
            <div className="step4-process">
                <div className="step4-error">
                    <h3>Error al cargar a producción</h3>
                    <Alert variant="error">{promoteError}</Alert>
                    <div className="error-actions">
                        <Button variant="secondary" onClick={() => navigate('/batches')}>
                            Ver batches
                        </Button>
                        <Button variant="primary" onClick={handlePromote}>
                            Reintentar carga a producción
                        </Button>
                    </div>
                </div>
            </div>
        );
    }

    if (
        validatedInPreview
        && !monitorMode
        && !completed
        && !promoteSuccess
        && !promoting
        && !error
    ) {
        return (
            <div className="step4-process">
                <PromotionPanel
                    progress={progress}
                    wizardData={wizardData}
                    mode="loading"
                />
                <p className="step4-process__hint">
                    <LoadingSpinner size="sm" />
                    Iniciando carga a producción…
                </p>
                <div className="error-actions" style={{ marginTop: '1rem' }}>
                    <Button variant="primary" onClick={handlePromote}>
                        Iniciar carga a producción
                    </Button>
                </div>
            </div>
        );
    }

    if (promoting || (completed && promoteSuccess)) {
        return (
            <div className="step4-process">
                <PromotionPanel
                    progress={progress}
                    wizardData={wizardData}
                    mode={promoteSuccess ? 'complete' : 'loading'}
                    onNewUpload={handleNewUpload}
                    onDashboard={() => navigate('/')}
                />
                {!promoteSuccess && (
                    <p className="step4-process__hint">
                        <LoadingSpinner size="sm" />
                        Cargando registros a producción. No cierres esta ventana.
                    </p>
                )}
                {pollWarning && (
                    <p className="step4-process__poll-warning" role="status">
                        {pollWarning}
                    </p>
                )}
            </div>
        );
    }

    if (completed) {
        const rejectedCount = progress?.rejected_rows || 0;
        const actualPassed = progress?.loaded_rows || 0;

        return (
            <div className="step4-process">
                <div className="step4-live">
                    <div className="step4-live__hero">
                        <div className="step4-live__hero-text">
                            <h2 className="step4-live__title">Proceso de validación completo</h2>
                            <p className="step4-live__subtitle">
                                {isCatalog
                                    ? 'Revisa válidos y rechazados antes de cargar a producción.'
                                    : 'Revisa el resultado antes de cargar a producción.'}
                            </p>
                        </div>
                        <ProgressBar pct={100} label="Completo" complete />
                    </div>

                    <div className="step4-live__stats step4-live__stats--review">
                        <ReviewStatCell
                            value={(progress?.total_rows || 0) || actualPassed + rejectedCount}
                            label="Total filas"
                        />
                        <ReviewStatCell
                            value={actualPassed}
                            label="Válidas"
                            variant="ok"
                            selectable
                            active={reviewTab === 'passed'}
                            onSelect={() => setReviewTab('passed')}
                        />
                        <ReviewStatCell
                            value={rejectedCount}
                            label="Rechazadas"
                            variant="err"
                            selectable
                            active={reviewTab === 'rejected'}
                            onSelect={() => setReviewTab('rejected')}
                        />
                    </div>

                    <div className="step4-live__body">
                        {promoteError && (
                            <div className="promotion-error">
                                <span className="icon">⛔</span>
                                {promoteError}
                            </div>
                        )}

                        {rejectedCount > 0 && reviewTab !== 'rejected' && (
                            <p className="step4-rejected-hint" role="note">
                                Para descargar el archivo con los errores, selecciona{' '}
                                <strong>Rechazadas</strong> y después pulsa «Descargar rechazados
                                (.csv)».
                            </p>
                        )}

                        {reviewTab === 'passed' && (
                            <p className="tab-pane__desc">
                                {isCatalog
                                    ? 'Pasaron validación de tipos, NOT NULL, enums y reglas del catálogo. Carga a producción cuando estés listo.'
                                    : 'Pasaron validaciones de formato y tipo. Carga a producción cuando estés listo.'}
                            </p>
                        )}

                        {reviewTab === 'rejected' && (
                            <p className="tab-pane__desc">
                                {rejectedCount > 0
                                    ? 'Registros que no cumplen tipos, enums, NOT NULL, duplicados o reglas del catálogo. Descarga el archivo, corrígelo y vuelve a cargar.'
                                    : 'No hay registros rechazados. Puedes descargar un CSV vacío para referencia.'}
                            </p>
                        )}

                        <div className="step4-completed__actions">
                            {reviewTab === 'rejected' ? (
                                <Button
                                    variant="secondary"
                                    size="lg"
                                    className="step4-btn-download"
                                    onClick={handleDownloadRejected}
                                >
                                    Descargar rechazados (.csv)
                                </Button>
                            ) : (
                                <Button
                                    variant="primary"
                                    size="lg"
                                    className="step4-btn-promote"
                                    onClick={handlePromote}
                                    disabled={promoting || actualPassed === 0}
                                >
                                    Cargar a producción
                                </Button>
                            )}
                        </div>
                    </div>

                    <footer className="step4-live__footer">
                        <Button variant="secondary" onClick={() => navigate('/batches')}>
                            Ver batches
                        </Button>
                        <Button variant="secondary" onClick={handleNewUpload}>
                            Nueva carga
                        </Button>
                    </footer>
                </div>
            </div>
        );
    }

    return (
        <div className="step4-process">
            <ProcessingLiveView
                progress={progress}
                isCatalog={isCatalog}
                promoting={false}
            />
            <p className="step4-process__hint">
                <LoadingSpinner size="sm" />
                Actualización en tiempo real cada pocos segundos. No cierres esta ventana.
            </p>
            {pollWarning && (
                <p className="step4-process__poll-warning" role="status">
                    {pollWarning}
                </p>
            )}
        </div>
    );
};

export default Step4Process;
