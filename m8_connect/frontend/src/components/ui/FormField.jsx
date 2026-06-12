import React from 'react';
import { cn } from '../../lib/utils';

/** Clases canónicas para inputs/selects — ver DESIGN_STYLE.md §6.2 */
export const inputClasses = cn(
  'w-full px-3 py-2 rounded-lg text-sm shadow-sm',
  'border border-[#e2e8f0] bg-white text-slate-900',
  'placeholder:text-slate-400',
  'focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent',
  'disabled:bg-slate-50 disabled:opacity-60 disabled:cursor-not-allowed',
  'dark:bg-slate-800 dark:border-[#334155] dark:text-slate-100 dark:placeholder:text-slate-500',
  'dark:disabled:bg-slate-900'
);

const inputBase = inputClasses;

/** Variante para selects/inputs con valor mapeado (paso 2 del wizard) */
export const inputMappedClasses = cn(
  inputClasses,
  'border-brand-600 bg-blue-50 text-slate-900 font-medium',
  'dark:border-brand-500 dark:bg-blue-950/30 dark:text-slate-100'
);

/** Clases para <option> cuando se necesiten inline (listas nativas) */
export const selectOptionClasses =
  'bg-white text-slate-900 dark:bg-slate-800 dark:text-slate-100';

const FormField = ({
  label,
  htmlFor,
  error,
  hint,
  className,
  children,
  required,
}) => (
  <div className={cn('flex flex-col gap-1.5', className)}>
    {label && (
      <label
        htmlFor={htmlFor}
        className="text-sm font-medium text-gray-700 dark:text-gray-300"
      >
        {label}
        {required && <span className="text-red-600 ml-0.5">*</span>}
      </label>
    )}
    {hint && <p className="text-xs text-slate-500 dark:text-slate-400">{hint}</p>}
    {children}
    {error && <p className="text-xs text-red-600 dark:text-red-400">{error}</p>}
  </div>
);

export const Input = React.forwardRef(({ className, icon: Icon, ...props }, ref) => (
  <div className="relative">
    {Icon && (
      <Icon className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400 pointer-events-none" />
    )}
    <input
      ref={ref}
      className={cn(inputBase, Icon && 'pl-10', className)}
      {...props}
    />
  </div>
));
Input.displayName = 'Input';

export const Select = React.forwardRef(({ className, children, ...props }, ref) => (
  <select ref={ref} className={cn('nc-select', inputBase, className)} {...props}>
    {children}
  </select>
));
Select.displayName = 'Select';

export const Textarea = React.forwardRef(({ className, ...props }, ref) => (
  <textarea
    ref={ref}
    className={cn(inputBase, 'font-mono text-xs min-h-[100px]', className)}
    {...props}
  />
));
Textarea.displayName = 'Textarea';

export default FormField;
