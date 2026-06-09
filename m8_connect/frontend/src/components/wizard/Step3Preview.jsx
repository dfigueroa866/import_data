import React, { useState, useEffect, useMemo } from 'react';
import { generatePreview } from '../../services/wizardService';
import { useAuth } from '../../context/AuthContext';
import useSessionLoadGuard from '../../hooks/useSessionLoadGuard';
import Button from '../Button';
import LoadingSpinner from '../LoadingSpinner';
import {
    enrichHistoryPreviewRows,
    getHistoryPreviewColumnKeys,
} from '../../constants/historyConfig';
import './Step3Preview.css';

const Step3Preview = ({ wizardData, updateWizardData, nextStep, prevStep }) => {
    const { user } = useAuth();
    const [previewData, setPreviewData] = useState(null);

    const organizationDisplayName =
        previewData?.organization_name ||
        user?.organization_name ||
        wizardData.organizationName ||
        '';
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');

    useSessionLoadGuard(loading);

    useEffect(() => {
        loadPreview();
    }, []);

    const loadPreview = async () => {
        try {
            setLoading(true);
            setError('');
            const data = await generatePreview(wizardData.batchId);
            console.log("Preview Data Loaded:", data); // Keep log for safety
            setPreviewData(data);

            if (updateWizardData) {
                updateWizardData({
                    previewData: data,
                    validationSummary: data?.validation_summary
                });
            }
        } catch (err) {
            console.error("Preview Load Error:", err);
            const detail = err.response?.data?.detail;
            if (err.code === 'ECONNABORTED') {
                setError(
                    'La vista previa tardó demasiado (archivo muy grande). '
                    + 'Intenta de nuevo o reduce el tamaño del archivo.'
                );
            } else if (detail) {
                setError(typeof detail === 'string' ? detail : JSON.stringify(detail));
            } else {
                setError('No se pudo generar la vista previa. Verifica que el backend esté activo.');
            }
        } finally {
            setLoading(false);
        }
    };

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

    const rowsSaved = Math.max(0, (val.total_rows || 0) - (val.grouped_rows || 0));
    const qtyIntegrityOk = (val.diff_qty || 0) === 0;
    const totalIntegrityOk = Math.abs(val.diff_total || 0) <= 0.001;
    const locIntegrityOk = (val.loc_diff_count || 0) === 0;
    const skuIntegrityOk = (val.dmd_unit_diff_count || 0) === 0;

    const targetTableName =
        previewData?.target_table ||
        wizardData?.selectedTable ||
        wizardData?.catalogTable ||
        '-';

    if (loading) {
        return (
            <div className="step3-loading">
                <LoadingSpinner />
                <p>Generando vista previa del mapeo…</p>
                <p className="step3-loading__hint">
                    Archivos grandes pueden tardar varios minutos. No cierres esta ventana.
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
                    <Button variant="primary" onClick={loadPreview}>
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
                    <Button variant="primary" onClick={loadPreview}>
                        Try Again
                    </Button>
                </div>
            </div>
        );
    }

    return (
        <div className="step3-preview">
            <h2>{isCatalog ? 'Paso 3: Vista previa del mapeo' : 'Paso 3: Vista previa y validación'}</h2>
            <p className="step-description">
                {isCatalog
                    ? 'Revisa cómo quedarán los datos tras el mapeo. La validación contra la tabla destino se hará en el siguiente paso, antes de promover a producción.'
                    : 'Revisa la agregación, integridad de cantidades y una muestra de filas antes de procesar.'}
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
                            ⚠ Error de Validación: {val.error_detail}
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
                            <article className="history-kpi">
                                <span className="history-kpi__label">Filas</span>
                                <div className="history-kpi__flow">
                                    <div className="history-kpi__value-block">
                                        <strong>{formatMetric(val.total_rows)}</strong>
                                        <small>originales</small>
                                    </div>
                                    <span className="history-kpi__arrow" aria-hidden="true">→</span>
                                    <div className="history-kpi__value-block history-kpi__value-block--accent">
                                        <strong>{formatMetric(val.grouped_rows)}</strong>
                                        <small>agrupadas</small>
                                    </div>
                                </div>
                                {rowsSaved > 0 && (
                                    <span className="history-kpi__delta">
                                        −{formatMetric(rowsSaved)} filas consolidadas
                                    </span>
                                )}
                            </article>

                            <article className={`history-kpi ${!qtyIntegrityOk ? 'history-kpi--warn' : ''}`}>
                                <span className="history-kpi__label">Cantidad (QTY)</span>
                                <div className="history-kpi__flow">
                                    <div className="history-kpi__value-block">
                                        <strong>{formatMetric(val.orig_qty)}</strong>
                                        <small>original</small>
                                    </div>
                                    <span className="history-kpi__arrow" aria-hidden="true">→</span>
                                    <div className="history-kpi__value-block">
                                        <strong>{formatMetric(val.agg_qty)}</strong>
                                        <small>agrupado</small>
                                    </div>
                                </div>
                                {!qtyIntegrityOk && (
                                    <span className="history-kpi__delta history-kpi__delta--danger">
                                        Δ {formatMetric(val.diff_qty)}
                                    </span>
                                )}
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
                            <h4 className="validation-report__title">Detalle de validaciones</h4>
                            <span className="validation-report__subtitle">
                                Pipeline weekly · {processType || 'Weekly'}
                            </span>
                        </div>

                        <div className="validation-report__sections">
                            <section className="report-section">
                                <h5 className="report-section__title">Limpieza</h5>
                                <dl className="report-dl">
                                    <div className="report-dl__row">
                                        <dt>Filas antes de drop NA</dt>
                                        <dd>{formatMetric(val.df_before_dropna ?? val.total_rows)}</dd>
                                    </div>
                                    <div className="report-dl__row report-dl__row--muted">
                                        <dt>Eliminadas por nulos</dt>
                                        <dd>−{formatMetric(val.dropped_rows)}</dd>
                                    </div>
                                    <div className="report-dl__row">
                                        <dt>Filas limpias</dt>
                                        <dd>{formatMetric(val.df_after_dropna ?? val.total_rows)}</dd>
                                    </div>
                                </dl>
                            </section>

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
                <div className="preview-table-container">
                    <div className="preview-table-header">
                        <h3>
                            {isCatalog
                                ? 'Vista previa (primeras 20 filas)'
                                : 'Data Preview (First 20 Aggregated Rows)'}
                        </h3>
                        <span className="preview-table-meta">
                            {displayPreviewRows.length} filas · {previewColumnKeys.length} columnas
                        </span>
                    </div>
                    <div className="table-wrapper">
                        <table className="preview-table">
                            <thead>
                                <tr>
                                    <th className="preview-table__row-num">#</th>
                                    {previewColumnKeys.map((key) => (
                                        <th key={key}>{formatPreviewColumnLabel(key)}</th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody>
                                {displayPreviewRows.map((row, index) => (
                                    <tr key={index}>
                                        <td className="preview-table__row-num">{index + 1}</td>
                                        {previewColumnKeys.map((key) => {
                                            const cellVal = row[key];
                                            const display = formatPreviewCellValue(key, cellVal);
                                            const isEmpty = !display;
                                            return (
                                                <td
                                                    key={key}
                                                    title={display || undefined}
                                                    className={isEmpty ? 'preview-table__empty' : ''}
                                                >
                                                    {isEmpty ? '—' : display}
                                                </td>
                                            );
                                        })}
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            ) : (
                <div className="preview-table-container preview-table-container--empty">
                    <h3>Data Preview Not Available</h3>
                    <p>Debug info: previewData.preview_data type is {typeof previewData?.preview_data}</p>
                    <pre style={{ maxWidth: '100%', overflow: 'auto' }}>{JSON.stringify(previewData, null, 2)}</pre>
                </div>
            )}

            <div className="step-actions">
                <Button variant="secondary" onClick={prevStep}>
                    ← Back to Mapping
                </Button>
                <Button
                    variant="primary"
                    onClick={nextStep}
                    disabled={catalogBlocked}
                    title={
                        catalogBlocked
                            ? 'Corrige los errores de validación antes de continuar'
                            : undefined
                    }
                >
                    {catalogBlocked ? 'Corrija errores para continuar' : isCatalog ? 'Procesar y validar →' : 'Confirmar y procesar →'}
                </Button>
            </div>
        </div>
    );
};

export default Step3Preview;
