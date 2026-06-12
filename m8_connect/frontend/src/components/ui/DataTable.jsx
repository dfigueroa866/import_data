import React from 'react';
import { Loader2 } from 'lucide-react';
import { cn } from '../../lib/utils';
import EmptyState from './EmptyState';

export const DataTableShell = ({
  title,
  meta,
  headerActions,
  children,
  loading,
  loadingMessage = 'Cargando…',
  empty,
  emptyTitle,
  emptyDescription,
  className,
  maxHeight = 'calc(100vh - 220px)',
}) => {
  if (loading) {
    return (
      <div className={cn('flex justify-center py-16', className)}>
        <div className="flex flex-col items-center gap-3 text-slate-500">
          <Loader2 className="h-8 w-8 animate-spin text-brand-700" />
          <p className="text-sm m-0">{loadingMessage}</p>
        </div>
      </div>
    );
  }

  if (empty) {
    return (
      <div
        className={cn(
          'flex flex-col overflow-hidden rounded-md border border-[#e2e8f0] bg-white shadow-sm dark:border-[#334155] dark:bg-slate-800',
          className
        )}
      >
        <EmptyState title={emptyTitle} description={emptyDescription} />
      </div>
    );
  }

  return (
    <div
      className={cn(
        'flex flex-col overflow-hidden rounded-md border border-[#e2e8f0] bg-white shadow-sm dark:border-[#334155] dark:bg-slate-800',
        className
      )}
    >
      {(title || headerActions) && (
        <div className="flex flex-wrap items-start justify-between gap-3 border-b border-[#e2e8f0] dark:border-[#334155] px-4 py-3">
          <div>
            {title && (
              <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-100">{title}</h3>
            )}
            {meta && <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5 m-0">{meta}</p>}
          </div>
          {headerActions && <div className="flex flex-wrap gap-2">{headerActions}</div>}
        </div>
      )}
      <div className={cn('overflow-auto scrollbar-thin', maxHeight && `max-h-[${maxHeight}]`)} style={maxHeight ? { maxHeight } : undefined}>
        {children}
      </div>
    </div>
  );
};

export const DataTable = ({ className, children }) => (
  <table className={cn('w-full text-xs border-collapse', className)}>{children}</table>
);

export const DataTableHead = ({ children, className }) => (
  <thead className={cn('sticky top-0 z-10 bg-slate-50 dark:bg-slate-800', className)}>
    {children}
  </thead>
);

export const DataTableBody = ({ children, className }) => (
  <tbody className={cn('divide-y divide-[#e2e8f0] dark:divide-[#334155]', className)}>
    {children}
  </tbody>
);

export const DataTableRow = ({ children, className, selected, onClick }) => (
  <tr
    className={cn(
      'hover:bg-slate-50 dark:hover:bg-slate-700/50 transition-colors',
      selected && 'bg-blue-50/60 dark:bg-blue-950/20',
      onClick && 'cursor-pointer',
      className
    )}
    onClick={onClick}
  >
    {children}
  </tr>
);

export const DataTableTh = ({ children, className, numeric }) => (
  <th
    className={cn(
      'px-3 py-2 text-left font-semibold text-slate-500 dark:text-slate-400',
      'border-r border-slate-100 dark:border-slate-700 last:border-r-0',
      'bg-slate-50 dark:bg-slate-800',
      numeric && 'text-right',
      className
    )}
  >
    {children}
  </th>
);

export const DataTableTd = ({ children, className, numeric, mono, empty }) => (
  <td
    className={cn(
      'px-3 py-2 text-slate-700 dark:text-slate-300',
      'border-r border-slate-100 dark:border-slate-700 last:border-r-0',
      numeric && 'text-right tabular-nums',
      mono && 'font-mono font-medium text-brand-700 dark:text-blue-300',
      empty && 'text-slate-400',
      className
    )}
  >
    {children}
  </td>
);

export const DataTableRowNum = ({ children }) => (
  <td className="px-2 py-2 text-center text-slate-500 bg-slate-50/50 dark:bg-slate-800/50 border-r border-slate-100 dark:border-slate-700 w-10">
    {children}
  </td>
);

export const DataTablePagination = ({ children, className }) => (
  <div
    className={cn(
      'flex items-center justify-center gap-4 px-4 py-3 border-t border-[#e2e8f0] dark:border-[#334155]',
      className
    )}
  >
    {children}
  </div>
);

export default DataTableShell;
