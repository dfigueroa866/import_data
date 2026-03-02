import React, { useState, useEffect } from 'react';
import { startProcessing, getProcessingProgress, promoteBatch, downloadRejectedRecords, deleteBatch } from '../../services/wizardService';
import { useNavigate } from 'react-router-dom';
import Button from '../Button';
import LoadingSpinner from '../LoadingSpinner';
import './Step4Process.css';

const Step4Process = ({ wizardData, updateWizardData, resetWizard, onComplete }) => {
    const navigate = useNavigate();
    const [status, setStatus] = useState('idle'); // idle, processing, success, error
    const [processing, setProcessing] = useState(true); // Default to true as we start immediately
    const [progress, setProgress] = useState(0);
    const [logs, setLogs] = useState([]);
    const [error, setError] = useState(null);
    const [completed, setCompleted] = useState(false);

    // New State for Promotion Phase
    const [activeTab, setActiveTab] = useState('passed'); // 'passed' | 'rejected'
    const [promoting, setPromoting] = useState(false);
    const [promoteSuccess, setPromoteSuccess] = useState(false);
    const [promoteError, setPromoteError] = useState('');

    useEffect(() => {
        // Auto-start processing when component mounts
        handleStartProcessing();
    }, []);

    const handleStartProcessing = async () => {
        try {
            setProcessing(true);
            setError('');

            // Trigger processing with auto-promotion enabled to allow graceful row rejection then direct Prod
            await startProcessing(wizardData.batchId, { auto_production: false });

            // Start polling for progress
            const pollInterval = setInterval(async () => {
                const progressData = await getProcessingProgress(wizardData.batchId);
                setProgress(progressData);

                // Check if completed
                if (progressData.status === 'PROMOTED') {
                    clearInterval(pollInterval);
                    setCompleted(true);
                    setProcessing(false);
                    setPromoteSuccess(true);
                } else if (!progressData.auto_production && progressData.status === 'COMPLETED') {
                    // Fallback in case backend doesn't support auto_production correctly
                    clearInterval(pollInterval);
                    setCompleted(true);
                    setProcessing(false);
                } else if (progressData.status === 'FAILED') {
                    clearInterval(pollInterval);
                    setError(progressData.error_message || 'Processing failed');
                    setStatus('error'); // Set status to error
                    setProcessing(false);
                    if (onError) onError();
                }
            }, 1000); // Poll every second

            // Cleanup interval on unmount
            return () => clearInterval(pollInterval);

        } catch (err) {
            setError(err.response?.data?.detail || 'Failed to start processing');
            setStatus('error'); // Set status to error
            setProcessing(false);
            if (onError) onError();
            console.error(err);
        }
    };

    const handleViewStaging = () => {
        navigate('/staging');
    };

    const handleNewUpload = async () => {
        try {
            // Eliminar el registro del batch si existe
            if (wizardData.batchId) {
                await deleteBatch(wizardData.batchId);
            }
        } catch (err) {
            console.error("Cleanup failed", err);
        } finally {
            resetWizard();
        }
    };

    const handlePromote = async () => {
        try {
            setPromoting(true);
            setPromoteError('');

            // 1. Trigger promotion job
            await promoteBatch(wizardData.batchId);

            // 2. Start polling for completion
            const pollInterval = setInterval(async () => {
                try {
                    const progressData = await getProcessingProgress(wizardData.batchId);

                    if (progressData.status === 'PROMOTED') {
                        clearInterval(pollInterval);
                        setPromoteSuccess(true);
                        setPromoting(false);
                    } else if (progressData.status === 'FAILED') {
                        clearInterval(pollInterval);
                        setPromoteError(progressData.error_message || 'Promotion failed');
                        setPromoting(false);
                    }
                    // Else: still promoting, keep polling
                } catch (err) {
                    console.error("Polling error", err);
                    // Don't stop polling on transient network errors, but maybe limit retries in a real app
                }
            }, 2000); // Poll every 2 seconds

            // Cleanup if component unmounts (optional, but good practice if we could access the interval ID outside)

        } catch (err) {
            setPromoteError(err.response?.data?.detail || 'Promotion start failed');
            setPromoting(false);
        }
    };

    const handleDownloadRejected = async () => {
        try {
            await downloadRejectedRecords(wizardData.batchId);
        } catch (err) {
            console.error("Download failed", err);
            alert("Failed to download rejected records: " + (err.response?.data?.detail || err.message));
        }
    };

    if (error && !processing) {
        return (
            <div className="step4-error">
                <div className="error-icon">✕</div>
                <h3>Staging Load Failed</h3>
                <p className="error-message">{error}</p>
                <div className="error-actions">
                    <Button variant="secondary" onClick={() => navigate('/batches')}>
                        View Batches
                    </Button>
                    <Button variant="primary" onClick={handleNewUpload}>
                        Start Over (Reset)
                    </Button>
                </div>
            </div>
        );
    }

    if (completed) {
        const passedCount = (progress?.loaded_rows || 0) - (progress?.rejected_rows || 0); // Estimation (or use explicit passed_count if avail)
        // Better: use records_count from batch info if available, otherwise calc
        const totalRows = progress?.total_rows || 0;
        const rejectedCount = progress?.rejected_rows || 0;
        const actualPassed = progress?.loaded_rows || 0; // Assuming loaded = passed staging validation

        if (promoteSuccess && rejectedCount === 0) {
            return (
                <div className="step4-completed success-animation">
                    <div className="success-icon grande">🎉</div>
                    <h2>Import Successful!</h2>
                    <p>Successfully imported <strong>{actualPassed.toLocaleString()}</strong> records directly to Production.</p>
                    <p className="sub-text">WAL growth was optimized through streaming COPY.</p>

                    <div className="completion-actions">
                        <Button variant="primary" onClick={handleNewUpload}>
                            Upload Another File
                        </Button>
                        <Button variant="secondary" onClick={() => navigate('/dashboard')}>
                            Go to Dashboard
                        </Button>
                    </div>
                </div>
            );
        }

        return (
            <div className="step4-completed">
                <div className={promoteSuccess ? "success-icon grande" : "success-icon"}>
                    {promoteSuccess ? '🎉' : '✓'}
                </div>
                <h2>{promoteSuccess ? 'Import Partially Successful' : 'Staging Processing Complete'}</h2>
                <p>
                    {promoteSuccess
                        ? `Loaded ${actualPassed.toLocaleString()} records to Production, but ${rejectedCount.toLocaleString()} failed validation.`
                        : 'Data has been loaded to staging. Please review validation results below.'}
                </p>

                <div className="validation-tabs">
                    <button
                        className={`tab-btn ${activeTab === 'passed' ? 'active' : ''}`}
                        onClick={() => setActiveTab('passed')}
                    >
                        ✅ Ready to Promote ({actualPassed.toLocaleString()})
                    </button>
                    <button
                        className={`tab-btn ${activeTab === 'rejected' ? 'active' : ''} ${rejectedCount > 0 ? 'has-errors' : ''}`}
                        onClick={() => setActiveTab('rejected')}
                    >
                        ❌ Rejected / Duplicates ({rejectedCount.toLocaleString()})
                    </button>
                </div>

                <div className="tab-content">
                    {activeTab === 'passed' && (
                        <div className="tab-pane passed-pane">
                            <div className="stat-big success">
                                <span className="number">{actualPassed.toLocaleString()}</span>
                                <span className="label">Valid Records</span>
                            </div>
                            <p>These records have passed all format and type validations.</p>
                            <p>
                                {promoteSuccess
                                    ? 'These records have been successfully imported to Production.'
                                    : 'Click Promote to run the final duplicate check and push to Production.'}
                            </p>

                            {promoteError && (
                                <div className="promotion-error">
                                    <span className="icon">⛔</span>
                                    {promoteError}
                                </div>
                            )}

                            <div className="action-area">
                                {!promoteSuccess ? (
                                    <Button
                                        variant="primary"
                                        className="promote-btn"
                                        onClick={handlePromote}
                                        disabled={promoting || actualPassed === 0}
                                    >
                                        {promoting ? <LoadingSpinner size="small" /> : '🚀 Promote to Production'}
                                    </Button>
                                ) : (
                                    <div className="success-badge import-complete">
                                        ✨ Import Cycle Finished
                                    </div>
                                )}
                            </div>
                        </div>
                    )}

                    {activeTab === 'rejected' && (
                        <div className="tab-pane rejected-pane">
                            <div className="stat-big error">
                                <span className="number">{rejectedCount.toLocaleString()}</span>
                                <span className="label">Rejected Records</span>
                            </div>

                            {rejectedCount > 0 ? (
                                <>
                                    <p>These records failed validation (format errors, special characters) or duplicates found.</p>
                                    <p>Download the report to correct them and upload a cleanup file later.</p>
                                    <div className="action-area">
                                        <Button
                                            variant="secondary"
                                            className="download-btn"
                                            onClick={handleDownloadRejected}
                                        >
                                            📥 Download Rejected Records (.csv)
                                        </Button>
                                    </div>
                                </>
                            ) : (
                                <p className="empty-state">No rejected records! Good job. ✨</p>
                            )}
                        </div>
                    )}
                </div>

                <div className="completion-summary mini">
                    <div className="summary-item">
                        <span className="label">Target:</span>
                        <span className="value">{progress?.target_schema}.{progress?.target_table}</span>
                    </div>
                </div>
            </div>
        );
    }

    return (
        <div className="step4-process">
            <h2>Step 4: Processing to Production</h2>
            <p className="step-description">
                Streaming your data directly to production using high-performance COPY.
            </p>

            {/* Progress Bar */}
            <div className="progress-container">
                <div className="progress-bar">
                    <div
                        className="progress-fill"
                        style={{ width: `${progress?.progress_percentage || 0}%` }}
                    ></div>
                </div>
                <div className="progress-text">
                    {progress?.progress_percentage || 0}% Complete
                </div>
            </div>

            {/* Current Operation */}
            <div className="current-operation">
                <LoadingSpinner size="small" />
                <span>{progress?.current_operation || 'Initializing...'}</span>
            </div>

            {/* Statistics */}
            <div className="processing-stats">
                <div className="stat-card">
                    <div className="stat-value">{progress?.total_rows?.toLocaleString() || 0}</div>
                    <div className="stat-label">Total Rows</div>
                </div>
                <div className="stat-card">
                    <div className="stat-value">{progress?.processed_rows?.toLocaleString() || 0}</div>
                    <div className="stat-label">Processed</div>
                </div>
                <div className="stat-card">
                    <div className="stat-value">{progress?.loaded_rows?.toLocaleString() || 0}</div>
                    <div className="stat-label">Loaded</div>
                </div>
                <div className="stat-card">
                    <div className="stat-value">{progress?.rejected_rows?.toLocaleString() || 0}</div>
                    <div className="stat-label">Rejected</div>
                </div>
            </div>

            {/* Processing Details */}
            <div className="processing-details">
                <h3>Processing Details</h3>
                <div className="detail-row">
                    <span className="detail-label">Staging Table:</span>
                    <span className="detail-value">{progress?.staging_table || wizardData.sourceName}</span>
                </div>
                <div className="detail-row">
                    <span className="detail-label">Target Schema:</span>
                    <span className="detail-value">{progress?.target_schema || wizardData.selectedSchema}</span>
                </div>
                <div className="detail-row">
                    <span className="detail-label">Target Table:</span>
                    <span className="detail-value">{progress?.target_table || wizardData.selectedTable}</span>
                </div>
                <div className="detail-row">
                    <span className="detail-label">Status:</span>
                    <span className="detail-value status-badge">{progress?.status || 'PENDING'}</span>
                </div>
            </div>
        </div>
    );
};

export default Step4Process;
