import React, { useState, useEffect } from 'react';
import { generatePreview } from '../../services/wizardService';
import Button from '../Button';
import LoadingSpinner from '../LoadingSpinner';
import './Step3Preview.css';

const Step3Preview = ({ wizardData, updateWizardData, nextStep, prevStep }) => {
    const [previewData, setPreviewData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');

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
            setError(err.response?.data?.detail || 'Failed to generate preview');
        } finally {
            setLoading(false);
        }
    };

    const val = previewData?.validation_summary || {};
    const processType = previewData?.process_type || 'Other';

    if (loading) {
        return (
            <div className="step3-loading">
                <LoadingSpinner />
                <p>Generating preview and validating data...</p>
            </div>
        );
    }

    if (error) {
        return (
            <div className="step3-error">
                <div className="error-icon">⚠</div>
                <h3>Preview Generation Failed</h3>
                <p>{error}</p>
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
            <h2>Step 3: Preview & Validate</h2>
            <p className="step-description">
                Review transformed data and validation results before continuing.
            </p>

            {/* Validation Dashboard */}
            {processType !== 'Other' ? (
                <>
                    {val.has_error && (
                        <div className="validation-alert error">
                            ⚠ Error de Validación: {val.error_detail}
                        </div>
                    )}
                    <div className="preview-summary validation-grid">
                        <div className="summary-card stat-pair">
                            <div className="card-label">Filas</div>
                            <div className="stat-compare">
                                <div className="stat-box">
                                    <span className="value">{val.total_rows?.toLocaleString() || 0}</span>
                                    <span className="label">Originales</span>
                                </div>
                                <span className="arrow">→</span>
                                <div className="stat-box">
                                    <span className="value">{val.grouped_rows?.toLocaleString() || 0}</span>
                                    <span className="label">Agrupadas</span>
                                </div>
                            </div>
                        </div>

                        <div className={`summary-card stat-pair ${val.diff_qty !== 0 ? 'error-state' : ''}`}>
                            <div className="card-label">Cantidades (QTY)</div>
                            <div className="stat-compare">
                                <div className="stat-box">
                                    <span className="value">{val.orig_qty?.toLocaleString() || 0}</span>
                                    <span className="label">Original</span>
                                </div>
                                <span className="arrow">→</span>
                                <div className="stat-box">
                                    <span className="value">{val.agg_qty?.toLocaleString() || 0}</span>
                                    <span className="label">Agrupado</span>
                                </div>
                            </div>
                            {val.diff_qty !== 0 && (
                                <div className="diff-alert">
                                    Diferencia: {val.diff_qty}
                                </div>
                            )}
                        </div>

                        {val.orig_total > 0 && (
                            <div className={`summary-card stat-pair ${Math.abs(val.diff_total || 0) > 0.001 ? 'error-state' : ''}`}>
                                <div className="card-label">Montos (Total Price)</div>
                                <div className="stat-compare">
                                    <div className="stat-box">
                                        <span className="value">${val.orig_total?.toLocaleString() || 0}</span>
                                        <span className="label">Original</span>
                                    </div>
                                    <span className="arrow">→</span>
                                    <div className="stat-box">
                                        <span className="value">${val.agg_total?.toLocaleString() || 0}</span>
                                        <span className="label">Agrupado</span>
                                    </div>
                                </div>
                                {Math.abs(val.diff_total || 0) > 0.001 && (
                                    <div className="diff-alert">
                                        Diferencia: ${val.diff_total}
                                    </div>
                                )}
                            </div>
                        )}
                    </div>

                    {/* Detailed Validation Report */}
                    <div className="validation-report">
                        <h4 className="report-title">Reporte de Agregación y Validaciones (Basado en weekly.py)</h4>
                        <div className="report-grid">
                            <div className="report-item">
                                <span className="report-label">Filas Originales Previas a Limpieza (Drop NA):</span>
                                <span className="report-value">{val.df_before_dropna?.toLocaleString() || val.total_rows?.toLocaleString() || 0}</span>
                            </div>
                            <div className="report-item text-danger">
                                <span className="report-label">Filas Eliminadas por Nulos en Columnas Requeridas:</span>
                                <span className="report-value">- {val.dropped_rows?.toLocaleString() || 0}</span>
                            </div>
                            <div className="report-item">
                                <span className="report-label">Filas Limpias Efectivas previas al agrupamiento:</span>
                                <span className="report-value">{val.df_after_dropna?.toLocaleString() || val.total_rows?.toLocaleString() || 0}</span>
                            </div>

                            <hr className="report-divider" />

                            <div className="report-item">
                                <span className="report-label">Total de Filas Consolidadas post-agrupamiento:</span>
                                <span className="report-value">{val.grouped_rows?.toLocaleString() || 0}</span>
                            </div>
                            <div className="report-item text-success">
                                <span className="report-label">Ahorro de Filas (Filas Comprimidas):</span>
                                <span className="report-value">- {val.consolidated_rows?.toLocaleString() || 0}</span>
                            </div>
                            <div className="report-item text-info">
                                <span className="report-label">Factor métrico de compresión:</span>
                                <span className="report-value badge">{val.compression_factor || 1}x</span>
                            </div>

                            <hr className="report-divider" />

                            <div className="report-item">
                                <span className="report-label">Validación de Integridad de Sumatorias por Location (Loc):</span>
                                <span className={`report-status ${val.loc_diff_count === 0 ? 'success' : 'error'}`}>
                                    {val.loc_diff_count === 0 ? 'OK ✓ No hay diferencias' : `${val.loc_diff_count} anomalías detectadas ⚠`}
                                </span>
                            </div>
                            <div className="report-item">
                                <span className="report-label">Validación de Integridad de Sumatorias por Producto (dmd_unit):</span>
                                <span className={`report-status ${val.dmd_unit_diff_count === 0 ? 'success' : 'error'}`}>
                                    {val.dmd_unit_diff_count === 0 ? 'OK ✓ No hay diferencias' : `${val.dmd_unit_diff_count} anomalías detectadas ⚠`}
                                </span>
                            </div>
                        </div>
                    </div>
                </>
            ) : (
                <div className="preview-summary validation-grid">
                    <div className="summary-card stat-pair">
                        <div className="card-label">Modo: Other (Carga Directa)</div>
                        <div className="stat-compare">
                            <div className="stat-box">
                                <span className="value">{val.total_rows?.toLocaleString() || 0}</span>
                                <span className="label">Originales</span>
                            </div>
                            <span className="arrow">→</span>
                            <div className="stat-box">
                                <span className="value">0</span>
                                <span className="label">Agrupadas</span>
                            </div>
                        </div>
                    </div>
                </div>
            )}

            {/* Preview Table */}
            {previewData?.preview_data && previewData.preview_data.length > 0 ? (
                <div className="preview-table-container" style={{ marginTop: '2rem' }}>
                    <h3>Data Preview (First 20 Aggregated Rows)</h3>
                    <div className="table-wrapper">
                        <table className="preview-table">
                            <thead>
                                <tr>
                                    {Object.keys(previewData.preview_data[0]).map((key) => (
                                        <th key={key}>{key}</th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody>
                                {previewData.preview_data.map((row, index) => (
                                    <tr key={index}>
                                        {Object.values(row).map((val, i) => (
                                            <td key={i}>{val !== null ? String(val) : ''}</td>
                                        ))}
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            ) : (
                <div className="preview-table-container" style={{ marginTop: '2rem', padding: '1rem', background: '#ffebee', color: '#c62828', borderRadius: '4px' }}>
                    <h3>Data Preview Not Available</h3>
                    <p>Debug info: previewData.preview_data type is {typeof previewData?.preview_data}</p>
                    <pre style={{ maxWidth: '100%', overflow: 'auto' }}>{JSON.stringify(previewData, null, 2)}</pre>
                </div>
            )}

            {/* Target Info */}
            <div className="target-info">
                <div className="info-row">
                    <span className="info-label">Target Schema:</span>
                    <span className="info-value">{previewData.target_schema || '-'}</span>
                </div>
                <div className="info-row">
                    <span className="info-label">Target Table:</span>
                    <span className="info-value">{previewData.target_table || '-'}</span>
                </div>
                <div className="info-row">
                    <span className="info-label">Staging Table:</span>
                    <span className="info-value">stage_{previewData.staging_table || '-'}</span>
                </div>
            </div>

            <div className="step-actions">
                <Button variant="secondary" onClick={prevStep}>
                    ← Back to Mapping
                </Button>
                <Button
                    variant="primary"
                    onClick={nextStep}
                >
                    Confirm & Process →
                </Button>
            </div>
        </div>
    );
};

export default Step3Preview;
