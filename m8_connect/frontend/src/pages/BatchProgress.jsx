import React, { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import Step4Process from '../components/wizard/Step4Process';
import Button from '../components/Button';
import { uploadService } from '../services/uploadService';
import './BatchProgress.css';

const BatchProgress = () => {
    const { batchId } = useParams();
    const navigate = useNavigate();
    const [cancelling, setCancelling] = useState(false);
    const [cancelError, setCancelError] = useState('');

    const handleCancel = async () => {
        if (!window.confirm('¿Cancelar este batch? Se detendrán los jobs en cola.')) {
            return;
        }
        setCancelError('');
        setCancelling(true);
        try {
            await uploadService.cancelBatch(batchId);
            navigate('/batches');
        } catch (err) {
            const detail = err.response?.data?.detail;
            setCancelError(
                typeof detail === 'string'
                    ? detail
                    : err.response?.status === 404
                      ? 'No se pudo cancelar: reinicia el backend (python run_app.py).'
                      : 'No se pudo cancelar el batch.'
            );
        } finally {
            setCancelling(false);
        }
    };

    return (
        <div className="batch-progress-page">
            <header className="batch-progress-header">
                <Link to="/batches" className="batch-progress-back">
                    ← Volver a batches
                </Link>
                <div className="batch-progress-meta">
                    <span className="batch-progress-label">Batch</span>
                    <code className="batch-progress-id">{batchId}</code>
                </div>
                <Button variant="secondary" size="sm" onClick={handleCancel} loading={cancelling}>
                    Cancelar batch
                </Button>
            </header>

            {cancelError && (
                <div className="batch-progress-cancel-error" role="alert">
                    {cancelError}
                </div>
            )}

            <Step4Process
                monitorMode
                wizardData={{ batchId, loadMode: 'catalog' }}
                onComplete={() => {}}
                onError={() => {}}
            />
        </div>
    );
};

export default BatchProgress;
