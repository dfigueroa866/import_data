import React from 'react';
import { Plus, Trash2 } from 'lucide-react';
import { Button, FormField, Input } from '../ui';

const ProcessTypesEditor = ({ value, onChange, embedded = false }) => {
    const rows = Array.isArray(value) ? value : [];

    const updateRow = (index, field, fieldValue) => {
        const next = rows.map((row, i) => (i === index ? { ...row, [field]: fieldValue } : row));
        onChange(next);
    };

    const addRow = () => {
        onChange([
            ...rows,
            {
                key: '',
                label: '',
                granularity: '',
                date_truncate: '1w',
            },
        ]);
    };

    const removeRow = (index) => {
        if (rows.length <= 1) return;
        onChange(rows.filter((_, i) => i !== index));
    };

    const tableBlock = (
        <>
            <div className="overflow-x-auto rounded-lg border border-[#e2e8f0] dark:border-[#334155] bg-white dark:bg-slate-800">
                <table className="w-full text-sm">
                    <thead className="bg-slate-50 dark:bg-slate-900/50 text-left">
                        <tr>
                            <th className="px-3 py-2 font-medium">Identificador</th>
                            <th className="px-3 py-2 font-medium">Etiqueta (paso 1)</th>
                            <th className="px-3 py-2 font-medium">Valor granularity</th>
                            <th className="px-3 py-2 font-medium">Truncado fecha</th>
                            <th className="px-3 py-2 w-10" aria-label="Acciones" />
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-[#e2e8f0] dark:divide-[#334155]">
                        {rows.map((row, index) => (
                            <tr key={`process-type-${index}`}>
                                <td className="px-3 py-2">
                                    <Input
                                        value={row.key || ''}
                                        onChange={(e) => updateRow(index, 'key', e.target.value)}
                                        placeholder="Weekly"
                                        className="min-w-[7rem]"
                                    />
                                </td>
                                <td className="px-3 py-2">
                                    <Input
                                        value={row.label || ''}
                                        onChange={(e) => updateRow(index, 'label', e.target.value)}
                                        placeholder="Weekly (agrupa por semana)"
                                    />
                                </td>
                                <td className="px-3 py-2">
                                    <Input
                                        value={row.granularity || ''}
                                        onChange={(e) => updateRow(index, 'granularity', e.target.value)}
                                        placeholder="week"
                                        className="min-w-[5rem]"
                                    />
                                </td>
                                <td className="px-3 py-2">
                                    <Input
                                        value={row.date_truncate || ''}
                                        onChange={(e) => updateRow(index, 'date_truncate', e.target.value)}
                                        placeholder="1w"
                                        className="min-w-[4rem]"
                                    />
                                </td>
                                <td className="px-3 py-2 text-center">
                                    <button
                                        type="button"
                                        onClick={() => removeRow(index)}
                                        disabled={rows.length <= 1}
                                        className="p-1.5 rounded text-slate-400 hover:text-red-600 disabled:opacity-30 disabled:cursor-not-allowed"
                                        title="Eliminar"
                                    >
                                        <Trash2 size={16} />
                                    </button>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
            <div className="mt-3">
                <Button type="button" variant="secondary" size="sm" onClick={addRow}>
                    <Plus size={16} className="mr-1" />
                    Añadir tipo
                </Button>
            </div>
        </>
    );

    if (embedded) {
        return (
            <div className="space-y-2">
                <p className="text-sm font-medium text-slate-700 dark:text-slate-200">
                    Tipos de proceso (granularidad)
                </p>
                <p className="text-xs text-slate-500 dark:text-slate-400">
                    Opciones del dropdown en el paso 1. Truncado fecha: formato Polars (1w, 1mo, 1d…).
                </p>
                {tableBlock}
            </div>
        );
    }

    return (
        <FormField
            label="Granularidad — tipos de proceso"
            hint="Estos valores aparecen en el paso 1 del wizard de carga. date_truncate usa formato Polars (1w, 1mo, 1d…)."
            className="col-span-full"
        >
            {tableBlock}
        </FormField>
    );
};

export default ProcessTypesEditor;
