import React, { useState, useEffect } from 'react';
import { getSchemas, getTables, getTableColumns } from '../../services/systemService';
import { uploadFileTemp } from '../../services/wizardService';
import Button from '../Button';
import LoadingSpinner from '../LoadingSpinner';
import './Step1Upload.css';

const Step1Upload = ({ wizardData, updateWizardData, nextStep }) => {
    const [file, setFile] = useState(wizardData.file || null);
    const [schemas, setSchemas] = useState([]);
    const [tables, setTables] = useState([]);
    const [selectedSchema, setSelectedSchema] = useState(wizardData.selectedSchema || '');
    const [selectedTable, setSelectedTable] = useState(wizardData.selectedTable || '');
    const [loading, setLoading] = useState(false);
    const [uploading, setUploading] = useState(false);
    const [error, setError] = useState('');
    const [dragActive, setDragActive] = useState(false);

    // Load schemas on mount
    useEffect(() => {
        loadSchemas();
    }, []);

    // Initial load of tables if schema was already selected (on back)
    useEffect(() => {
        if (wizardData.selectedSchema && !tables.length) {
            loadTables(wizardData.selectedSchema);
        }
    }, [wizardData.selectedSchema]);

    // Load tables when schema changes
    useEffect(() => {
        if (selectedSchema) {
            loadTables(selectedSchema);
        } else {
            setTables([]);
            setSelectedTable('');
        }
    }, [selectedSchema]);

    const loadSchemas = async () => {
        try {
            setLoading(true);
            const data = await getSchemas();
            setSchemas(data.schemas || []);
        } catch (err) {
            setError('Failed to load schemas');
            console.error(err);
        } finally {
            setLoading(false);
        }
    };

    const loadTables = async (schema) => {
        try {
            setLoading(true);
            const data = await getTables(schema);
            setTables(data.tables || []);
        } catch (err) {
            setError('Failed to load tables');
            console.error(err);
        } finally {
            setLoading(false);
        }
    };

    const handleDrag = (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (e.type === "dragenter" || e.type === "dragover") {
            setDragActive(true);
        } else if (e.type === "dragleave") {
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
        // Validation
        if (!file) {
            setError('Please select a file');
            return;
        }
        if (!selectedSchema) {
            setError('Please select a schema');
            return;
        }
        if (!selectedTable) {
            setError('Please select a production table');
            return;
        }

        try {
            setUploading(true);
            setError('');

            // Upload file and get headers
            const response = await uploadFileTemp(file, selectedSchema, selectedTable);

            // Update wizard data
            updateWizardData({
                file: file,
                fileName: response.file_name,
                fileHeaders: response.file_headers || [],
                selectedSchema: selectedSchema,
                selectedTable: selectedTable,
                sourceName: response.source_name,
                batchId: response.batch_id,
                estimatedRows: response.estimated_rows,
                fileType: response.file_type
            });

            // Move to next step
            nextStep();

        } catch (err) {
            setError(err.response?.data?.detail || 'Failed to upload file');
            console.error(err);
        } finally {
            setUploading(false);
        }
    };

    return (
        <div className="step1-upload">
            <h2>Step 1: Upload File & Select Production Table</h2>
            <p className="step-description">
                Upload your data file and select the production table you want to map to.
            </p>

            <div className="step1-content">
                {/* File Upload Section */}
                <div className="upload-section">
                    <h3>Upload File</h3>
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
                                    <div className="file-size">{(file.size / 1024 / 1024).toFixed(2)} MB</div>
                                </div>
                                <button
                                    className="remove-file"
                                    onClick={(e) => {
                                        e.stopPropagation();
                                        setFile(null);
                                        // Also clear central state
                                        updateWizardData({
                                            file: null,
                                            fileName: '',
                                            fileHeaders: [],
                                            batchId: '',
                                            sourceName: '',
                                            estimatedRows: 0,
                                            fileType: null
                                        });
                                    }}
                                >
                                    ✕
                                </button>
                            </div>
                        ) : (
                            <>
                                <div className="drop-icon">📁</div>
                                <p className="drop-text">Drag & drop your file here or</p>
                                <label className="browse-button">
                                    Browse Files
                                    <input
                                        type="file"
                                        accept=".csv,.xlsx,.xls,.json"
                                        onChange={handleFileSelect}
                                        style={{ display: 'none' }}
                                    />
                                </label>
                                <p className="drop-hint">Supported: CSV, Excel, JSON</p>
                            </>
                        )}
                    </div>
                </div>

                {/* Schema & Table Selection */}
                <div className="selection-section">
                    <h3>Select Production Table</h3>

                    <div className="form-group">
                        <label htmlFor="schema">Schema *</label>
                        <select
                            id="schema"
                            value={selectedSchema}
                            onChange={(e) => setSelectedSchema(e.target.value)}
                            disabled={loading}
                        >
                            <option value="">-- Select Schema --</option>
                            {schemas.map(schema => (
                                <option key={schema} value={schema}>{schema}</option>
                            ))}
                        </select>
                    </div>

                    <div className="form-group">
                        <label htmlFor="table">Production Table *</label>
                        <select
                            id="table"
                            value={selectedTable}
                            onChange={(e) => setSelectedTable(e.target.value)}
                            disabled={!selectedSchema || loading}
                        >
                            <option value="">-- Select Table --</option>
                            {tables.map(table => (
                                <option key={table.table_name} value={table.table_name}>
                                    {table.table_name} ({table.column_count} columns)
                                </option>
                            ))}
                        </select>
                    </div>

                    {selectedTable && (
                        <div className="info-box">
                            <div className="info-label">Staging Table:</div>
                            <div className="info-value">staging_data.stage_{selectedTable}</div>
                            <p className="info-hint">Data will be loaded here for validation before production</p>
                        </div>
                    )}
                </div>
            </div>

            {error && (
                <div className="error-message">
                    {error}
                </div>
            )}

            <div className="step-actions">
                <Button
                    variant="primary"
                    onClick={handleSubmit}
                    disabled={!file || !selectedSchema || !selectedTable || uploading}
                >
                    {uploading ? (
                        <>
                            <LoadingSpinner size="small" />
                            Uploading...
                        </>
                    ) : (
                        'Next: Map Columns →'
                    )}
                </Button>
            </div>
        </div>
    );
};

export default Step1Upload;
