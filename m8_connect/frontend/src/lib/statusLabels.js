/** Etiquetas en español para estados de lotes y badges del sistema. */

export const STATUS_LABELS = {
  completed: 'Completado',
  success: 'Éxito',
  passed: 'Aprobado',
  promoted: 'Promovido',
  healthy: 'Saludable',
  connected: 'Conectado',
  failed: 'Fallido',
  error: 'Error',
  rejected: 'Rechazado',
  disconnected: 'Desconectado',
  pending: 'Pendiente',
  queued: 'En cola',
  waiting: 'En espera',
  processing: 'Procesando',
  in_progress: 'En progreso',
  running: 'En ejecución',
  partially_promoted: 'Parcialmente promovido',
  cancelled: 'Cancelado',
  unknown: 'Desconocido',
  pending_process: 'Pendiente de proceso',
  pending_mapping: 'Pendiente de mapeo',
  pending_preview: 'Pendiente de vista previa',
};

export const BATCH_STATUS_FILTER_OPTIONS = [
  { value: '', label: 'Todos los estados' },
  { value: 'PENDING', label: 'Pendiente' },
  { value: 'PENDING_PROCESS', label: 'Pendiente de proceso' },
  { value: 'PROCESSING', label: 'Procesando' },
  { value: 'COMPLETED', label: 'Completado' },
  { value: 'PARTIALLY_PROMOTED', label: 'Parcialmente promovido' },
  { value: 'FAILED', label: 'Fallido' },
  { value: 'CANCELLED', label: 'Cancelado' },
  { value: 'PROMOTED', label: 'Promovido' },
];

export const getStatusLabel = (status) => {
  if (!status) return STATUS_LABELS.unknown;
  const key = String(status).toLowerCase();
  return STATUS_LABELS[key] || status;
};

export const CATALOG_SLUG_LABELS = {
  skus: 'Productos (SKUs)',
  location: 'Ubicaciones',
};

export const formatMissingCatalogs = (missing) => {
  if (!Array.isArray(missing) || missing.length === 0) return null;
  return missing.map((slug) => CATALOG_SLUG_LABELS[slug] || slug).join(', ');
};

const INCREMENTAL_RUN_STATUS_LABELS = {
  COMPLETED: 'Completada',
  FAILED: 'Fallida',
  PROCESSING: 'En proceso',
  NOTIFICATION_FAILED: 'Completada (aviso no enviado)',
  PENDING: 'Pendiente',
};

export const incrementalRunStatusLabel = (status) =>
  INCREMENTAL_RUN_STATUS_LABELS[status] || getStatusLabel(status);

export const incrementalBatchLabel = (batch) => {
  if (!batch) return '—';
  const catalog = batch.catalog_name || batch.target_table;
  if (catalog) {
    return CATALOG_SLUG_LABELS[catalog] || catalog;
  }
  if (batch.load_type === 'history') return 'Historia';
  return batch.file_name || batch.source_name || batch.load_type || '—';
};

export const incrementalExecutionLabel = (item) => {
  if (!item) return '—';
  if (item.load_kind === 'history') {
    return item.granularity === 'monthly' ? 'Historia mensual' : 'Historia semanal';
  }
  if (item.catalog_slug) {
    return CATALOG_SLUG_LABELS[item.catalog_slug] || item.catalog_slug;
  }
  return item.load_kind === 'catalog' ? 'Catálogo' : '—';
};
