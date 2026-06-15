import React, { useState, useEffect } from 'react';
import {
    uploadFileTemp,
    getHistoryTable,
    saveColumnMapping,
    waitForMappingValidation,
} from '../../services/wizardService';
import { getTableColumns } from '../../services/systemService';
import useSessionLoadGuard from '../../hooks/useSessionLoadGuard';
import { useAuth } from '../../context/AuthContext';
import { Button, LoadingSpinner, Alert, FormField, Select } from '../ui';
import {
    HISTORY_TARGET_SCHEMA,
    HISTORY_TARGET_TABLE,
    HISTORY_TABLE_META,
    FALLBACK_PROCESS_TYPES,
} from '../../constants/historyConfig';
import { formatNumber } from '../../lib/format';
import {
    appendFixedHistoryAutoMappings,
    appendFixedOrganizationMapping,
    buildAutoColumnMappings,
    buildMappingContext,
    mergeHistoryProductionColumns,
} from '../../utils/wizardColumnMapping';
import './Step1Upload.css';

const Step1Upload = ({ wizardData, updateWizardData, nextStep }) => {
    const { user } = useAuth();
    const organizationId = user?.organization_id || wizardData.organizationId || '';
    const [file, setFile] = useState(wizardData.file || null);
    const [processType, setProcessType] = useState(wizardData.processType || '');
    const [uploading, setUploading] = useState(false);
    const [validating, setValidating] = useState(false);
    const [validationProgress, setValidationProgress] = useState(null);
    const [error, setError] = useState('');
    const [historyMeta, setHistoryMeta] = useState(
        wizardData.historyTableMeta || HISTORY_TABLE_META
    );
    const [metaLoading, setMetaLoading] = useState(!wizardData.historyTableMeta?.process_types?.length);

    useSessionLoadGuard(uploading || validating);
    const [dragActive, setDragActive] = useState(false);

    useEffect(() => {
        let cancelled = false;
        (async () => {
            try {
                setMetaLoading(true);
                const { table } = await getHistoryTable();
                if (!cancelled) {
                    setHistoryMeta(table);
                }
            } catch {
                if (!cancelled) {
                    setHistoryMeta(HISTORY_TABLE_META);
                }
            } finally {
                if (!cancelled) {
                    setMetaLoading(false);
                }
            }
        })();
        return () => {
            cancelled = true;
        };
    }, []);

    const processTypes = historyMeta?.process_types?.length
        ? historyMeta.process_types
        : FALLBACK_PROCESS_TYPES;

    const validationHints = historyMeta?.validation_hints?.length
        ? historyMeta.validation_hints
        : HISTORY_TABLE_META.validation_hints;

    const handleDrag = (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (e.type === 'dragenter' || e.type === 'dragover') {
            setDragActive(true);
        } else if (e.type === 'dragleave') {
            setDragActive(false);
        }
    };

    const handleDrop = (e) => {
        e.preventDefault();
        e.stopPropagation();
        setDragActive(false);

        if (e.dataTransfer.files && e.dataTransfer.files[0]) {
            setFile(e.dataTransfer.files[0]);
            setError('');
        }
    };

    const handleFileSelect = (e) => {
        if (e.target.files && e.target.files[0]) {
            setFile(e.target.files[0]);
            setError('');
        }
    };

    const handleSubmit = async () => {
        if (!file) {
            setError('Selecciona un archivo');
            return;
        }
        if (!processType) {
            setError('Selecciona el tipo de proceso (granularidad)');
            return;
        }

        try {
            setUploading(true);
            setError('');

            const response = await uploadFileTemp(
                file,
                HISTORY_TARGET_SCHEMA,
                HISTORY_TARGET_TABLE,
                processType,
                'history'
            );

            const batchId = response.batch_id;
            const fileHeaders = response.file_headers || [];

            const colsData = await getTableColumns(HISTORY_TARGET_SCHEMA, HISTORY_TARGET_TABLE);
            const productionColumns = mergeHistoryProductionColumns(colsData.columns || []);
            const mappingCtx = buildMappingContext({
                loadMode: 'history',
                selectedSchema: HISTORY_TARGET_SCHEMA,
                selectedTable: HISTORY_TARGET_TABLE,
                historyTableMeta: historyMeta,
            });

            let { mappings, toggles } = buildAutoColumnMappings(
                fileHeaders,
                productionColumns,
                mappingCtx,
            );

            const tableHasOrganizationId = productionColumns.some(
                (col) => col.name === 'organization_id',
            );
            const withOrg = appendFixedOrganizationMapping(mappings, toggles, {
                organizationId,
                tableHasOrganizationId,
            });
            mappings = withOrg.mappings;
            toggles = withOrg.toggles;

            const withHistory = appendFixedHistoryAutoMappings(mappings, toggles, {
                loadMode: 'history',
                processType,
                fileName: response.file_name,
                historyTableMeta: historyMeta,
            });
            if (withHistory.error) {
                setError(withHistory.error);
                return;
            }
            mappings = withHistory.mappings;
            toggles = withHistory.toggles;

            await saveColumnMapping(
                batchId,
                {
                    target_schema: HISTORY_TARGET_SCHEMA,
                    target_table: HISTORY_TARGET_TABLE,
                    column_mappings: mappings,
                    column_toggles: toggles,
                },
                processType,
                'history',
                { triggerValidation: true },
            );

            setUploading(false);
            setValidating(true);
            setValidationProgress(null);

            await waitForMappingValidation(batchId, {
                onProgress: (p) => setValidationProgress(p),
                estimatedRows: response.estimated_rows,
            });

            updateWizardData({
                file: file,
                fileName: response.file_name,
                fileHeaders,
                selectedSchema: HISTORY_TARGET_SCHEMA,
                selectedTable: HISTORY_TARGET_TABLE,
                historyTableMeta: historyMeta,
                sourceName: response.source_name,
                batchId,
                processType: processType,
                loadMode: 'history',
                estimatedRows: response.estimated_rows,
                fileType: response.file_type,
                columnMappings: mappings,
                columnToggles: toggles,
                productionColumns,
                validationComplete: true,
                organizationId,
            });

            nextStep();
        } catch (err) {
            const detail = err.response?.data?.detail;
            if (typeof detail === 'string') {
                setError(
                    detail === 'Not Found'
                        ? 'Servicio de carga no disponible. Reinicia el backend (python run_app.py).'
                        : detail
                );
            } else {
                setError(
                    err.message
                        || 'No se pudo completar la carga o validación. Verifica que el API y los workers estén activos.'
                );
            }
            console.error(err);
        } finally {
            setUploading(false);
            setValidating(false);
        }
    };

    if (validating) {
        const pct = Math.min(100, Math.max(0, Number(validationProgress?.progress_percentage) || 0));
        const operation = validationProgress?.current_operation || 'Validando filas del archivo…';
        const processed = validationProgress?.processed_rows ?? 0;
        const total = validationProgress?.total_rows ?? 0;
        const showRowCounts = total > 0;

        return (
            <div className="step1-upload">
                <div className="step1-validating">
                    <LoadingSpinner />
                    <p>{operation}</p>
                    <div className="step1-progress">
                        <div className="step1-progress__bar">
                            <div
                                className="step1-progress__fill"
                                style={{ width: `${pct}%` }}
                            />
                        </div>
                        {showRowCounts && (
                            <p className="step1-progress__rows">
                                {formatNumber(processed)} de {formatNumber(total)} filas
                            </p>
                        )}
                    </div>
                    <p className="step1-validating__hint">
                        Iniciando validaciones preliminares del archivo.
                    </p>
                </div>
            </div>
        );
    }

    return (
        <div className="step1-upload">
            <div className="step1-content">
                <div className="upload-section">
                    <h3>Archivo</h3>
                    <div
                        className={`drop-zone ${dragActive ? 'active' : ''} ${file ? 'has-file' : ''}`}
                        onDragEnter={handleDrag}
                        onDragLeave={handleDrag}
                        onDragOver={handleDrag}
                        onDrop={handleDrop}
                    >
                        {file ? (
                            <div className="file-info">
                                <div className="file-icon">📄</div>
                                <div className="file-details">
                                    <div className="file-name">{file.name}</div>
                                    <div className="file-size">
                                        {(file.size / 1024 / 1024).toFixed(2)} MB
                                    </div>
                                </div>
                                <button
                                    type="button"
                                    className="remove-file"
                                    onClick={(e) => {
                                        e.stopPropagation();
                                        setFile(null);
                                        updateWizardData({
                                            file: null,
                                            fileName: '',
                                            fileHeaders: [],
                                            batchId: '',
                                            processType: '',
                                            sourceName: '',
                                            estimatedRows: 0,
                                            fileType: null,
                                        });
                                    }}
                                >
                                    ✕
                                </button>
                            </div>
                        ) : (
                            <>
                                <div className="drop-icon">📁</div>
                                <p className="drop-text">Arrastra tu archivo aquí o</p>
                                <label className="browse-button">
                                    Examinar
                                    <input
                                        type="file"
                                        accept=".csv,.xlsx,.xls,.json"
                                        onChange={handleFileSelect}
                                        style={{ display: 'none' }}
                                    />
                                </label>
                                <p className="drop-hint">CSV, Excel o JSON</p>
                            </>
                        )}
                    </div>
                </div>

                <div className="selection-section">
                    <h3>Configuración</h3>

                    <FormField label="Granularidad (tipo de proceso)" htmlFor="processType" required className="form-group">
                        <Select
                            id="processType"
                            value={processType}
                            onChange={(e) => setProcessType(e.target.value)}
                            disabled={metaLoading}
                        >
                            <option value="">
                                {metaLoading ? 'Cargando opciones…' : '-- Seleccionar --'}
                            </option>
                            {processTypes.map((pt) => (
                                <option key={pt.key} value={pt.key}>
                                    {pt.label}
                                </option>
                            ))}
                        </Select>
                    </FormField>

                    <div className="info-box history-target-box">
                        <div className="info-label">Tabla destino</div>
                        <div className="info-value">
                            {HISTORY_TARGET_SCHEMA}.{HISTORY_TARGET_TABLE}
                        </div>
                        <p className="info-hint">
                            Columnas clave: location_code, sku, period_start, quantity.
                            granularity y source (extensión del archivo) se asignan automáticamente.
                        </p>
                        <ul className="history-hints-list">
                            {validationHints.map((hint) => (
                                <li key={hint}>{hint}</li>
                            ))}
                        </ul>
                    </div>
                </div>
            </div>

            {error && <Alert variant="error">{error}</Alert>}

            <div className="step-actions">
                <Button
                    variant="primary"
                    onClick={handleSubmit}
                    loading={uploading}
                    loadingLabel="Subiendo archivo…"
                    disabled={!file || !processType || validating || metaLoading}
                >
                    Siguiente: mapear columnas →
                </Button>
            </div>
        </div>
    );
};

export default Step1Upload;
