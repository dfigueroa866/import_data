import React from 'react';
import { cn } from '../../lib/utils';

const INDICATOR_COLORS = {
  blue: 'bg-blue-500',
  emerald: 'bg-emerald-500',
  violet: 'bg-violet-500',
  red: 'bg-red-400',
  orange: 'bg-orange-300',
  yellow: 'bg-yellow-300',
};

const Card = ({
  children,
  title,
  subtitle,
  indicatorColor,
  indicator,
  className,
  hoverable,
  onClick,
  bodyClassName,
}) => {
  const indicatorClass =
    indicator ||
    (indicatorColor && !indicatorColor.startsWith('#')
      ? INDICATOR_COLORS[indicatorColor]
      : null);

  return (
    <div
      className={cn(
        'flex flex-col overflow-hidden rounded-md border border-[#e2e8f0] bg-white shadow-sm',
        'dark:border-[#334155] dark:bg-slate-800',
        hoverable && 'transition-shadow hover:shadow-md',
        onClick && 'cursor-pointer',
        className
      )}
      onClick={onClick}
    >
      {(title || subtitle) && (
        <div className="flex items-center gap-2 border-b border-[#e2e8f0] dark:border-[#334155] p-2">
          {(indicatorClass || indicatorColor) && (
            <span
              className={cn('h-3 w-3 rounded-sm flex-shrink-0', indicatorClass)}
              style={indicatorColor?.startsWith('#') ? { background: indicatorColor } : undefined}
            />
          )}
          <div className="min-w-0">
            {title && (
              <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-100 truncate">
                {title}
              </h3>
            )}
            {subtitle && (
              <p className="text-xs text-slate-500 dark:text-slate-400 truncate">{subtitle}</p>
            )}
          </div>
        </div>
      )}
      <div className={cn('p-4 text-body-md text-slate-600 dark:text-slate-300', bodyClassName)}>
        {children}
      </div>
    </div>
  );
};

export default Card;
