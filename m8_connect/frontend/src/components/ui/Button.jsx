import React from 'react';
import { Loader2 } from 'lucide-react';
import { cn } from '../../lib/utils';

const variants = {
  primary: 'bg-brand-600 text-white hover:bg-brand-700',
  secondary: 'bg-white text-gray-700 border border-gray-300 hover:bg-gray-50 dark:bg-slate-800 dark:text-slate-100 dark:border-slate-600 dark:hover:bg-slate-700',
  danger: 'bg-red-600 text-white hover:bg-red-700',
  success: 'bg-green-700 text-white hover:bg-green-800',
  warning: 'bg-amber-600 text-white hover:bg-amber-700',
  ghost: 'bg-transparent text-slate-600 hover:bg-slate-100 hover:text-brand-700 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-blue-300',
};

const sizes = {
  sm: 'text-xs px-2.5 py-1.5',
  md: 'text-sm px-3.5 py-2',
  lg: 'text-base px-4 py-2.5',
};

const iconSizes = { sm: 16, md: 16, lg: 20 };

const Button = ({
  children,
  variant = 'primary',
  size = 'md',
  onClick,
  disabled = false,
  type = 'button',
  className,
  icon: Icon,
  loading = false,
  loadingLabel = 'Cargando…',
}) => {
  return (
    <button
      type={type}
      className={cn(
        'inline-flex items-center justify-center gap-1.5 font-medium rounded-lg transition-colors disabled:cursor-not-allowed',
        !loading && 'disabled:opacity-50',
        loading && 'cursor-wait',
        variants[variant],
        sizes[size],
        className
      )}
      onClick={onClick}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
    >
      {loading ? (
        <>
          <Loader2 className={cn('animate-spin shrink-0', size === 'lg' ? 'h-5 w-5' : 'h-4 w-4')} />
          <span>{loadingLabel}</span>
        </>
      ) : (
        <>
          {Icon && <Icon size={iconSizes[size]} />}
          <span>{children}</span>
        </>
      )}
    </button>
  );
};

export default Button;
