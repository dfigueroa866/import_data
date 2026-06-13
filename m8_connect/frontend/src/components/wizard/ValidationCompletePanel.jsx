import React, { useState } from 'react';
import { Button } from '../ui';
import { formatNumber } from '../../lib/format';
import './Step3Preview.css';

const formatMetric = (value) => {
    if (value === null || value === undefined || Number.isNaN(Number(value))) {
        return '0';
    }
    return Number(value).toLocaleString('es-MX');
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
                        complete ? 'step4-live__bar-fill--success' : 'step4-live__bar-fill--rows',
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

/**
 * Pantalla unificada de validación completa (historia paso 3 / catálogos paso 4).
 * Solo presentación: cada flujo alimenta sus propias métricas.
 */
const ValidationCompletePanel = ({
    totalRows = 0,
    validRows = 0,
    rejectedRows = 0,
    reportSubtitle = '',
    promoteError = '',
    promoting = false,
    onPromote,
    onDownloadRejected,
    onNavigateBatches,
    onNewUpload,
}) => {
    const [downloadingRejected, setDownloadingRejected] = useState(false);
    const validationOk = rejectedRows === 0 && validRows > 0;

    const handleDownloadRejected = async () => {
        if (downloadingRejected) return;
        try {
            setDownloadingRejected(true);
            await onDownloadRejected?.();
        } finally {
            setDownloadingRejected(false);
        }
    };

    return (
        <div className="step4-live">
            <div className="step4-live__hero">
                <div className="step4-live__hero-text">
                    <h2 className="step4-live__title">Proceso de validación completo</h2>
                    <p className="step4-live__subtitle">
                        Revisa el resultado antes de cargar a producción.
                    </p>
                </div>
                <ProgressBar pct={100} label="Completo" complete />
            </div>

            <div className="history-metrics-panel validation-complete-panel__metrics">
                <div className="history-metrics-panel__header">
                    <h3 className="history-metrics-panel__title">Resumen de validación</h3>
                    <div className="history-metrics-panel__badges">
                        <span
                            className={`metric-chip ${
                                validationOk ? 'metric-chip--success' : 'metric-chip--danger'
                            }`}
                        >
                            {validationOk ? 'Validación OK' : 'Revisar rechazados'}
                        </span>
                    </div>
                </div>

                <div className="history-kpi-grid">
                    <article className="history-kpi history-kpi--filas">
                        <span className="history-kpi__label">Filas</span>
                        <div className="history-kpi__flow history-kpi__flow--prod">
                            <div className="step3-prod-summary step3-prod-summary--inline step3-prod-summary--source">
                                <p className="step3-prod-summary__hint">
                                    Total de filas procesadas en el archivo.
                                </p>
                                <div className="step3-prod-summary__value">
                                    <span className="step3-prod-summary__label">Total</span>
                                    <strong>{formatMetric(totalRows)}</strong>
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
                                    Registros que pasaron validación y se cargarán a producción.
                                </p>
                                <div className="step3-prod-summary__value">
                                    <span className="step3-prod-summary__label">A producción</span>
                                    <strong>{formatMetric(validRows)}</strong>
                                </div>
                            </div>
                        </div>
                    </article>
                </div>
            </div>

            <div className="validation-report validation-report--compact validation-complete-panel__report">
                <div className="validation-report__header">
                    <h4 className="validation-report__title">Detalle de validación</h4>
                    {reportSubtitle ? (
                        <span className="validation-report__subtitle">{reportSubtitle}</span>
                    ) : null}
                </div>

                <div className="validation-report__sections">
                    <section className="report-section report-section--validation">
                        <h5 className="report-section__title">Validación</h5>
                        <dl className="report-dl">
                            <div className="report-dl__row report-dl__row--success">
                                <dt>Válidas</dt>
                                <dd>{formatMetric(validRows)}</dd>
                            </div>
                            <div className="report-dl__row report-dl__row--rejected">
                                <dt>Rechazadas</dt>
                                <dd>{formatMetric(rejectedRows)}</dd>
                            </div>
                        </dl>
                        {rejectedRows > 0 && (
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
                        )}
                    </section>
                </div>
            </div>

            <div className="step4-live__body">
                {promoteError && (
                    <div className="promotion-error">
                        <span className="icon">⛔</span>
                        {promoteError}
                    </div>
                )}

                <p className="tab-pane__desc">
                    {validRows > 0
                        ? 'Pasaron validaciones de formato y tipo. Carga a producción cuando estés listo.'
                        : 'No hay filas válidas para cargar. Descarga los rechazados, corrígelos y vuelve a intentar.'}
                </p>

                <div className="step4-completed__actions">
                    <Button
                        variant="primary"
                        size="lg"
                        className="step4-btn-promote"
                        onClick={onPromote}
                        disabled={promoting || validRows === 0}
                    >
                        Cargar a producción
                    </Button>
                </div>
            </div>

            <footer className="step4-live__footer">
                <Button variant="secondary" onClick={onNavigateBatches}>
                    Ver batches
                </Button>
                <Button variant="secondary" onClick={onNewUpload}>
                    Nueva carga
                </Button>
            </footer>
        </div>
    );
};

export default ValidationCompletePanel;
