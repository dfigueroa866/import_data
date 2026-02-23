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

    const getStatusColor = (status) => {
        switch (status) {
            case 'valid': return 'green';
            case 'warning': return 'orange';
            case 'error': return 'red';
            default: return 'gray';
        }
    };

    const getStatusIcon = (status) => {
        switch (status) {
            case 'valid': return '✓';
            case 'warning': return '⚠';
            case 'error': return '✕';
            default: return '○';
        }
    };

    const renderPreviewTable = () => {
        try {
            if (!previewData?.preview_data || previewData.preview_data.length === 0) {
                return <div className="no-data-message">No preview data available.</div>;
            }

            const firstRow = previewData.preview_data[0];
            const processedKeys = firstRow && firstRow.processed ? Object.keys(firstRow.processed) : [];

            if (processedKeys.length === 0) {
                return <div className="no-data-message">No processed columns found in the preview data.</div>;
            }

            return (
                <table className="preview-table">
                    <thead>
                        <tr>
                            <th>#</th>
                            <th>Status</th>
                            {processedKeys.map((key) => (
                                <th key={key}>{key}</th>
                            ))}
                            <th>Issues</th>
                        </tr>
                    </thead>
                    <tbody>
                        {previewData.preview_data.map((row, idx) => {
                            const processed = row.processed || {};
                            return (
                                <tr key={idx} className={`row-${row.status}`}>
                                    <td className="row-number">{row.row_number}</td>
                                    <td className="row-status">
                                        <span className={`status-badge status-${row.status}`}>
                                            {getStatusIcon(row.status)}
                                        </span>
                                    </td>
                                    {processedKeys.map((key) => (
                                        <td key={key} className="data-cell">
                                            {typeof processed[key] === 'object' && processed[key] !== null
                                                ? JSON.stringify(processed[key])
                                                : String(processed[key] !== undefined && processed[key] !== null ? processed[key] : '')}
                                        </td>
                                    ))}
                                    <td className="issues-cell">
                                        {row.warnings?.map((warning, i) => (
                                            <div key={i} className="issue warning">⚠ {warning}</div>
                                        ))}
                                        {row.errors?.map((error, i) => (
                                            <div key={i} className="issue error">✕ {error}</div>
                                        ))}
                                    </td>
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
            );
        } catch (err) {
            console.error("Table Render Error:", err);
            return <div className="error-message">Error rendering table: {err.message}</div>;
        }
    };

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
                Review transformed data and validation results before processing to staging.
            </p>

            {/* Summary Cards */}
            <div className="preview-summary">
                <div className="summary-card total">
                    <div className="card-value">{previewData.total_rows || 0}</div>
                    <div className="card-label">Total Rows</div>
                </div>
                {/* Removed Valid card as requested */}
                <div className="summary-card warning">
                    <div className="card-value">{previewData.warning_rows || 0}</div>
                    <div className="card-label">Warnings</div>
                </div>
                <div className="summary-card error">
                    <div className="card-value">{previewData.error_rows || 0}</div>
                    <div className="card-label">Errors</div>
                </div>
                {(previewData.duplicate_rows || 0) > 0 && (
                    <div className="summary-card duplicate">
                        <div className="card-value">{previewData.duplicate_rows}</div>
                        <div className="card-label">Duplicates</div>
                    </div>
                )}
            </div>

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

            {/* Preview Data Table */}
            <div className="preview-table-section">
                <h3>Data Preview (First 20 Rows)</h3>
                <div className="preview-table-container">
                    {renderPreviewTable()}
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
                    Process to Staging →
                </Button>
            </div>
        </div>
    );
};

export default Step3Preview;
