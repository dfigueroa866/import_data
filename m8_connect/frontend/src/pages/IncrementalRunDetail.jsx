import React, { useCallback, useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { Layers, ArrowLeft, Download, CheckCircle2, XCircle } from 'lucide-react';
import {
  PageHeader,
  Button,
  Card,
  LoadingSpinner,
  Alert,
  Badge,
  SummaryGrid,
  SummaryBlock,
} from '../components/ui';
import { formatDate, formatNumber, formatPromotedStats } from '../lib/format';
import {
  incrementalExecutionLabel,
  incrementalRunStatusLabel,
} from '../lib/statusLabels';
import * as incrementalService from '../services/incrementalService';

const IncrementalRunDetail = () => {
  const { runId } = useParams();
  const [run, setRun] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [downloading, setDownloading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const data = await incrementalService.getRun(runId);
      setRun(data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Error al cargar ejecución');
      setRun(null);
    } finally {
      setLoading(false);
    }
  }, [runId]);

  useEffect(() => {
    load();
  }, [load]);

  const handleDownload = async () => {
    setDownloading(true);
    setError('');
    try {
      const blob = await incrementalService.downloadRunRejected(runId);
      if (blob?.type?.includes('application/json')) {
        const text = await blob.text();
        const parsed = JSON.parse(text);
        throw new Error(parsed.detail || 'Error al descargar rechazados');
      }
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `rejected_${runId}.zip`;
      a.click();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      const detail = err.response?.data?.detail;
      if (detail instanceof Blob) {
        try {
          const parsed = JSON.parse(await detail.text());
          setError(parsed.detail || 'Error al descargar rechazados');
        } catch {
          setError('Error al descargar rechazados');
        }
      } else {
        setError(detail || err.message || 'Error al descargar rechazados');
      }
    } finally {
      setDownloading(false);
    }
  };

  if (loading) return <LoadingSpinner label="Cargando detalle…" />;
  if (!run) return <Alert variant="error">{error || 'Ejecución no encontrada'}</Alert>;

  const hasRejected = Number(run.total_rejected) > 0 || Boolean(run.has_rejected_files);
  const promotedTotal = Number(run.total_inserted || 0) + Number(run.total_updated || 0);
  const enqueued = run.execution_summary?.enqueued || [];
  const skipped = run.execution_summary?.skipped || [];

  return (
    <div className="flex flex-1 flex-col gap-5 overflow-y-auto p-8 scrollbar-thin">
      <PageHeader
        icon={Layers}
        title={`Ejecución ${run.load_date}`}
        subtitle={run.organization_name || run.organization_id}
        actions={(
          <div className="flex gap-2">
            <Link to="/incremental/runs">
              <Button variant="secondary"><ArrowLeft className="mr-2 h-4 w-4" />Volver</Button>
            </Link>
            {hasRejected && (
              <Button variant="secondary" onClick={handleDownload} disabled={downloading}>
                <Download className="mr-2 h-4 w-4" />
                {downloading ? 'Descargando…' : 'Rechazados'}
              </Button>
            )}
          </div>
        )}
      />
      {error && <Alert variant="error">{error}</Alert>}

      <div className="flex items-center gap-2">
        <Badge status={run.status} label={incrementalRunStatusLabel(run.status)} />
        <span className="text-sm text-[#64748b]">
          Inicio: {formatDate(run.started_at)}
          {run.finished_at ? ` · Fin: ${formatDate(run.finished_at)}` : ''}
        </span>
      </div>

      {run.error_message && <Alert variant="error">{run.error_message}</Alert>}

      {run.status === 'COMPLETED'
        && Number(run.total_inserted) === 0
        && Number(run.total_updated) > 0 && (
        <Alert variant="info">
          Los registros ya existían en la base de datos; la carga los actualizó (
          {formatNumber(run.total_updated)} filas).
        </Alert>
      )}

      {Number(run.total_rejected) > 0 && (
        <Alert variant="warning">
          {formatNumber(run.total_rejected)} filas del archivo original fueron rechazadas en validación
          y no se promovieron. Descárgalas para revisar errores (fechas, SKUs o ubicaciones faltantes).
        </Alert>
      )}

      <SummaryGrid columns={4}>
        <SummaryBlock
          label="Filas del archivo"
          value={formatNumber(run.total_processed)}
          hint="Total leído en preview (válidas + rechazadas)"
        />
        <SummaryBlock
          label="Promovidos"
          value={formatPromotedStats(run.total_inserted, run.total_updated)}
          hint={`${formatNumber(promotedTotal)} filas en producción`}
        />
        <SummaryBlock
          label="Rechazados"
          value={formatNumber(run.total_rejected)}
          hint={hasRejected ? 'Descargables desde el botón superior' : 'Sin rechazos'}
        />
        <SummaryBlock
          label="Insertados / actualizados"
          value={`${formatNumber(run.total_inserted)} / ${formatNumber(run.total_updated)}`}
          hint="Detalle del UPSERT en producción"
        />
      </SummaryGrid>

      <Card className="p-5">
        <h3 className="mb-4 font-semibold text-[#0f172a] dark:text-[#f1f5f9]">Resumen de ejecución</h3>

        <div className="mb-6">
          <h4 className="mb-2 flex items-center gap-2 text-sm font-medium text-green-700 dark:text-green-400">
            <CheckCircle2 className="h-4 w-4" />
            Ejecutado ({enqueued.length})
          </h4>
          {enqueued.length === 0 ? (
            <p className="text-sm text-[#64748b]">Ninguna carga se encoló en esta ejecución.</p>
          ) : (
            <ul className="space-y-2">
              {enqueued.map((item) => (
                <li
                  key={item.batch_id || `${item.load_kind}-${item.catalog_slug}-${item.file_name}`}
                  className="flex flex-col gap-1 rounded-md border border-[#e2e8f0] px-3 py-2 text-sm dark:border-[#334155] sm:flex-row sm:items-center sm:justify-between"
                >
                  <div>
                    <span className="font-medium text-[#0f172a] dark:text-[#f1f5f9]">
                      {incrementalExecutionLabel(item)}
                    </span>
                    {item.file_name && (
                      <span className="ml-2 text-[#64748b]">{item.file_name}</span>
                    )}
                    {item.batch_id && (
                      <div className="mt-1">
                        <Link
                          to={`/batches/${item.batch_id}`}
                          className="text-[#3b82f6] hover:underline"
                        >
                          Ver batch
                        </Link>
                      </div>
                    )}
                  </div>
                  <div className="flex flex-wrap items-center gap-2 text-[#64748b]">
                    {item.status && <Badge status={item.status} />}
                    {item.source_rows != null && (
                      <span>{formatNumber(item.source_rows)} en archivo</span>
                    )}
                    {(item.promoted_inserted != null || item.promoted_updated != null) && (
                      <span>
                        {formatPromotedStats(item.promoted_inserted, item.promoted_updated)}
                      </span>
                    )}
                    {Number(item.total_rejected) > 0 && (
                      <span>{formatNumber(item.total_rejected)} rech.</span>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div>
          <h4 className="mb-2 flex items-center gap-2 text-sm font-medium text-amber-700 dark:text-amber-400">
            <XCircle className="h-4 w-4" />
            Omitido / no procesado ({skipped.length})
          </h4>
          {skipped.length === 0 ? (
            <p className="text-sm text-[#64748b]">Todas las cargas configuradas se intentaron procesar.</p>
          ) : (
            <ul className="space-y-2">
              {skipped.map((item, index) => (
                <li
                  key={`${item.load_kind}-${item.catalog_slug || item.granularity}-${index}`}
                  className="rounded-md border border-amber-200 bg-amber-50/50 px-3 py-2 text-sm dark:border-amber-900/50 dark:bg-amber-950/20"
                >
                  <div className="font-medium text-[#0f172a] dark:text-[#f1f5f9]">
                    {incrementalExecutionLabel(item)}
                    {item.file_name && (
                      <span className="ml-2 font-normal text-[#64748b]">{item.file_name}</span>
                    )}
                  </div>
                  <p className="mt-1 text-[#64748b]">{item.reason}</p>
                </li>
              ))}
            </ul>
          )}
        </div>
      </Card>
    </div>
  );
};

export default IncrementalRunDetail;
