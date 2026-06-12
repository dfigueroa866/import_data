import React from 'react';
import { cn } from '../../lib/utils';

export const SummaryBlock = ({ title, children, className, accent }) => (
  <div
    className={cn(
      'rounded-md border border-[#e2e8f0] bg-white p-4 shadow-sm dark:border-[#334155] dark:bg-slate-800',
      accent && 'border-l-4 border-l-brand-600',
      className
    )}
  >
    {title && (
      <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 block mb-3">
        {title}
      </span>
    )}
    {children}
  </div>
);

export const SummaryGrid = ({ children, columns = 4, className }) => (
  <div
    className={cn(
      'grid gap-4',
      columns === 4 && 'grid-cols-2 lg:grid-cols-4',
      columns === 3 && 'grid-cols-1 sm:grid-cols-3',
      columns === 2 && 'grid-cols-1 sm:grid-cols-2',
      className
    )}
  >
    {children}
  </div>
);

export const StatItem = ({ label, value, icon: Icon, variant = 'default', className }) => {
  const valueColors = {
    default: 'text-slate-900 dark:text-slate-100',
    success: 'text-green-700 dark:text-green-400',
    danger: 'text-red-600 dark:text-red-400',
    brand: 'text-brand-700 dark:text-blue-400',
  };

  return (
    <div className={cn('flex items-start gap-3', className)}>
      {Icon && (
        <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-blue-50 text-brand-600 dark:bg-blue-950/40 dark:text-blue-400 flex-shrink-0">
          <Icon size={20} />
        </span>
      )}
      <div>
        <p className="text-xs text-slate-500 dark:text-slate-400 m-0 mb-0.5">{label}</p>
        <p className={cn('text-2xl font-bold tracking-tight m-0', valueColors[variant])}>{value}</p>
      </div>
    </div>
  );
};

export default SummaryGrid;
