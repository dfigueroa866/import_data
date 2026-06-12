import React, { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Layers } from 'lucide-react';
import Step4Process from '../components/wizard/Step4Process';
import { Button, PageHeader, Alert } from '../components/ui';
import { uploadService } from '../services/uploadService';

const BatchProgress = () => {
  const { batchId } = useParams();
  const navigate = useNavigate();
  const [cancelling, setCancelling] = useState(false);
  const [cancelError, setCancelError] = useState('');

  const handleCancel = async () => {
    if (!window.confirm('¿Cancelar este lote? Se detendrán los jobs en cola.')) return;
    setCancelError('');
    setCancelling(true);
    try {
      await uploadService.cancelBatch(batchId);
      navigate('/batches');
    } catch (err) {
      const detail = err.response?.data?.detail;
      setCancelError(typeof detail === 'string' ? detail : err.response?.status === 404 ? 'No se pudo cancelar: reinicia el backend (python run_app.py).' : 'No se pudo cancelar el lote.');
    } finally {
      setCancelling(false);
    }
  };

  return (
    <div className="flex flex-1 flex-col gap-5 overflow-y-auto p-8 max-w-4xl mx-auto w-full scrollbar-thin">
      <PageHeader
        icon={Layers}
        title="Progreso del lote"
        subtitle={<code className="font-mono text-sm text-brand-700">{batchId}</code>}
        backTo="/batches"
        backLabel="Volver a lotes"
        action={<Button variant="secondary" size="sm" onClick={handleCancel} loading={cancelling}>Cancelar lote</Button>}
      />
      {cancelError && <Alert variant="error">{cancelError}</Alert>}
      <Step4Process monitorMode wizardData={{ batchId, loadMode: 'catalog' }} />
    </div>
  );
};

export default BatchProgress;
