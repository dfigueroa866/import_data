import React, { useState, useEffect, useCallback } from 'react';
import { Activity, TrendingUp, Clock } from 'lucide-react';
import { PageHeader, Card, Badge, LoadingSpinner, Alert, Button } from '../components/ui';
import { formatPercent, formatTime } from '../lib/format';
import { monitoringService } from '../services/monitoringService';

const Monitoring = () => {
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [loadError, setLoadError] = useState('');
  const [systemStatus, setSystemStatus] = useState(null);
  const [health, setHealth] = useState(null);

  const loadData = useCallback(async (isRefresh = false) => {
    try {
      if (isRefresh) {
        setRefreshing(true);
      } else {
        setLoading(true);
      }
      setLoadError('');
      const [statusData, healthData] = await Promise.all([
        monitoringService.getSystemStatus(),
        monitoringService.getHealth(),
      ]);
      setSystemStatus(statusData);
      setHealth(healthData);
    } catch (error) {
      console.error('Error loading monitoring data:', error);
      setLoadError('No se pudo cargar el monitoreo. Comprueba que el servidor esté en marcha.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadData(false);
    const interval = setInterval(() => loadData(true), 30000);
    return () => clearInterval(interval);
  }, [loadData]);

  if (loading && !systemStatus && !loadError) {
    return (
      <div className="flex-1 overflow-y-auto p-8 scrollbar-thin">
        <LoadingSpinner size="lg" message="Cargando monitoreo…" />
      </div>
    );
  }

  const stats = systemStatus?.batch_statistics || {};

  const statRows = [
    { label: 'Total de lotes', value: stats.total_batches || 0 },
    { label: 'Completados', value: stats.completed_batches || 0, success: true },
    { label: 'Fallidos', value: stats.failed_batches || 0, error: true },
  ];

  return (
    <div className="flex flex-1 flex-col gap-5 overflow-y-auto p-8 scrollbar-thin">
      <PageHeader
        icon={Activity}
        title="Monitoreo"
        subtitle="Salud del sistema y métricas de rendimiento"
        action={
          refreshing ? (
            <span className="text-xs text-slate-500">Actualizando…</span>
          ) : null
        }
      />

      {loadError && (
        <Alert variant="error">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <span>{loadError}</span>
            <Button variant="secondary" size="sm" onClick={() => loadData(false)} loading={loading}>
              Reintentar
            </Button>
          </div>
        </Alert>
      )}

      <Card title="Salud del sistema" indicatorColor="#34d399">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
          <div>
            <div className="flex items-center gap-2 text-sm text-slate-500 mb-2"><Activity size={16} /><span>Estado</span></div>
            <Badge status={health?.status || 'unknown'} />
          </div>
          <div>
            <div className="flex items-center gap-2 text-sm text-slate-500 mb-2"><Clock size={16} /><span>Última verificación</span></div>
            <span className="text-base font-semibold text-slate-900 dark:text-slate-100">{health?.timestamp ? formatTime(health.timestamp) : '—'}</span>
          </div>
          <div>
            <div className="flex items-center gap-2 text-sm text-slate-500 mb-2"><TrendingUp size={16} /><span>Entorno</span></div>
            <span className="text-base font-semibold text-slate-900 dark:text-slate-100">{health?.environment || '—'}</span>
          </div>
        </div>
      </Card>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card title="Estadísticas de lotes" indicatorColor="#3b82f6">
          <div className="flex flex-col gap-1">
            {statRows.map((row) => (
              <div key={row.label} className="flex justify-between py-2 border-b border-[#e2e8f0] last:border-0">
                <span className="text-sm text-slate-500">{row.label}</span>
                <span className={`font-semibold ${row.success ? 'text-green-700' : row.error ? 'text-red-600' : 'text-slate-900 dark:text-slate-100'}`}>{row.value}</span>
              </div>
            ))}
            <div className="flex justify-between py-3 mt-2 px-3 rounded-lg bg-slate-50 dark:bg-slate-700/50">
              <span className="text-sm font-medium text-slate-900 dark:text-slate-100">Tasa de éxito</span>
              <span className="text-xl font-bold text-brand-700">{formatPercent(stats.success_rate ?? 0)}%</span>
            </div>
          </div>
        </Card>

        <Card title="Base de datos" indicatorColor="#8b5cf6">
          <div className="flex flex-col gap-1">
            <div className="flex justify-between py-2 border-b border-[#e2e8f0]">
              <span className="text-sm text-slate-500">Estado</span>
              <Badge status={health?.database_connected ? 'connected' : 'disconnected'} />
            </div>
            <div className="flex justify-between py-2">
              <span className="text-sm text-slate-500">Tipo</span>
              <span className="font-semibold text-slate-900 dark:text-slate-100">{health?.database?.type || 'Desconocido'}</span>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
};

export default Monitoring;
