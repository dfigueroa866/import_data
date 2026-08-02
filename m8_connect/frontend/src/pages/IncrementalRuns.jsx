import React, { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Layers, ArrowLeft, Trash2 } from 'lucide-react';
import {
  PageHeader,
  Button,
  LoadingSpinner,
  Alert,
  Badge,
  DataTableShell,
  DataTable,
  DataTableHead,
  DataTableBody,
  DataTableRow,
  DataTableTh,
  DataTableTd,
  ConfirmDialog,
} from '../components/ui';
import { formatDate, formatNumber, formatPromotedStats } from '../lib/format';
import { incrementalRunStatusLabel } from '../lib/statusLabels';
import * as incrementalService from '../services/incrementalService';
import { useAuth } from '../context/AuthContext';
import { canEditConfig } from '../utils/permissions';

const IncrementalRuns = () => {
  const { user } = useAuth();
  const canEdit = canEditConfig(user);
  const [data, setData] = useState({ items: [], total: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selectedIds, setSelectedIds] = useState(() => new Set());
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const result = await incrementalService.listRuns({ limit: 50 });
      setData(result);
      setSelectedIds(new Set());
    } catch (err) {
      setError(err.response?.data?.detail || 'Error al cargar ejecuciones');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const pageIds = data.items.map((r) => r.run_id);
  const allSelected = pageIds.length > 0 && pageIds.every((id) => selectedIds.has(id));
  const someSelected = pageIds.some((id) => selectedIds.has(id));

  const toggleOne = (runId) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(runId)) next.delete(runId);
      else next.add(runId);
      return next;
    });
  };

  const toggleAll = () => {
    if (allSelected) {
      setSelectedIds(new Set());
      return;
    }
    setSelectedIds(new Set(pageIds));
  };

  const handleDelete = async () => {
    if (selectedIds.size === 0) return;
    setDeleting(true);
    setError('');
    try {
      await incrementalService.deleteRuns([...selectedIds]);
      setConfirmOpen(false);
      await load();
    } catch (err) {
      const detail = err.response?.data?.detail;
      setError(
        typeof detail === 'string'
          ? detail
          : detail?.message || 'No se pudieron eliminar las ejecuciones'
      );
    } finally {
      setDeleting(false);
    }
  };

  if (loading) return <LoadingSpinner label="Cargando ejecuciones…" />;

  return (
    <div className="flex flex-1 flex-col gap-5 overflow-y-auto p-8 scrollbar-thin">
      <PageHeader
        icon={Layers}
        title="Ejecuciones incremental"
        subtitle={`${data.total} registro(s)`}
        actions={(
          <Link to="/incremental">
            <Button variant="secondary"><ArrowLeft className="mr-2 h-4 w-4" />Volver</Button>
          </Link>
        )}
      />
      {error && <Alert variant="error">{error}</Alert>}

      <DataTableShell
        title="Historial de ejecuciones"
        meta={`${data.items.length} fila(s)`}
        headerActions={
          canEdit ? (
            <Button
              variant="secondary"
              icon={Trash2}
              onClick={() => setConfirmOpen(true)}
              disabled={selectedIds.size === 0 || deleting}
              loading={deleting}
            >
              Eliminar seleccionados
              {selectedIds.size > 0 ? ` (${selectedIds.size})` : ''}
            </Button>
          ) : null
        }
      >
        <DataTable>
          <DataTableHead>
            <DataTableRow>
              {canEdit && (
                <DataTableTh className="w-10 text-center">
                  <input
                    type="checkbox"
                    className="accent-brand-600"
                    checked={allSelected}
                    ref={(el) => {
                      if (el) el.indeterminate = someSelected && !allSelected;
                    }}
                    onChange={toggleAll}
                    aria-label="Seleccionar todas"
                    disabled={deleting || pageIds.length === 0}
                  />
                </DataTableTh>
              )}
              <DataTableTh>Organización</DataTableTh>
              <DataTableTh>Fecha carga</DataTableTh>
              <DataTableTh>Estado</DataTableTh>
              <DataTableTh>Promovidos</DataTableTh>
              <DataTableTh>Rechazados</DataTableTh>
              <DataTableTh>Inicio</DataTableTh>
              <DataTableTh />
            </DataTableRow>
          </DataTableHead>
          <DataTableBody>
            {data.items.map((run) => (
              <DataTableRow key={run.run_id} selected={selectedIds.has(run.run_id)}>
                {canEdit && (
                  <DataTableTd className="text-center">
                    <input
                      type="checkbox"
                      className="accent-brand-600"
                      checked={selectedIds.has(run.run_id)}
                      onChange={() => toggleOne(run.run_id)}
                      aria-label={`Seleccionar ${run.run_id}`}
                      disabled={deleting}
                    />
                  </DataTableTd>
                )}
                <DataTableTd>{run.organization_name || run.organization_id}</DataTableTd>
                <DataTableTd>{run.load_date}</DataTableTd>
                <DataTableTd>
                  <Badge status={run.status} label={incrementalRunStatusLabel(run.status)} />
                </DataTableTd>
                <DataTableTd>{formatPromotedStats(run.total_inserted, run.total_updated)}</DataTableTd>
                <DataTableTd>{formatNumber(run.total_rejected)}</DataTableTd>
                <DataTableTd>{formatDate(run.started_at)}</DataTableTd>
                <DataTableTd>
                  <Link to={`/incremental/runs/${run.run_id}`} className="text-[#3b82f6] text-sm hover:underline">
                    Detalle
                  </Link>
                </DataTableTd>
              </DataTableRow>
            ))}
          </DataTableBody>
        </DataTable>
      </DataTableShell>

      <ConfirmDialog
        isOpen={confirmOpen}
        onClose={() => !deleting && setConfirmOpen(false)}
        onConfirm={handleDelete}
        title="Eliminar ejecuciones"
        message={`Se eliminarán ${selectedIds.size} ejecución(es), incluyendo batches, archivos asociados y datos de historia promovidos. Esta acción no se puede deshacer.`}
        confirmText="Eliminar"
        variant="danger"
        loading={deleting}
      />
    </div>
  );
};

export default IncrementalRuns;
