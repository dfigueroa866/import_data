import React from 'react';
import { cn } from '../../lib/utils';

const variants = {
  error: 'bg-red-50 text-red-600 border-red-200 dark:bg-red-950/40 dark:text-red-400 dark:border-red-800',
  success: 'bg-green-50 text-green-700 border-green-200 dark:bg-green-950/40 dark:text-green-400 dark:border-green-800',
  warning: 'bg-yellow-50 text-yellow-700 border-yellow-200 dark:bg-yellow-950/40 dark:text-yellow-400 dark:border-yellow-800',
  info: 'bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-950/40 dark:text-blue-400 dark:border-blue-800',
};

const Alert = ({ variant = 'error', children, className, onClose }) => (
  <div
    role="alert"
    className={cn(
      'text-sm rounded-lg px-3 py-2 border flex items-start justify-between gap-2',
      variants[variant],
      className
    )}
  >
    <div className="flex-1">{children}</div>
    {onClose && (
      <button
        type="button"
        onClick={onClose}
        className="opacity-75 hover:opacity-100 text-lg leading-none"
        aria-label="Cerrar"
      >
        ×
      </button>
    )}
  </div>
);

export default Alert;
