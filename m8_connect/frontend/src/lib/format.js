export const LOCALE = 'es-MX';
export const EMPTY = '—';

export const formatNumber = (n, options) => {
  if (n == null || Number.isNaN(Number(n))) return EMPTY;
  return Number(n).toLocaleString(LOCALE, options);
};

export const formatPercent = (n, fractionDigits = 1) => {
  if (n == null || Number.isNaN(Number(n))) return EMPTY;
  return Number(n).toLocaleString(LOCALE, {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  });
};

export const formatDate = (value, options = {}) => {
  if (value == null || value === '') return EMPTY;
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return EMPTY;
  return date.toLocaleString(LOCALE, {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    ...options,
  });
};

export const formatDateShort = (value) =>
  formatDate(value, { hour: undefined, minute: undefined });

export const formatTime = (value) => {
  if (value == null || value === '') return EMPTY;
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return EMPTY;
  return date.toLocaleTimeString(LOCALE);
};

export const formatFileSize = (bytes) => {
  if (!bytes) return EMPTY;
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(2)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
};

/** Resumen legible de filas promovidas (insertadas vs actualizadas). */
export const formatPromotedStats = (inserted, updated) => {
  const ins = Number(inserted) || 0;
  const upd = Number(updated) || 0;
  if (ins === 0 && upd === 0) return 'sin cambios en BD';
  const parts = [];
  if (ins > 0) parts.push(`${formatNumber(ins)} nuevos`);
  if (upd > 0) parts.push(`${formatNumber(upd)} actualizados`);
  return parts.join(' · ');
};

export const formatDurationSeconds = (seconds) => {
  const total = Math.max(0, Math.floor(Number(seconds) || 0));
  if (total < 60) return `${total}s`;
  if (total < 3600) {
    const minutes = Math.floor(total / 60);
    const secs = total % 60;
    return secs ? `${minutes}m ${secs}s` : `${minutes}m`;
  }
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  const parts = [`${hours}h`];
  if (minutes) parts.push(`${minutes}m`);
  if (secs && hours < 2) parts.push(`${secs}s`);
  return parts.join(' ');
};
