import React from 'react';
import { cn } from '../../lib/utils';

const EmptyState = ({ title, description, action, className }) => (
  <div className={cn('text-center py-10 px-6', className)}>
    {title && <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-100 mb-2">{title}</h3>}
    {description && <p className="text-sm text-slate-500 dark:text-slate-400 m-0">{description}</p>}
    {action && <div className="mt-4">{action}</div>}
  </div>
);

export default EmptyState;
