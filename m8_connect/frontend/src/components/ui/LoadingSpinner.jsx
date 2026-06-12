import React from 'react';
import { Loader2 } from 'lucide-react';
import { cn } from '../../lib/utils';

const sizes = { sm: 'h-6 w-6', md: 'h-10 w-10', lg: 'h-14 w-14' };

const LoadingSpinner = ({ size = 'md', message, className }) => (
  <div className={cn('flex flex-col items-center justify-center gap-3 p-8', className)}>
    <Loader2 className={cn('animate-spin text-brand-700', sizes[size])} />
    {message && <p className="text-sm text-slate-500 m-0">{message}</p>}
  </div>
);

export default LoadingSpinner;
