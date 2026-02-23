import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Upload as UploadIcon, File, CheckCircle, XCircle } from 'lucide-react';
import Card from '../components/Card';
import Button from '../components/Button';
import { uploadService } from '../services/uploadService';
import './Upload.css';

const Upload = () => {
    const navigate = useNavigate();
    const [dragActive, setDragActive] = useState(false);
    const [file, setFile] = useState(null);
    const [sourceName, setSourceName] = useState('');
    const [uploading, setUploading] = useState(false);
    const [uploadResult, setUploadResult] = useState(null);
    const [error, setError] = useState(null);

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
        }
    };

    const handleFileChange = (e) => {
        if (e.target.files && e.target.files[0]) {
            setFile(e.target.files[0]);
        }
    };

    const handleUpload = async () => {
        if (!file) return;

        try {
            setUploading(true);
            setError(null);

            const result = await uploadService.uploadFile(file, sourceName || null);
            setUploadResult(result);

            // Clear form
            setFile(null);
            setSourceName('');
        } catch (err) {
            setError(err.response?.data?.detail || 'Upload failed');
        } finally {
            setUploading(false);
        }
    };

    const handleReset = () => {
        setFile(null);
        setSourceName('');
        setUploadResult(null);
        setError(null);
    };

    return (
        <div className="page-container">
            <div className="page-header">
                <h1 className="page-title">File Upload</h1>
                <p className="page-subtitle">Upload CSV, Excel, or JSON files for processing</p>
            </div>

            {!uploadResult ? (
                <Card className="upload-card">
                    {/* Drag & Drop Zone */}
                    <div
                        className={`dropzone ${dragActive ? 'dropzone-active' : ''} ${file ? 'dropzone-has-file' : ''}`}
                        onDragEnter={handleDrag}
                        onDragLeave={handleDrag}
                        onDragOver={handleDrag}
                        onDrop={handleDrop}
                    >
                        {file ? (
                            <div className="file-preview">
                                <File size={48} className="file-icon" />
                                <p className="file-name">{file.name}</p>
                                <p className="file-size">{(file.size / 1024).toFixed(2)} KB</p>
                                <Button variant="secondary" size="sm" onClick={() => setFile(null)}>
                                    Remove
                                </Button>
                            </div>
                        ) : (
                            <div className="dropzone-content">
                                <UploadIcon size={64} className="upload-icon" />
                                <p className="dropzone-title">Drag & drop file here</p>
                                <p className="dropzone-subtitle">or</p>
                                <label htmlFor="file-input">
                                    <Button variant="primary" as="span">
                                        Browse Files
                                    </Button>
                                </label>
                                <input
                                    id="file-input"
                                    type="file"
                                    accept=".csv,.xlsx,.xls,.json"
                                    onChange={handleFileChange}
                                    style={{ display: 'none' }}
                                />
                                <p className="dropzone-formats">Supported: CSV, Excel, JSON</p>
                            </div>
                        )}
                    </div>

                    {/* Source Name Input */}
                    <div className="form-group">
                        <label htmlFor="source-name" className="form-label">
                            Source Name (Optional)
                        </label>
                        <input
                            id="source-name"
                            type="text"
                            className="form-input"
                            placeholder="e.g., Monthly Sales Data"
                            value={sourceName}
                            onChange={(e) => setSourceName(e.target.value)}
                        />
                        <p className="form-hint">
                            Provide a descriptive name to identify this data source
                        </p>
                    </div>

                    {/* Error Message */}
                    {error && (
                        <div className="alert alert-error">
                            <XCircle size={20} />
                            <span>{error}</span>
                        </div>
                    )}

                    {/* Upload Button */}
                    <div className="upload-actions">
                        <Button
                            variant="primary"
                            size="lg"
                            onClick={handleUpload}
                            disabled={!file || uploading}
                            loading={uploading}
                            icon={UploadIcon}
                        >
                            Upload File
                        </Button>
                    </div>
                </Card>
            ) : (
                <Card className="upload-success">
                    <div className="success-content">
                        <CheckCircle size={64} className="success-icon" />
                        <h2 className="success-title">Upload Successful!</h2>
                        <p className="success-message">
                            Your file has been uploaded and is being processed
                        </p>

                        <div className="success-details">
                            <div className="detail-item">
                                <span className="detail-label">Batch ID:</span>
                                <code className="detail-value">{uploadResult.batch_id}</code>
                            </div>
                            <div className="detail-item">
                                <span className="detail-label">Source:</span>
                                <span className="detail-value">{uploadResult.source_name || 'N/A'}</span>
                            </div>
                        </div>

                        <div className="success-actions">
                            <Button
                                variant="primary"
                                onClick={() => navigate(`/batches`)}
                            >
                                View Batches
                            </Button>
                            <Button
                                variant="secondary"
                                onClick={handleReset}
                            >
                                Upload Another File
                            </Button>
                        </div>
                    </div>
                </Card>
            )}
        </div>
    );
};

export default Upload;
