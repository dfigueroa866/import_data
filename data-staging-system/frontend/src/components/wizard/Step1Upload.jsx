import React, { useState } from 'react';
import { uploadFileTemp } from '../../services/wizardService';
import useSessionLoadGuard from '../../hooks/useSessionLoadGuard';
import Button from '../Button';
import LoadingSpinner from '../LoadingSpinner';
import {
    HISTORY_TARGET_SCHEMA,
    HISTORY_TARGET_TABLE,
    HISTORY_TABLE_META,
} from '../../constants/historyConfig';
import './Step1Upload.css';

const Step1Upload = ({ wizardData, updateWizardData, nextStep }) => {
    const [file, setFile] = useState(wizardData.file || null);
    const [processType, setProcessType] = useState(wizardData.processType || '');
    const [uploading, setUploading] = useState(false);
    const [error, setError] = useState('');

    useSessionLoadGuard(uploading);
    const [dragActive, setDragActive] = useState(false);

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
            setError('Selecciona el tipo de proceso (Weekly o Monthly)');
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

            updateWizardData({
                file: file,
                fileName: response.file_name,
                fileHeaders: response.file_headers || [],
                selectedSchema: HISTORY_TARGET_SCHEMA,
                selectedTable: HISTORY_TARGET_TABLE,
                historyTableMeta: HISTORY_TABLE_META,
                sourceName: response.source_name,
                batchId: response.batch_id,
                processType: processType,
                loadMode: 'history',
                estimatedRows: response.estimated_rows,
                fileType: response.file_type,
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
                setError('No se pudo subir el archivo. Verifica que el API esté en ejecución.');
            }
            console.error(err);
        } finally {
            setUploading(false);
        }
    };

    return (
        <div className="step1-upload">
            <h2>Paso 1: Archivo y tipo de agregación</h2>
            <p className="step-description">
                Los datos se cargarán siempre en{' '}
                <strong>
                    {HISTORY_TARGET_SCHEMA}.{HISTORY_TARGET_TABLE}
                </strong>
                . Elige cómo consolidar fechas antes de mapear columnas.
            </p>

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

                    <div className="form-group">
                        <label htmlFor="processType">Tipo de proceso *</label>
                        <select
                            id="processType"
                            value={processType}
                            onChange={(e) => setProcessType(e.target.value)}
                        >
                            <option value="">-- Seleccionar --</option>
                            <option value="Weekly">Weekly (agrupa por semana)</option>
                            <option value="Monthly">Monthly (agrupa por mes)</option>
                        </select>
                    </div>

                    <div className="info-box history-target-box">
                        <div className="info-label">Tabla destino</div>
                        <div className="info-value">
                            {HISTORY_TARGET_SCHEMA}.{HISTORY_TARGET_TABLE}
                        </div>
                        <p className="info-hint">
                            Columnas clave: location_code, sku, period_start, quantity.
                            granularity (week/month) y source (extensión del archivo) se asignan automáticamente.
                        </p>
                        <ul className="history-hints-list">
                            {HISTORY_TABLE_META.validation_hints.map((hint) => (
                                <li key={hint}>{hint}</li>
                            ))}
                        </ul>
                    </div>
                </div>
            </div>

            {error && <div className="error-message">{error}</div>}

            <div className="step-actions">
                <Button
                    variant="primary"
                    onClick={handleSubmit}
                    disabled={!file || !processType || uploading}
                >
                    {uploading ? (
                        <>
                            <LoadingSpinner size="small" />
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

export default Step1Upload;
