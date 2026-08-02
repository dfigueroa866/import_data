import React from 'react';
import { cn } from '../../lib/utils';
import { getStatusLabel } from '../../lib/statusLabels';

const STATUS_MAP = {
  completed: { variant: 'success' },
  success: { variant: 'success' },
  passed: { variant: 'success' },
  promoted: { variant: 'success' },
  healthy: { variant: 'success' },
  connected: { variant: 'success' },
  failed: { variant: 'error' },
  error: { variant: 'error' },
  rejected: { variant: 'error' },
  disconnected: { variant: 'error' },
  pending: { variant: 'pending' },
  queued: { variant: 'pending' },
  waiting: { variant: 'pending' },
  processing: { variant: 'processing' },
  in_progress: { variant: 'processing' },
  running: { variant: 'processing' },
  partially_promoted: { variant: 'warning' },
  cancelled: { variant: 'default' },
  pending_process: { variant: 'pending' },
  pending_mapping: { variant: 'pending' },
  pending_preview: { variant: 'pending' },
};

const variantStyles = {
  success: 'bg-green-50 text-green-700 border-green-200 dark:bg-green-950/40 dark:text-green-400 dark:border-green-800',
  error: 'bg-red-50 text-red-700 border-red-200 dark:bg-red-950/40 dark:text-red-400 dark:border-red-800',
  pending: 'bg-yellow-50 text-yellow-700 border-yellow-200 dark:bg-yellow-950/40 dark:text-yellow-400 dark:border-yellow-800',
  processing: 'bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-950/40 dark:text-blue-400 dark:border-blue-800',
  warning: 'bg-yellow-50 text-yellow-700 border-yellow-200 dark:bg-yellow-950/40 dark:text-yellow-400 dark:border-yellow-800',
  default: 'bg-slate-100 text-slate-600 border-slate-200 dark:bg-slate-700 dark:text-slate-300 dark:border-slate-600',
};

const dotStyles = {
  success: 'bg-green-600',
  error: 'bg-red-600',
  pending: 'bg-yellow-600',
  processing: 'bg-blue-600 animate-pulse',
  warning: 'bg-yellow-600',
  default: 'bg-slate-400',
};

const Badge = ({ status, label, className }) => {
  const key = status?.toLowerCase() || '';
  const info = STATUS_MAP[key] || { variant: 'default' };
  const displayLabel = label ?? getStatusLabel(status);
  const variant = info.variant;

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-medium',
        variantStyles[variant],
        className
      )}
    >
      <span className={cn('h-1.5 w-1.5 rounded-full flex-shrink-0', dotStyles[variant])} />
      {displayLabel}
    </span>
  );
};

export default Badge;
