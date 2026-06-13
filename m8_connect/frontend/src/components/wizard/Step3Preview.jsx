import React, { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import {
    startPreview,
    getPreviewResult,
    getProcessingProgress,
    downloadRejectedRecords,
} from '../../services/wizardService';
import { useAuth } from '../../context/AuthContext';
import useSessionLoadGuard from '../../hooks/useSessionLoadGuard';
import {
    POLL_INTERVAL_PREVIEW_MS,
    POLL_INTERVAL_MAX_MS,
    MAX_TRANSIENT_POLL_ERRORS,
    MAX_STALE_POLLS,
    isTransientPollError,
    resolvePollIntervalMs,
} from '../../constants/pollConfig';
import { Button, LoadingSpinner, DataTableShell, DataTable, DataTableHead, DataTableBody, DataTableRow, DataTableTh, DataTableTd, DataTableRowNum, EmptyState } from '../ui';
import { formatNumber, EMPTY } from '../../lib/format';
import {
    enrichHistoryPreviewRows,
    getHistoryPreviewColumnKeys,
} from '../../constants/historyConfig';
import './Step3Preview.css';

/** Evita doble init en Strict Mode (misma pestaña). */
const previewInitInflight = new Map();

const previewProgressSnapshot = (progressData) => {
    if (!progressData) return '';
    return [
        progressData.phase,
        progressData.progress_percentage,
        progressData.current_operation,
        progressData.chunks_processed,
        progressData.status,
    ].join('|');
};

const Step3Preview = ({ wizardData, updateWizardData, nextStep, prevStep }) => {
    const { user } = useAuth();
    const [previewData, setPreviewData] = useState(null);

    const organizationDisplayName =
        previewData?.organization_name ||
        user?.organization_name ||
        wizardData.organizationName ||
        '';
    const [loading, setLoading] = useState(true);
    const [downloadingRejected, setDownloadingRejected] = useState(false);
    const [error, setError] = useState('');
    const [previewProgress, setPreviewProgress] = useState(null);

    const pollIntervalRef = useRef(null);
    const pollDelayRef = useRef(POLL_INTERVAL_PREVIEW_MS);
    const pollErrorCountRef = useRef(0);
    const stalePollCountRef = useRef(0);
    const lastProgressSnapshotRef = useRef(null);
    const previewPollBatchRef = useRef(null);
    const updateWizardDataRef = useRef(updateWizardData);
    updateWizardDataRef.current = updateWizardData;

    useSessionLoadGuard(loading);

    const stopPreviewPoll = useCallback(() => {
        previewPollBatchRef.current = null;
        if (pollIntervalRef.current) {
            clearTimeout(pollIntervalRef.current);
            pollIntervalRef.current = null;
        }
    }, []);

    const clearPollTimer = useCallback(() => {
        stopPreviewPoll();
    }, [stopPreviewPoll]);

    const isPreviewProgressComplete = (progressData) => {
        if (!progressData) return false;
        if (progressData.phase === 'preview_done') return true;
        if (progressData.phase === 'preview_failed') return false;
        return (
            progressData.status === 'COMPLETED'
            && Number(progressData.progress_percentage) >= 100
            && progressData.phase === 'done'
        );
    };

    const fetchPreviewResultOnce = useCallback(async (batchId) => {
        const data = await getPreviewResult(batchId);
        if (!data?.validation_summary && !data?.preview_data) {
            throw new Error('Respuesta de vista previa incompleta.');
        }
        return data;
    }, []);

    const applyPreviewData = useCallback((data) => {
        setPreviewData(data);
        updateWizardDataRef.current?.({
            previewData: data,
            validationSummary: data?.validation_summary,
            validatedInPreview: Boolean(data?.validated_in_preview),
        });
    }, []);

    const pollPreviewUntilDone = useCallback(async (batchId) => {
        if (previewPollBatchRef.current === batchId) {
            return;
        }
        stopPreviewPoll();
        previewPollBatchRef.current = batchId;
        pollErrorCountRef.current = 0;
        stalePollCountRef.current = 0;
        lastProgressSnapshotRef.current = null;
        pollDelayRef.current = POLL_INTERVAL_PREVIEW_MS;

        const runPollLoop = async () => {
            if (previewPollBatchRef.current !== batchId) {
                return;
            }

            try {
                const progressData = await getProcessingProgress(batchId);
                if (previewPollBatchRef.current !== batchId) {
                    return;
                }

                setPreviewProgress(progressData);
                pollErrorCountRef.current = 0;
                pollDelayRef.current = resolvePollIntervalMs(progressData, { preview: true });

                const snapshot = previewProgressSnapshot(progressData);
                if (lastProgressSnapshotRef.current === snapshot) {
                    stalePollCountRef.current += 1;
                } else {
                    stalePollCountRef.current = 0;
                    lastProgressSnapshotRef.current = snapshot;
                }

                if (progressData?.phase === 'preview_failed') {
                    stopPreviewPoll();
                    setLoading(false);
                    setError(progressData?.current_operation || 'Error al generar la vista previa.');
                    return;
                }

                if (isPreviewProgressComplete(progressData)) {
                    stopPreviewPoll();
                    const data = await fetchPreviewResultOnce(batchId);
                    applyPreviewData(data);
                    setLoading(false);
                    return;
                }

                if (stalePollCountRef.current >= MAX_STALE_POLLS) {
                    stopPreviewPoll();
                    setLoading(false);
                    setError(
                        'La vista previa dejó de reportar progreso. '
                        + 'Reinicia el backend si hace falta y pulsa Reintentar.',
                    );
                    return;
                }

                try {
                    const data = await fetchPreviewResultOnce(batchId);
                    if (previewPollBatchRef.current !== batchId) {
                        return;
                    }
                    stopPreviewPoll();
                    applyPreviewData(data);
                    setLoading(false);
                    return;
                } catch (resultErr) {
                    if (resultErr.response?.status !== 409) {
                        throw resultErr;
                    }
                }

                pollIntervalRef.current = setTimeout(runPollLoop, pollDelayRef.current);
            } catch (err) {
                if (previewPollBatchRef.current !== batchId) {
                    return;
                }
                console.error('Preview poll error:', err);
                if (err.response?.status === 409) {
                    pollIntervalRef.current = setTimeout(runPollLoop, pollDelayRef.current);
                    return;
                }
                if (isTransientPollError(err)) {
                    pollErrorCountRef.current += 1;
                    pollDelayRef.current = Math.min(
                        pollDelayRef.current * 1.5,
                        POLL_INTERVAL_MAX_MS,
                    );
                    if (pollErrorCountRef.current <= MAX_TRANSIENT_POLL_ERRORS) {
                        pollIntervalRef.current = setTimeout(runPollLoop, pollDelayRef.current);
                        return;
                    }
                }
                stopPreviewPoll();
                setLoading(false);
                const detail = err.response?.data?.detail;
                setError(
                    typeof detail === 'string'
                        ? detail
                        : 'No se pudo completar la vista previa. Verifica que el backend esté activo.',
                );
            }
        };

        pollIntervalRef.current = setTimeout(runPollLoop, pollDelayRef.current);
    }, [applyPreviewData, fetchPreviewResultOnce, stopPreviewPoll]);

    const loadPreview = useCallback(async (batchId, { force = false } = {}) => {
        if (!batchId) {
            setLoading(false);
            setError('No hay batch activo para generar la vista previa.');
            return;
        }

        if (!force && previewInitInflight.has(batchId)) {
            await previewInitInflight.get(batchId);
            return;
        }

        const runLoad = async () => {
            try {
                setLoading(true);
                setError('');
                setPreviewProgress(null);
                stopPreviewPoll();

                const { status, data } = await startPreview(batchId, { force });

                if (status === 200 && data?.validation_summary) {
                    stopPreviewPoll();
                    applyPreviewData(data);
                    setLoading(false);
                    return;
                }

                await pollPreviewUntilDone(batchId);
            } catch (err) {
                console.error('Preview Load Error:', err);
                stopPreviewPoll();
                const detail = err.response?.data?.detail;
                if (detail) {
                    setError(typeof detail === 'string' ? detail : JSON.stringify(detail));
                } else {
                    setError('No se pudo generar la vista previa. Verifica que el backend esté activo.');
                }
                setLoading(false);
            }
        };

        if (force) {
            previewInitInflight.delete(batchId);
        }

        const loadPromise = runLoad();
        previewInitInflight.set(batchId, loadPromise);
        try {
            await loadPromise;
        } finally {
            if (previewInitInflight.get(batchId) === loadPromise) {
                previewInitInflight.delete(batchId);
            }
        }
    }, [applyPreviewData, pollPreviewUntilDone, stopPreviewPoll]);

    useEffect(() => {
        const batchId = wizardData?.batchId;
        if (!batchId) return undefined;

        loadPreview(batchId);

        return () => {
            stopPreviewPoll();
        };
        // loadPreview/stopPreviewPoll are estabilizados con refs; solo reaccionar al batch.
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [wizardData?.batchId]);

    const val = previewData?.validation_summary || {};
    const loadMode = previewData?.load_type || wizardData?.loadMode || 'history';
    const isCatalog = loadMode === 'catalog';
    const processType = previewData?.process_type || wizardData?.processType || '';
    const catalogBlocked = false;

    const sourceExtension =
        previewData?.source_extension ||
        wizardData?.fileName?.split('.').pop()?.toLowerCase() ||
        '';

    const displayPreviewRows = useMemo(() => {
        const raw = previewData?.preview_data || [];
        if (isCatalog) return raw;
        return enrichHistoryPreviewRows(raw, {
            processType,
            sourceExtension,
            organizationId: user?.organization_id || wizardData.organizationId,
        });
    }, [
        previewData?.preview_data,
        isCatalog,
        processType,
        sourceExtension,
        user?.organization_id,
        wizardData.organizationId,
    ]);

    const previewColumnKeys = useMemo(() => {
        if (!displayPreviewRows.length) return [];
        return isCatalog
            ? Object.keys(displayPreviewRows[0])
            : getHistoryPreviewColumnKeys(displayPreviewRows);
    }, [displayPreviewRows, isCatalog]);

    const formatPreviewColumnLabel = (key) => {
        if (key === 'organization_id') {
            return 'Organización';
        }
        if (key === 'sales_channel') {
            return 'Canal (sales_channel)';
        }
        return key;
    };

    const formatPreviewCellValue = (key, cellVal) => {
        if (key === 'organization_id' && organizationDisplayName) {
            return organizationDisplayName;
        }
        return cellVal !== null && cellVal !== undefined ? String(cellVal) : '';
    };

    const formatMetric = (value) => {
        if (value === null || value === undefined || Number.isNaN(Number(value))) {
            return '0';
        }
        return Number(value).toLocaleString('es-MX');
    };

    const handleDownloadRejected = async () => {
        if (!wizardData?.batchId || downloadingRejected) {
            return;
        }
        try {
            setDownloadingRejected(true);
            await downloadRejectedRecords(wizardData.batchId);
        } catch (err) {
            console.error('Download failed', err);
            const message = err?.message || err.response?.data?.detail || 'Error desconocido';
            alert(`No se pudo descargar rechazados: ${message}`);
        } finally {
            setDownloadingRejected(false);
        }
    };

    const validRows = val.valid_rows ?? val.df_after_dropna ?? val.total_rows;
    const rejectedRows = val.rejected_rows ?? val.dropped_rows ?? 0;
    const productionRows = val.grouped_rows ?? validRows;
    const canContinue = !val.has_error && (validRows > 0);
    const qtyIntegrityOk = Math.abs(val.diff_qty || 0) <= 0.001;
    const totalIntegrityOk = Math.abs(val.diff_total || 0) <= 0.001;
    const locIntegrityOk = (val.loc_diff_count || 0) === 0;
    const skuIntegrityOk = (val.dmd_unit_diff_count || 0) === 0;

    const targetTableName =
        previewData?.target_table ||
        wizardData?.selectedTable ||
        wizardData?.catalogTable ||
        '-';

    if (loading) {
        const pct = Math.min(100, Math.max(0, Number(previewProgress?.progress_percentage) || 0));
        const operation = previewProgress?.current_operation || 'Generando vista previa del mapeo…';
        const processed = previewProgress?.processed_rows ?? 0;
        const total = previewProgress?.total_rows ?? 0;
        const showRowCounts = total > 0;

        return (
            <div className="step3-loading">
                <LoadingSpinner />
                <p>{operation}</p>
                <div className="step3-progress">
                    <div className="step3-progress__bar">
                        <div
                            className="step3-progress__fill"
                            style={{ width: `${pct}%` }}
                        />
                    </div>
                    {showRowCounts && (
                        <p className="step3-progress__rows">
                            {formatNumber(processed)} de {formatNumber(total)} filas
                        </p>
                    )}
                </div>
                <p className="step3-loading__hint">
                    Archivos grandes pueden tardar varios minutos. Puedes dejar esta ventana abierta.
                </p>
            </div>
        );
    }

    if (error) {
        return (
            <div className="step3-error">
                <div className="error-icon">⚠</div>
                <h3>Error al generar la vista previa</h3>
                <p>{error}</p>
                <div className="error-actions">
                    <Button variant="secondary" onClick={prevStep}>
                        ← Volver al mapeo
                    </Button>
                    <Button variant="primary" onClick={() => {
                        const batchId = wizardData?.batchId;
                        if (batchId) {
                            previewInitInflight.delete(batchId);
                        }
                        stopPreviewPoll();
                        loadPreview(wizardData?.batchId, { force: true });
                    }}>
                        Reintentar
                    </Button>
                </div>
            </div>
        );
    }

    if (!previewData) {
        return (
            <div className="step3-error">
                <div className="error-icon">⚠</div>
                <h3>No Data Available</h3>
                <p>Preview data could not be loaded.</p>
                <div className="error-actions">
                    <Button variant="secondary" onClick={prevStep}>
                        ← Back to Mapping
                    </Button>
                    <Button variant="primary" onClick={() => {
                        const batchId = wizardData?.batchId;
                        if (batchId) {
                            previewInitInflight.delete(batchId);
                        }
                        stopPreviewPoll();
                        loadPreview(wizardData?.batchId, { force: true });
                    }}>
                        Try Again
                    </Button>
                </div>
            </div>
        );
    }

    return (
        <div className="step3-preview">
            <h2>{isCatalog ? 'Paso 3: Vista previa del mapeo' : 'Paso 3: Vista previa y agregación'}</h2>
            <p className="step-description">
                {isCatalog
                    ? 'Revisa cómo quedarán los datos tras el mapeo. La validación contra la tabla destino se hará en el siguiente paso, antes de promover a producción.'
                    : 'Validación completa sobre todas las filas del archivo, descarga de rechazados, agregación weekly/monthly y vista previa del resultado.'}
            </p>

            {isCatalog ? (
                <div className="catalog-preview-summary">
                    <div className="validation-alert info catalog-preview-hint">
                        Las comprobaciones de formato, tipos, enums y duplicados se ejecutan al procesar
                        el archivo. Podrás descargar los registros rechazados para corregirlos.
                    </div>
                    <div className="summary-card">
                        <div className="card-label">Filas en archivo</div>
                        <span className="value">{val.total_rows?.toLocaleString() || 0}</span>
                    </div>
                    <div className="summary-card summary-card--target">
                        <div className="card-label">Tabla destino</div>
                        <span className="value value--table">{targetTableName}</span>
                    </div>
                </div>
            ) : (
                <>
                    {val.has_error && (
                        <div className="validation-alert error">
                            ⚠ {val.error_detail}
                        </div>
                    )}
                    <div className="history-metrics-panel">
                        <div className="history-metrics-panel__header">
                            <h3 className="history-metrics-panel__title">Resumen de agregación</h3>
                            <div className="history-metrics-panel__badges">
                                {val.compression_factor > 1 && (
                                    <span className="metric-chip metric-chip--info">
                                        Compresión {val.compression_factor}x
                                    </span>
                                )}
                                <span
                                    className={`metric-chip ${
                                        qtyIntegrityOk && totalIntegrityOk
                                            ? 'metric-chip--success'
                                            : 'metric-chip--danger'
                                    }`}
                                >
                                    {qtyIntegrityOk && totalIntegrityOk
                                        ? 'Integridad OK'
                                        : 'Revisar integridad'}
                                </span>
                            </div>
                        </div>

                        <div className="history-kpi-grid">
                            <article className="history-kpi history-kpi--filas">
                                <span className="history-kpi__label">Filas</span>
                                <div className="history-kpi__flow history-kpi__flow--prod">
                                    <div className="step3-prod-summary step3-prod-summary--inline step3-prod-summary--source">
                                        <p className="step3-prod-summary__hint">
                                            Filas del archivo original antes de agregación.
                                        </p>
                                        <div className="step3-prod-summary__value">
                                            <span className="step3-prod-summary__label">Originales</span>
                                            <strong>{formatMetric(val.total_rows)}</strong>
                                        </div>
                                    </div>
                                    <span
                                        className="history-kpi__arrow history-kpi__arrow--prominent"
                                        aria-hidden="true"
                                    >
                                        →
                                    </span>
                                    <div className="step3-prod-summary step3-prod-summary--inline step3-prod-summary--success">
                                        <p className="step3-prod-summary__hint">
                                            Total final que se cargará a producción en el siguiente paso.
                                        </p>
                                        <div className="step3-prod-summary__value">
                                            <span className="step3-prod-summary__label">A producción</span>
                                            <strong>{formatMetric(productionRows)}</strong>
                                        </div>
                                    </div>
                                </div>
                            </article>

                            {val.orig_total > 0 && (
                                <article className={`history-kpi ${!totalIntegrityOk ? 'history-kpi--warn' : ''}`}>
                                    <span className="history-kpi__label">Monto total</span>
                                    <div className="history-kpi__flow">
                                        <div className="history-kpi__value-block">
                                            <strong>${formatMetric(val.orig_total)}</strong>
                                            <small>original</small>
                                        </div>
                                        <span className="history-kpi__arrow" aria-hidden="true">→</span>
                                        <div className="history-kpi__value-block">
                                            <strong>${formatMetric(val.agg_total)}</strong>
                                            <small>agrupado</small>
                                        </div>
                                    </div>
                                    {!totalIntegrityOk && (
                                        <span className="history-kpi__delta history-kpi__delta--danger">
                                            Δ ${formatMetric(val.diff_total)}
                                        </span>
                                    )}
                                </article>
                            )}
                        </div>
                    </div>

                    <div className="validation-report validation-report--compact">
                        <div className="validation-report__header">
                            <h4 className="validation-report__title">Detalle de validación y agregación</h4>
                            <span className="validation-report__subtitle">
                                {processType === 'Monthly' ? 'Agrupación mensual' : 'Agrupación semanal'}
                            </span>
                        </div>

                        <div className="validation-report__sections">
                            {rejectedRows > 0 && (
                                <section className="report-section report-section--validation">
                                    <h5 className="report-section__title">Validación</h5>
                                    <dl className="report-dl">
                                        <div className="report-dl__row report-dl__row--rejected">
                                            <dt>Rechazadas</dt>
                                            <dd>{formatMetric(rejectedRows)}</dd>
                                        </div>
                                    </dl>
                                    <div className="step3-rejected-download">
                                        <Button
                                            variant="danger"
                                            size="sm"
                                            onClick={handleDownloadRejected}
                                            disabled={downloadingRejected}
                                            className="step3-rejected-download__btn"
                                        >
                                            {downloadingRejected
                                                ? 'Preparando descarga…'
                                                : 'Descargar rechazados (.csv)'}
                                        </Button>
                                    </div>
                                </section>
                            )}

                            <section className="report-section">
                                <h5 className="report-section__title">Agregación</h5>
                                <dl className="report-dl">
                                    <div className="report-dl__row">
                                        <dt>Filas consolidadas</dt>
                                        <dd>{formatMetric(val.grouped_rows)}</dd>
                                    </div>
                                    <div className="report-dl__row report-dl__row--success">
                                        <dt>Filas comprimidas</dt>
                                        <dd>−{formatMetric(val.consolidated_rows)}</dd>
                                    </div>
                                    <div className="report-dl__row">
                                        <dt>Factor de compresión</dt>
                                        <dd>
                                            <span className="report-pill">{val.compression_factor || 1}x</span>
                                        </dd>
                                    </div>
                                </dl>
                            </section>

                            <section className="report-section">
                                <h5 className="report-section__title">Integridad</h5>
                                <dl className="report-dl">
                                    <div className="report-dl__row">
                                        <dt>Sumatorias totales</dt>
                                        <dd>
                                            <span
                                                className={`report-status ${
                                                    qtyIntegrityOk ? 'success' : 'error'
                                                }`}
                                            >
                                                {qtyIntegrityOk
                                                    ? 'Sin diferencias'
                                                    : `Δ ${formatMetric(val.diff_qty)}`}
                                            </span>
                                        </dd>
                                    </div>
                                    <div className="report-dl__row">
                                        <dt>Sumatorias por locación</dt>
                                        <dd>
                                            <span
                                                className={`report-status ${
                                                    locIntegrityOk ? 'success' : 'error'
                                                }`}
                                            >
                                                {locIntegrityOk
                                                    ? 'Sin diferencias'
                                                    : `${val.loc_diff_count} anomalías`}
                                            </span>
                                        </dd>
                                    </div>
                                    <div className="report-dl__row">
                                        <dt>Sumatorias por producto</dt>
                                        <dd>
                                            <span
                                                className={`report-status ${
                                                    skuIntegrityOk ? 'success' : 'error'
                                                }`}
                                            >
                                                {skuIntegrityOk
                                                    ? 'Sin diferencias'
                                                    : `${val.dmd_unit_diff_count} anomalías`}
                                            </span>
                                        </dd>
                                    </div>
                                </dl>
                            </section>
                        </div>
                    </div>
                </>
            )}

            {/* Preview Table */}
            {displayPreviewRows.length > 0 ? (
                <DataTableShell
                    title={isCatalog ? 'Vista previa (primeras 20 filas)' : 'Vista previa (primeras 20 filas agregadas)'}
                    meta={`${displayPreviewRows.length} filas · ${previewColumnKeys.length} columnas`}
                    maxHeight="400px"
                >
                    <DataTable>
                        <DataTableHead>
                            <tr>
                                <DataTableTh className="w-10 text-center">#</DataTableTh>
                                {previewColumnKeys.map((key) => (
                                    <DataTableTh key={key}>{formatPreviewColumnLabel(key)}</DataTableTh>
                                ))}
                            </tr>
                        </DataTableHead>
                        <DataTableBody>
                            {displayPreviewRows.map((row, index) => (
                                <DataTableRow key={index}>
                                    <DataTableRowNum>{index + 1}</DataTableRowNum>
                                    {previewColumnKeys.map((key) => {
                                        const cellVal = row[key];
                                        const display = formatPreviewCellValue(key, cellVal);
                                        const isEmpty = !display;
                                        return (
                                            <DataTableTd key={key} title={display || undefined} empty={isEmpty}>
                                                {isEmpty ? EMPTY : display}
                                            </DataTableTd>
                                        );
                                    })}
                                </DataTableRow>
                            ))}
                        </DataTableBody>
                    </DataTable>
                </DataTableShell>
            ) : (
                <DataTableShell
                    empty
                    emptyTitle="Vista previa no disponible"
                    emptyDescription={`Tipo de preview_data: ${typeof previewData?.preview_data}`}
                />
            )}

            <div className="step-actions">
                <Button variant="secondary" onClick={prevStep}>
                    ← Back to Mapping
                </Button>
                <Button
                    variant="primary"
                    onClick={nextStep}
                    disabled={catalogBlocked || (!isCatalog && !canContinue)}
                    title={
                        catalogBlocked
                            ? 'Corrige los errores de validación antes de continuar'
                            : !canContinue
                              ? 'No hay filas válidas para continuar'
                              : undefined
                    }
                >
                    {catalogBlocked
                        ? 'Corrija errores para continuar'
                        : isCatalog
                          ? 'Procesar y validar →'
                          : 'Cargar a producción →'}
                </Button>
            </div>
        </div>
    );
};

export default Step3Preview;
