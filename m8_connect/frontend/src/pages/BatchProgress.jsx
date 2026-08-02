import React, { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Layers } from 'lucide-react';
import Step4Process from '../components/wizard/Step4Process';
import { Button, PageHeader, Alert, LoadingSpinner, ConfirmDialog } from '../components/ui';
import { uploadService } from '../services/uploadService';

const deriveLoadMode = (metadata) => {
  const loadType = metadata?.load_type;
  return loadType === 'catalog' ? 'catalog' : 'history';
};

const BatchProgress = () => {
  const { batchId } = useParams();
  const navigate = useNavigate();
  const [cancelling, setCancelling] = useState(false);
  const [cancelError, setCancelError] = useState('');
  const [loading, setLoading] = useState(true);
  const [statusError, setStatusError] = useState('');
  const [wizardData, setWizardData] = useState(null);
  const [confirmCancelOpen, setConfirmCancelOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setStatusError('');
      try {
        const status = await uploadService.getBatchStatus(batchId);
        if (cancelled) return;
        const metadata = status.metadata || {};
        setWizardData({
          batchId,
          loadMode: deriveLoadMode(metadata),
          processType: metadata.process_type,
          selectedTable: metadata.target_table,
          catalogTable: metadata.target_table,
          catalogTableMeta: metadata.target_table
            ? { target_table: metadata.target_table }
            : undefined,
        });
      } catch (err) {
        if (!cancelled) {
          const detail = err.response?.data?.detail;
          setStatusError(
            typeof detail === 'string'
              ? detail
              : 'No se pudo cargar el estado del lote.'
          );
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [batchId]);

  const handleCancel = async () => {
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
      setConfirmCancelOpen(false);
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
        action={
          <Button
            variant="secondary"
            size="sm"
            onClick={() => setConfirmCancelOpen(true)}
            loading={cancelling}
          >
            Cancelar lote
          </Button>
        }
      />
      {cancelError && <Alert variant="error">{cancelError}</Alert>}
      {statusError && <Alert variant="error">{statusError}</Alert>}
      {loading ? (
        <LoadingSpinner size="lg" message="Cargando progreso del lote…" />
      ) : wizardData ? (
        <Step4Process monitorMode wizardData={wizardData} />
      ) : null}

      <ConfirmDialog
        isOpen={confirmCancelOpen}
        onClose={() => setConfirmCancelOpen(false)}
        onConfirm={handleCancel}
        title="Cancelar lote"
        message="¿Cancelar este lote? Se detendrán los jobs en cola."
        confirmText="Sí, cancelar"
        cancelText="No"
        variant="danger"
        loading={cancelling}
      />
    </div>
  );
};

export default BatchProgress;
