import React, { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { LayoutDashboard, Database, TrendingUp, Activity, Upload as UploadIcon } from 'lucide-react';
import { PageHeader, Card, Badge, LoadingSpinner, Button, Alert } from '../components/ui';
import { formatNumber, formatPercent, formatDateShort } from '../lib/format';
import { monitoringService } from '../services/monitoringService';
import { uploadService } from '../services/uploadService';

const Dashboard = () => {
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [systemStatus, setSystemStatus] = useState(null);
  const [recentBatches, setRecentBatches] = useState([]);
  const [health, setHealth] = useState(null);

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      setLoadError('');
      const [statusData, batchesData, healthData] = await Promise.all([
        monitoringService.getSystemStatus(),
        uploadService.listBatches({ limit: 5 }),
        monitoringService.getHealth(),
      ]);
      setSystemStatus(statusData);
      setRecentBatches(batchesData.batches || []);
      setHealth(healthData);
    } catch (error) {
      console.error('Error loading dashboard:', error);
      setLoadError('No se pudo cargar el panel. Comprueba que el servidor esté en marcha.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  if (loading && !systemStatus && !loadError) {
    return (
      <div className="flex-1 overflow-y-auto p-4 scrollbar-thin">
        <LoadingSpinner size="lg" message="Cargando panel…" />
      </div>
    );
  }

  const stats = systemStatus?.batch_statistics || {};

  const statCards = [
    { label: 'Total de lotes', value: stats.total_batches || 0, icon: Database, color: '#3b82f6', iconBg: 'bg-blue-50 text-brand-600' },
    { label: 'Completados', value: stats.completed_batches || 0, icon: TrendingUp, color: '#34d399', iconBg: 'bg-green-50 text-green-700' },
    { label: 'Fallidos', value: stats.failed_batches || 0, icon: Activity, color: '#f87171', iconBg: 'bg-red-50 text-red-600' },
    { label: 'Tasa de éxito', value: `${formatPercent(stats.success_rate ?? 0)}%`, icon: UploadIcon, color: '#facc15', iconBg: 'bg-yellow-50 text-yellow-700' },
  ];

  return (
    <div className="flex flex-1 flex-col gap-5 overflow-y-auto p-4 scrollbar-thin">
      <PageHeader icon={LayoutDashboard} title="Panel" subtitle="Resumen del sistema y actividad reciente" />

      {loadError && (
        <Alert variant="error">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <span>{loadError}</span>
            <Button variant="secondary" size="sm" onClick={loadData} loading={loading}>
              Reintentar
            </Button>
          </div>
        </Alert>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
        {statCards.map((s) => (
          <Card key={s.label} indicatorColor={s.color} bodyClassName="p-4">
            <div className="flex items-start gap-3 -m-4 p-4">
              <span className={`flex h-10 w-10 items-center justify-center rounded-lg flex-shrink-0 ${s.iconBg}`}>
                <s.icon size={20} />
              </span>
              <div>
                <p className="text-xs text-slate-500 m-0 mb-1">{s.label}</p>
                <p className="font-display text-3xl font-bold tracking-tight text-slate-900 dark:text-slate-100 m-0">{s.value}</p>
              </div>
            </div>
          </Card>
        ))}
      </div>

      <Card title="Salud del sistema" indicatorColor="#34d399">
        <div className="flex items-center gap-4">
          <Badge status={health?.status || 'unknown'} />
          <span className="text-sm text-slate-600 dark:text-slate-300">
            {health?.status === 'healthy' ? 'Todos los sistemas operativos' : 'Se detectaron problemas en el sistema'}
          </span>
        </div>
      </Card>

      <Card title="Lotes recientes" subtitle="Últimas cargas de archivos" indicatorColor="#8b5cf6">
        {recentBatches.length > 0 ? (
          <div className="overflow-x-auto -mx-4 -mb-4">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-slate-50 dark:bg-slate-800">
                <tr>
                  {['ID de lote', 'Fuente', 'Estado', 'Registros', 'Creado'].map((h) => (
                    <th key={h} className="px-4 py-2 text-left font-semibold text-slate-500 border-b border-[#e2e8f0]">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-[#e2e8f0]">
                {recentBatches.map((batch) => (
                  <tr key={batch.batch_id} className="hover:bg-slate-50 dark:hover:bg-slate-700/50">
                    <td className="px-4 py-2 font-mono text-xs whitespace-nowrap text-brand-700 dark:text-blue-300">{batch.batch_id}</td>
                    <td className="px-4 py-2">{batch.source_name || '—'}</td>
                    <td className="px-4 py-2"><Badge status={batch.status} /></td>
                    <td className="px-4 py-2">{formatNumber(batch.records_count || 0)}</td>
                    <td className="px-4 py-2">{formatDateShort(batch.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-center text-slate-500 py-8 m-0">No se encontraron lotes</p>
        )}
        <div className="mt-4 pt-4 border-t border-[#e2e8f0] flex justify-end">
          <Link to="/batches"><Button variant="ghost">Ver todos los lotes →</Button></Link>
        </div>
      </Card>
    </div>
  );
};

export default Dashboard;
