import React from 'react';
import { Moon, Sun } from 'lucide-react';
import { useTheme } from '../../context/ThemeContext';
import { cn } from '../../lib/utils';

/**
 * FAB icono claro/oscuro — esquina inferior derecha (DESIGN_STYLE.md §11).
 */
const ThemeToggle = ({ className }) => {
  const { isDark, toggleTheme } = useTheme();

  return (
    <button
      type="button"
      onClick={toggleTheme}
      className={cn(
        'fixed bottom-5 right-5 z-50',
        'flex h-10 w-10 items-center justify-center rounded-lg',
        'border border-[#e2e8f0] bg-white text-slate-600 shadow-sm',
        'hover:bg-slate-100 hover:text-brand-600',
        'transition-colors duration-200',
        'dark:border-[#334155] dark:bg-slate-800 dark:text-slate-300',
        'dark:hover:bg-slate-700 dark:hover:text-brand-400',
        className
      )}
      aria-label={isDark ? 'Cambiar a modo claro' : 'Cambiar a modo oscuro'}
      title={isDark ? 'Modo claro' : 'Modo oscuro'}
    >
      {isDark ? <Sun size={18} strokeWidth={2} /> : <Moon size={18} strokeWidth={2} />}
    </button>
  );
};

export default ThemeToggle;
