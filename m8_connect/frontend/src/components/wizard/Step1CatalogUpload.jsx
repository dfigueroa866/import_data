import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { uploadFileTemp, getCatalogTables } from '../../services/wizardService';
import { useAuth } from '../../context/AuthContext';
import useSessionLoadGuard from '../../hooks/useSessionLoadGuard';
import { Button, LoadingSpinner, Alert, FormField, Select } from '../ui';
import './Step1Upload.css';

const formatCatalogDestination = (catalog) => {
    const schema = catalog.target_schema || 'public';
    const table = catalog.target_table || catalog.name;
    return `${schema}.${table}`;
};

const Step1CatalogUpload = ({ wizardData, updateWizardData, nextStep }) => {
    const { user } = useAuth();
    const organizationName = user?.organization_name || wizardData.organizationName || '';

    const [file, setFile] = useState(wizardData.file || null);
    const [catalogTables, setCatalogTables] = useState([]);
    const [selectedCatalog, setSelectedCatalog] = useState(
        wizardData.catalogTable || wizardData.catalogTableMeta?.name || ''
    );
    const [tableMeta, setTableMeta] = useState(wizardData.catalogTableMeta || null);
    const [loading, setLoading] = useState(false);
    const [uploading, setUploading] = useState(false);
    const [error, setError] = useState('');
    const [dragActive, setDragActive] = useState(false);

    useSessionLoadGuard(uploading);

    useEffect(() => {
        loadCatalogTables();
    }, []);

    useEffect(() => {
        const meta = catalogTables.find((t) => t.name === selectedCatalog);
        setTableMeta(meta || null);
    }, [selectedCatalog, catalogTables]);

    const loadCatalogTables = async () => {
        try {
            setLoading(true);
            setError('');
            const data = await getCatalogTables();
            const tables = data.tables || [];
            setCatalogTables(tables);
            if (tables.length === 0) {
                setError('No hay catálogos activos configurados.');
            }
        } catch (err) {
            const detail = err.response?.data?.detail;
            setError(
                detail
                    ? `No se pudieron cargar catálogos: ${typeof detail === 'string' ? detail : JSON.stringify(detail)}`
                    : 'No se pudieron cargar catálogos. Verifica que el API esté en ejecución.'
            );
        } finally {
            setLoading(false);
        }
    };

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
        if (e.dataTransfer.files?.[0]) {
            setFile(e.dataTransfer.files[0]);
            setError('');
        }
    };

    const handleFileSelect = (e) => {
        if (e.target.files?.[0]) {
            setFile(e.target.files[0]);
            setError('');
        }
    };

    const handleSubmit = async () => {
        if (!file) {
            setError('Selecciona un archivo');
            return;
        }
        if (!selectedCatalog || !tableMeta) {
            setError('Selecciona un catálogo');
            return;
        }

        const targetSchema = tableMeta.target_schema || 'public';
        const physicalTable = tableMeta.target_table || tableMeta.name;

        try {
            setUploading(true);
            setError('');

            const response = await uploadFileTemp(
                file,
                targetSchema,
                tableMeta.name,
                null,
                'catalog'
            );

            updateWizardData({
                file,
                fileName: response.file_name,
                fileHeaders: response.file_headers || [],
                selectedSchema: targetSchema,
                selectedTable: physicalTable,
                catalogTable: tableMeta.name,
                sourceName: response.source_name,
                batchId: response.batch_id,
                processType: '',
                loadMode: 'catalog',
                catalogTableMeta: tableMeta,
                organizationName,
                estimatedRows: response.estimated_rows,
                fileType: response.file_type,
            });

            nextStep();
        } catch (err) {
            const detail = err.response?.data?.detail;
            setError(
                typeof detail === 'string'
                    ? detail
                    : 'No se pudo subir el archivo. Verifica que el API esté en ejecución.'
            );
        } finally {
            setUploading(false);
        }
    };

    return (
        <div className="step1-upload">
            <h2>Paso 1: Archivo y catálogo</h2>
            <p className="step-description">
                Sube tu archivo y elige el catálogo destino. El esquema y la tabla se toman de la
                configuración en <Link to="/config/catalogs">Catálogos</Link>.
            </p>

            <div className="step1-content catalog-step1-layout">
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
                                    }}
                                >
                                    ✕
                                </button>
                            </div>
                        ) : (
                            <>
                                <div className="drop-icon">📁</div>
                                <p className="drop-text">Arrastra tu archivo o</p>
                                <label className="browse-button">
                                    Examinar
                                    <input
                                        type="file"
                                        accept=".csv,.xlsx,.xls,.json"
                                        onChange={handleFileSelect}
                                        style={{ display: 'none' }}
                                    />
                                </label>
                                <p className="drop-hint">CSV, Excel, JSON</p>
                            </>
                        )}
                    </div>

                    <div className="selection-section" style={{ marginTop: '1.5rem' }}>
                        <h3>Catálogo *</h3>
                        {catalogTables.length === 0 && !loading ? (
                            <p className="catalog-no-match-hint">
                                No hay catálogos activos.{' '}
                                <Link to="/config/catalogs">Configúralos en Catálogos</Link>.
                            </p>
                        ) : (
                            <FormField label="Catálogo destino" htmlFor="catalogDefinition" required className="form-group">
                                <Select
                                    id="catalogDefinition"
                                    value={selectedCatalog}
                                    onChange={(e) => setSelectedCatalog(e.target.value)}
                                    disabled={loading}
                                >
                                    <option value="">-- Seleccionar catálogo --</option>
                                    {catalogTables.map((c) => (
                                        <option key={c.name} value={c.name}>
                                            {c.label} → {formatCatalogDestination(c)}
                                        </option>
                                    ))}
                                </Select>
                            </FormField>
                        )}
                    </div>
                </div>

                {tableMeta && (
                    <aside className="catalog-rules-panel widget-card">
                        {organizationName && (
                            <div className="rules-block org-context">
                                <strong>Organización</strong>
                                <p>{organizationName}</p>
                            </div>
                        )}
                        <h3>Reglas de {tableMeta.label}</h3>
                        <div className="rules-block">
                            <strong>Obligatorias en mapping</strong>
                            <ul>
                                {(tableMeta.required_mapping_columns?.length
                                    ? tableMeta.required_mapping_columns
                                    : tableMeta.required_columns || []
                                )
                                    .filter((c) => c !== 'organization_id')
                                    .map((c) => (
                                        <li key={c}>{c}</li>
                                    ))}
                            </ul>
                        </div>
                        {Object.keys(tableMeta.enums || {}).length > 0 && (
                            <div className="rules-block">
                                <strong>Valores permitidos</strong>
                                {Object.entries(tableMeta.enums).map(([col, vals]) => (
                                    <p key={col}>
                                        {col}: {vals.join(', ')}
                                    </p>
                                ))}
                            </div>
                        )}
                        <div className="rules-block">
                            <strong>Notas</strong>
                            <ul>
                                {(tableMeta.validation_hints || [])
                                    .filter((h) => !/clave\s+única/i.test(h))
                                    .map((h, i) => (
                                        <li key={i}>{h}</li>
                                    ))}
                            </ul>
                        </div>
                    </aside>
                )}
            </div>

            {error && <Alert variant="error">{error}</Alert>}

            <div className="step-actions">
                <Button
                    variant="primary"
                    onClick={handleSubmit}
                    disabled={!file || !selectedCatalog || uploading}
                >
                    {uploading ? (
                        <>
                            <LoadingSpinner size="sm" />
                            Subiendo...
                        </>
                    ) : (
                        'Siguiente: mapear columnas →'
                    )}
                </Button>
            </div>
        </div>
    );
};

export default Step1CatalogUpload;
