import React from 'react';
import { cn } from '../../lib/utils';

const WizardStepper = ({ steps, currentStep, completedSteps = [], errorStep, className }) => (
  <nav
    className={cn(
      'flex items-start justify-center flex-nowrap w-full max-w-3xl mx-auto py-4',
      className
    )}
    aria-label="Pasos del asistente"
  >
    {steps.map((label, idx) => {
      const stepNum = idx + 1;
      const isComplete = completedSteps.includes(stepNum) || currentStep > stepNum;
      const isError = errorStep === stepNum;
      const isActive = currentStep === stepNum && !isComplete && !isError;
      const connectorComplete = completedSteps.includes(idx) || currentStep > idx;

      return (
        <React.Fragment key={label}>
          {idx > 0 && (
            <div
              className={cn(
                'h-0.5 flex-1 min-w-6 max-w-28 self-start mt-[1.125rem]',
                connectorComplete
                  ? 'bg-brand-700'
                  : 'bg-slate-200 dark:bg-slate-600'
              )}
              aria-hidden
            />
          )}
          <div className="flex flex-col items-center gap-2 shrink-0 w-[5.5rem]">
            <span
              className={cn(
                'flex h-9 w-9 items-center justify-center rounded-full text-sm font-semibold transition-colors',
                isError && 'bg-red-600 text-white ring-4 ring-red-100 dark:ring-red-950/40',
                isComplete && !isError && 'bg-brand-700 text-white ring-4 ring-blue-100 dark:ring-blue-950/40',
                isActive && 'bg-brand-700 text-white ring-4 ring-blue-100 dark:ring-blue-950/40',
                !isActive && !isComplete && !isError && 'bg-slate-200 text-slate-500 dark:bg-slate-600 dark:text-slate-400'
              )}
            >
              {isComplete ? '✓' : isError ? '✕' : stepNum}
            </span>
            <span
              className={cn(
                'text-[10px] font-bold uppercase tracking-wider text-center max-w-[6.5rem] leading-tight',
                (isActive || isComplete) && !isError && 'text-brand-700 dark:text-blue-400',
                isError && 'text-red-600',
                !isActive && !isComplete && !isError && 'text-slate-500'
              )}
            >
              {label}
            </span>
          </div>
        </React.Fragment>
      );
    })}
  </nav>
);

export default WizardStepper;
