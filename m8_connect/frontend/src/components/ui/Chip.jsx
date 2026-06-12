import React from 'react';
import { X } from 'lucide-react';
import { cn } from '../../lib/utils';

const Chip = ({ children, onRemove, invalid, className }) => (
  <span
    className={cn(
      'inline-flex items-center gap-1 rounded-full bg-slate-100 px-1.5 py-0 text-[10px] font-medium text-slate-600',
      'dark:bg-slate-700 dark:text-slate-300',
      invalid && 'bg-red-50 text-red-700 border border-red-200 dark:bg-red-950/40',
      className
    )}
  >
    {children}
    {onRemove && (
      <button
        type="button"
        onClick={onRemove}
        className="hover:text-slate-900 dark:hover:text-white"
        aria-label="Eliminar"
      >
        <X size={12} />
      </button>
    )}
  </span>
);

export default Chip;
