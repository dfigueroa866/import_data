import React from 'react';
import { cn } from '../../lib/utils';

const STATUS_MAP = {
  completed: { variant: 'success', label: 'completed' },
  success: { variant: 'success', label: 'success' },
  passed: { variant: 'success', label: 'passed' },
  promoted: { variant: 'success', label: 'promoted' },
  healthy: { variant: 'success', label: 'healthy' },
  connected: { variant: 'success', label: 'connected' },
  failed: { variant: 'error', label: 'failed' },
  error: { variant: 'error', label: 'error' },
  rejected: { variant: 'error', label: 'rejected' },
  disconnected: { variant: 'error', label: 'disconnected' },
  pending: { variant: 'pending', label: 'pending' },
  queued: { variant: 'pending', label: 'queued' },
  waiting: { variant: 'pending', label: 'waiting' },
  processing: { variant: 'processing', label: 'processing' },
  in_progress: { variant: 'processing', label: 'in_progress' },
  running: { variant: 'processing', label: 'running' },
  partially_promoted: { variant: 'warning', label: 'partially_promoted' },
  cancelled: { variant: 'default', label: 'cancelled' },
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
  const info = STATUS_MAP[key] || { variant: 'default', label: status };
  const displayLabel = label ?? info.label;
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
