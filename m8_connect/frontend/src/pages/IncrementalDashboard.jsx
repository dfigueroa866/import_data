import React, { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { TrendingUp, Calendar, Building2, Play, Layers, Trash2 } from 'lucide-react';
import {
  PageHeader,
  Button,
  Card,
  LoadingSpinner,
  Alert,
  SummaryGrid,
  SummaryBlock,
  ConfirmDialog,
} from '../components/ui';
import { formatPromotedStats } from '../lib/format';
import { incrementalRunStatusLabel } from '../lib/statusLabels';
import { describeWeeklyCron } from '../lib/cronSchedule';
import * as incrementalService from '../services/incrementalService';
import { useAuth } from '../context/AuthContext';
import { canEditConfig } from '../utils/permissions';

const IncrementalDashboard = () => {
  const { user } = useAuth();
  const canEdit = canEditConfig(user);
  const [schedule, setSchedule] = useState(null);
  const [runs, setRuns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [triggering, setTriggering] = useState(false);
  const [selectedIds, setSelectedIds] = useState(() => new Set());
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [sched, runData] = await Promise.all([
        incrementalService.getSchedule().catch(() => null),
        incrementalService.listRuns({ limit: 5 }),
      ]);
      setSchedule(sched);
      setRuns(runData.items || []);
      setSelectedIds(new Set());
    } catch (err) {
      setError(err.response?.data?.detail || 'No se pudo cargar el panel incremental');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const toggleOne = (runId) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(runId)) next.delete(runId);
      else next.add(runId);
      return next;
    });
  };

  const allSelected = runs.length > 0 && runs.every((r) => selectedIds.has(r.run_id));
  const someSelected = runs.some((r) => selectedIds.has(r.run_id));

  const toggleAll = () => {
    if (allSelected) {
      setSelectedIds(new Set());
      return;
    }
    setSelectedIds(new Set(runs.map((r) => r.run_id)));
  };

  const handleTrigger = async () => {
    setTriggering(true);
    try {
      await incrementalService.triggerRun();
      await load();
    } catch (err) {
      setError(err.response?.data?.detail || 'Error al disparar carga');
    } finally {
      setTriggering(false);
    }
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

  if (loading) return <LoadingSpinner label="Cargando incremental…" />;

  return (
    <div className="flex flex-1 flex-col gap-5 overflow-y-auto p-8 scrollbar-thin">
      <PageHeader
        icon={TrendingUp}
        title="Carga incremental"
        subtitle="Configuración y monitoreo de cargas automáticas semanales/mensuales"
        actions={canEdit ? (
          <Button onClick={handleTrigger} disabled={triggering}>
            <Play className="mr-2 h-4 w-4" />
            {triggering ? 'Ejecutando…' : 'Ejecutar ahora'}
          </Button>
        ) : null}
      />

      {error && <Alert variant="error">{error}</Alert>}

      <SummaryGrid>
        <SummaryBlock
          label="Programación"
          value={schedule?.enabled ? 'Activa' : 'Inactiva'}
          hint={schedule
            ? describeWeeklyCron(schedule.cron_expression, schedule.timezone)
            : 'Sin configurar'}
        />
        <SummaryBlock
          label="Retención"
          value={schedule ? `${schedule.retention_years} años` : '—'}
        />
        <SummaryBlock
          label="Zona horaria"
          value={schedule?.timezone || '—'}
        />
      </SummaryGrid>

      <div className="grid gap-4 md:grid-cols-3">
        <Link to="/incremental/schedule" className="block">
          <Card className="p-5 hover:border-[#3b82f6] dark:hover:border-[#60a5fa]">
            <Calendar className="mb-2 h-8 w-8 text-[#3b82f6]" />
            <h3 className="font-semibold text-[#0f172a] dark:text-[#f1f5f9]">Programación</h3>
            <p className="text-sm text-[#64748b]">Cron, zona horaria y retención</p>
          </Card>
        </Link>
        <Link to="/incremental/organizations" className="block">
          <Card className="p-5 hover:border-[#3b82f6] dark:hover:border-[#60a5fa]">
            <Building2 className="mb-2 h-8 w-8 text-[#3b82f6]" />
            <h3 className="font-semibold text-[#0f172a] dark:text-[#f1f5f9]">Organizaciones</h3>
            <p className="text-sm text-[#64748b]">Rutas de origen y tablas</p>
          </Card>
        </Link>
        <Link to="/incremental/runs" className="block">
          <Card className="p-5 hover:border-[#3b82f6] dark:hover:border-[#60a5fa]">
            <Layers className="mb-2 h-8 w-8 text-[#3b82f6]" />
            <h3 className="font-semibold text-[#0f172a] dark:text-[#f1f5f9]">Ejecuciones</h3>
            <p className="text-sm text-[#64748b]">Historial y detalle de cargas</p>
          </Card>
        </Link>
      </div>

      <Card className="p-5">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <h3 className="font-semibold text-[#0f172a] dark:text-[#f1f5f9]">Últimas ejecuciones</h3>
          {canEdit && runs.length > 0 && (
            <Button
              variant="secondary"
              size="sm"
              icon={Trash2}
              onClick={() => setConfirmOpen(true)}
              disabled={selectedIds.size === 0 || deleting}
              loading={deleting}
            >
              Eliminar
              {selectedIds.size > 0 ? ` (${selectedIds.size})` : ''}
            </Button>
          )}
        </div>
        {runs.length === 0 ? (
          <p className="text-sm text-[#64748b]">Sin ejecuciones registradas.</p>
        ) : (
          <ul className="space-y-2">
            <li className="flex items-center gap-3 border-b border-[#e2e8f0] pb-2 text-xs text-[#64748b] dark:border-[#334155]">
              {canEdit && (
                <input
                  type="checkbox"
                  className="accent-brand-600"
                  checked={allSelected}
                  ref={(el) => {
                    if (el) el.indeterminate = someSelected && !allSelected;
                  }}
                  onChange={toggleAll}
                  aria-label="Seleccionar todas"
                  disabled={deleting}
                />
              )}
              <span>Seleccionar</span>
            </li>
            {runs.map((run) => (
              <li key={run.run_id} className="flex items-center gap-3 text-sm">
                {canEdit && (
                  <input
                    type="checkbox"
                    className="accent-brand-600 shrink-0"
                    checked={selectedIds.has(run.run_id)}
                    onChange={() => toggleOne(run.run_id)}
                    aria-label={`Seleccionar ejecución ${run.run_id}`}
                    disabled={deleting}
                  />
                )}
                <Link
                  to={`/incremental/runs/${run.run_id}`}
                  className="min-w-0 flex-1 text-[#3b82f6] hover:underline"
                >
                  {run.organization_name || run.organization_id} — {run.load_date}
                </Link>
                <span className="shrink-0 text-[#64748b]">
                  {incrementalRunStatusLabel(run.status)}
                  {' · '}
                  {formatPromotedStats(run.total_inserted, run.total_updated)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>

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

export default IncrementalDashboard;
