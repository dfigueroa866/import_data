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
            <h2>{isCatalog ? 'Paso 3: Vista previa del mapeo' : 'Step 3: Preview & Validate'}</h2>
            <p className="step-description">
                {isCatalog
                    ? 'Revisa cómo quedarán los datos tras el mapeo. La validación contra la tabla destino se hará en el siguiente paso, antes de promover a producción.'
                    : 'Review transformed data and validation results before continuing.'}
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
