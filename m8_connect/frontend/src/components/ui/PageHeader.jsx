import React from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { cn } from '../../lib/utils';

const PageHeader = ({ icon: Icon, title, subtitle, action, backTo, backLabel, className }) => (
  <header className={cn('mb-5', className)}>
    {backTo && (
      <Link
        to={backTo}
        className="inline-flex items-center gap-1 mb-2 text-sm text-slate-500 hover:text-brand-600 transition-colors"
      >
        <ArrowLeft size={16} />
        <span>{backLabel || 'Volver'}</span>
      </Link>
    )}
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div className="flex items-start gap-2 min-w-0">
        {Icon && (
          <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-100 text-brand-700 dark:bg-blue-950/50 dark:text-blue-300 flex-shrink-0">
            <Icon size={20} />
          </span>
        )}
        <div className="min-w-0">
          <h1 className="text-xl font-bold tracking-tight text-slate-900 dark:text-slate-100">
            {title}
          </h1>
          {subtitle && (
            <div className="text-sm text-slate-500 dark:text-slate-400 mt-0.5">{subtitle}</div>
          )}
        </div>
      </div>
      {action && <div className="flex-shrink-0">{action}</div>}
    </div>
  </header>
);

export default PageHeader;
