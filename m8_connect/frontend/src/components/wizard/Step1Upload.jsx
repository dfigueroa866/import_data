import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import {
    uploadFileTemp,
    getHistoryTables,
    getHistoryTable,
    getHistoryCatalogReadiness,
    saveColumnMapping,
    waitForMappingValidation,
} from '../../services/wizardService';
import { getTableColumns } from '../../services/systemService';
import useSessionLoadGuard from '../../hooks/useSessionLoadGuard';
import { useAuth } from '../../context/AuthContext';
import { Button, LoadingSpinner, Alert, FormField, Select } from '../ui';
import {
    HISTORY_TABLE_META,
    FALLBACK_PROCESS_TYPES,
} from '../../constants/historyConfig';
import { formatNumber } from '../../lib/format';
import { formatMissingCatalogs } from '../../lib/statusLabels';
import {
    appendFixedHistoryAutoMappings,
    appendFixedOrganizationMapping,
    buildAutoColumnMappings,
    buildMappingContext,
    mergeHistoryProductionColumns,
} from '../../utils/wizardColumnMapping';
import './Step1Upload.css';

const formatHistoryDestination = (meta) => {
    const schema = meta?.target_schema || 'public';
    const table = meta?.target_table || meta?.name || 'sales_history';
    return `${schema}.${table}`;
};

const Step1Upload = ({ wizardData, updateWizardData, nextStep }) => {
    const { user } = useAuth();
    const organizationId = user?.organization_id || wizardData.organizationId || '';
    const [file, setFile] = useState(wizardData.file || null);
    const [processType, setProcessType] = useState(wizardData.processType || '');
    const [uploading, setUploading] = useState(false);
    const [validating, setValidating] = useState(false);
    const [validationProgress, setValidationProgress] = useState(null);
    const [error, setError] = useState('');
    const [historyTables, setHistoryTables] = useState([]);
    const [selectedHistoryTable, setSelectedHistoryTable] = useState(
        wizardData.selectedTable || wizardData.historyTableMeta?.name || 'sales_history',
    );
    const [historyMeta, setHistoryMeta] = useState(
        wizardData.historyTableMeta || HISTORY_TABLE_META
    );
    const [tablesLoading, setTablesLoading] = useState(true);
    const [metaLoading, setMetaLoading] = useState(!wizardData.historyTableMeta?.process_types?.length);
    const [readinessLoading, setReadinessLoading] = useState(true);
    const [catalogReadiness, setCatalogReadiness] = useState(null);

    useSessionLoadGuard(uploading || validating);
    const [dragActive, setDragActive] = useState(false);

    useEffect(() => {
        let cancelled = false;
        (async () => {
            try {
                setReadinessLoading(true);
                const readiness = await getHistoryCatalogReadiness();
                if (!cancelled) {
                    setCatalogReadiness(readiness);
                }
            } catch {
                if (!cancelled) {
                    setCatalogReadiness(null);
                }
            } finally {
                if (!cancelled) {
                    setReadinessLoading(false);
                }
            }
        })();
        return () => {
            cancelled = true;
        };
    }, []);

    useEffect(() => {
        let cancelled = false;
        (async () => {
            try {
                setTablesLoading(true);
                const data = await getHistoryTables();
                const tables = data.tables || [];
                if (!cancelled) {
                    setHistoryTables(tables);
                    if (tables.length > 0 && !tables.some((t) => t.name === selectedHistoryTable)) {
                        setSelectedHistoryTable(tables[0].name);
                    }
                }
            } catch {
                if (!cancelled) {
                    setHistoryTables([]);
                }
            } finally {
                if (!cancelled) {
                    setTablesLoading(false);
                }
            }
        })();
        return () => {
            cancelled = true;
        };
    }, []);

    useEffect(() => {
        let cancelled = false;
        (async () => {
            if (!selectedHistoryTable) return;
            try {
                setMetaLoading(true);
                const { table } = await getHistoryTable(selectedHistoryTable);
                if (!cancelled) {
                    setHistoryMeta(table);
                    const pts = table?.process_types || [];
                    if (pts.length === 1) {
                        setProcessType(pts[0].key);
                    } else if (!pts.some((pt) => pt.key === processType)) {
                        setProcessType('');
                    }
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
    }, [selectedHistoryTable]);

    const processTypes = historyMeta?.process_types?.length
        ? historyMeta.process_types
        : FALLBACK_PROCESS_TYPES;

    const validationHints = historyMeta?.validation_hints?.length
        ? historyMeta.validation_hints
        : HISTORY_TABLE_META.validation_hints;

    const targetSchema = historyMeta?.target_schema || 'public';
    const targetTable = historyMeta?.target_table || selectedHistoryTable || 'sales_history';
    const catalogBlocked = catalogReadiness != null && catalogReadiness.ready === false;
    const uploadDisabled = catalogBlocked || readinessLoading || metaLoading || tablesLoading;
    const missingCatalogsLabel = formatMissingCatalogs(catalogReadiness?.missing);

    const handleDrag = (e) => {
        if (uploadDisabled) return;
        e.preventDefault();
        e.stopPropagation();
        if (e.type === 'dragenter' || e.type === 'dragover') {
            setDragActive(true);
        } else if (e.type === 'dragleave') {
            setDragActive(false);
        }
    };

    const handleDrop = (e) => {
        if (uploadDisabled) return;
        e.preventDefault();
        e.stopPropagation();
        setDragActive(false);

        if (e.dataTransfer.files && e.dataTransfer.files[0]) {
            setFile(e.dataTransfer.files[0]);
            setError('');
        }
    };

    const handleFileSelect = (e) => {
        if (uploadDisabled) return;
        if (e.target.files && e.target.files[0]) {
            setFile(e.target.files[0]);
            setError('');
        }
    };

    const handleSubmit = async () => {
        if (catalogBlocked) {
            setError(catalogReadiness?.message || 'Debes promover catálogos antes de cargar historia.');
            return;
        }
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
                targetSchema,
                targetTable,
                processType,
                'history'
            );

            const batchId = response.batch_id;
            const fileHeaders = response.file_headers || [];

            const colsData = await getTableColumns(targetSchema, targetTable);
            const productionColumns = mergeHistoryProductionColumns(colsData.columns || []);
            const mappingCtx = buildMappingContext({
                loadMode: 'history',
                selectedSchema: targetSchema,
                selectedTable: targetTable,
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
                    target_schema: targetSchema,
                    target_table: targetTable,
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
                selectedSchema: targetSchema,
                selectedTable: targetTable,
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
                {catalogBlocked && (
                    <Alert variant="warning">
                        <p>{catalogReadiness.message}</p>
                        {missingCatalogsLabel && (
                            <p className="mt-2">Faltan: {missingCatalogsLabel}</p>
                        )}
                        <p className="mt-2">
                            <Link to="/upload/catalog" className="text-brand-600 hover:underline font-semibold">
                                Ir a carga de catálogos →
                            </Link>
                        </p>
                    </Alert>
                )}

                <div className="upload-section">
                    <h3>Archivo</h3>
                    <div
                        className={[
                            'drop-zone',
                            dragActive ? 'active' : '',
                            file ? 'has-file' : '',
                            uploadDisabled ? 'drop-zone--disabled' : '',
                        ]
                            .filter(Boolean)
                            .join(' ')}
                        onDragEnter={handleDrag}
                        onDragLeave={handleDrag}
                        onDragOver={handleDrag}
                        onDrop={handleDrop}
                        aria-disabled={uploadDisabled}
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

                    <FormField label="Tabla de historia" htmlFor="historyTable" required className="form-group">
                        <Select
                            id="historyTable"
                            value={selectedHistoryTable}
                            onChange={(e) => setSelectedHistoryTable(e.target.value)}
                            disabled={uploadDisabled}
                        >
                            <option value="">
                                {tablesLoading ? 'Cargando tablas…' : '-- Seleccionar --'}
                            </option>
                            {historyTables.map((table) => (
                                <option key={table.name} value={table.name}>
                                    {table.label || table.name}
                                </option>
                            ))}
                        </Select>
                    </FormField>

                    <FormField label="Granularidad (tipo de proceso)" htmlFor="processType" required className="form-group">
                        <Select
                            id="processType"
                            value={processType}
                            onChange={(e) => setProcessType(e.target.value)}
                            disabled={uploadDisabled}
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
                            {formatHistoryDestination(historyMeta)}
                        </div>
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
                    disabled={!file || !processType || !selectedHistoryTable || validating || uploadDisabled}
                >
                    Siguiente: mapear columnas →
                </Button>
            </div>
        </div>
    );
};

export default Step1Upload;
