import React from 'react';
import { Input } from '../ui';

const SalesChannelDefaultEditor = ({ value, onChange }) => (
    <div className="space-y-2 max-w-md">
        <p className="text-sm font-medium text-slate-700 dark:text-slate-200">
            Valor por defecto de sales_channel
        </p>
        <p className="text-xs text-slate-500 dark:text-slate-400">
            Se inyecta automáticamente en el wizard (paso 2) y en la agregación. No se mapea desde el archivo.
        </p>
        <Input
            value={value || ''}
            onChange={(e) => onChange(e.target.value)}
            placeholder="SELL_IN"
        />
    </div>
);

export default SalesChannelDefaultEditor;
