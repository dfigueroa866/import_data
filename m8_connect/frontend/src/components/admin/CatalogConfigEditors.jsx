import React, { useState } from 'react';
import { FormField, Input, Button, Chip } from '../ui';
import { classifyCatalogColumn } from '../../utils/catalogColumnRules';

export const CATALOG_TABS = [
    { id: 'general', label: 'General' },
    { id: 'columns', label: 'Columnas' },
    { id: 'advanced', label: 'Avanzado' },
];

export const HISTORY_TABS = [
    { id: 'general', label: 'General' },
    { id: 'columns', label: 'Columnas' },
];

const AUTO_DB_LEGEND = 'Se genera automáticamente en la BD';
const AUTO_SESSION_LEGEND = 'Se asigna desde la sesión (organización)';
const AUTO_AUDIT_LEGEND = 'Lo gestiona el sistema';
const AUTO_WIZARD_LEGEND = 'Se asigna automáticamente en el wizard';

export const ChipListEditor = ({ label, value, onChange, hint, readOnly = false }) => {
    const [draft, setDraft] = useState('');

    const addChip = () => {
        const v = draft.trim();
        if (!v || value.includes(v)) return;
        onChange([...value, v]);
        setDraft('');
    };

    if (readOnly) {
        return (
            <FormField label={label} hint={hint} className="col-span-full">
                <div className="flex flex-wrap gap-1">
                    {(value || []).length === 0 ? (
                        <span className="text-sm text-slate-500 dark:text-slate-400">—</span>
                    ) : (
                        value.map((chip) => <Chip key={chip}>{chip}</Chip>)
                    )}
                </div>
            </FormField>
        );
    }

    return (
        <FormField label={label} hint={hint} className="col-span-full">
            <div className="flex gap-2">
                <Input
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), addChip())}
                    placeholder="Escribe y Enter"
                />
                <Button type="button" variant="secondary" size="sm" onClick={addChip}>Añadir</Button>
            </div>
            <div className="flex flex-wrap gap-1 mt-2">
                {value.map((chip) => (
                    <Chip key={chip} onRemove={() => onChange(value.filter((c) => c !== chip))}>{chip}</Chip>
                ))}
            </div>
        </FormField>
    );
};

const ColumnLegend = ({ children }) => (
    <span className="inline-block text-sm text-slate-500 dark:text-slate-400 italic">{children}</span>
);

export const RequiredColumnToggle = ({ checked, onChange, disabled = false }) => (
    <label className={`inline-flex items-center gap-3 select-none ${disabled ? 'cursor-not-allowed opacity-60' : 'cursor-pointer not-italic'}`}>
        <span className="text-sm text-slate-600 dark:text-slate-300">Obligatorio</span>
        <span className="relative inline-block h-6 w-11 shrink-0">
            <input
                type="checkbox"
                className="peer sr-only"
                checked={Boolean(checked)}
                onChange={(e) => onChange(e.target.checked)}
                disabled={disabled}
            />
            <span
                aria-hidden="true"
                className="absolute inset-0 rounded-full bg-slate-200 transition-colors peer-checked:bg-emerald-500 dark:bg-slate-600 dark:peer-checked:bg-emerald-600 peer-disabled:opacity-50"
            />
            <span
                aria-hidden="true"
                className="absolute left-0.5 top-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform peer-checked:translate-x-5"
            />
        </span>
        <span className="text-xs font-medium text-slate-500 dark:text-slate-400 w-5">
            {checked ? 'Sí' : 'No'}
        </span>
    </label>
);

export const ConfigTabs = ({ tabs, activeTab, onTabChange }) => (
    <div className="flex flex-wrap gap-2 mb-4">
        {tabs.map((t) => (
            <button
                key={t.id}
                type="button"
                className={`px-3 py-1.5 rounded-lg border text-sm transition-colors ${activeTab === t.id ? 'border-brand-600 bg-blue-50 text-brand-700 dark:bg-blue-950/30' : 'border-[#e2e8f0] dark:border-[#334155] text-slate-600'}`}
                onClick={() => onTabChange(t.id)}
            >
                {t.label}
            </button>
        ))}
    </div>
);

export const CatalogColumnsEditor = ({
    schemaColumns,
    columnRequired,
    onRequiredChange,
    organizationName,
    classifyColumn = classifyCatalogColumn,
    readOnly = false,
    footerNote,
    columnEditors = {},
    mappableLegend = '',
    requiredLockedColumns = [],
}) => {
    if (schemaColumns.length === 0) {
        return (
            <p className="text-sm text-slate-500 dark:text-slate-400">
                Selecciona schema y tabla destino en General para listar las columnas de la tabla.
            </p>
        );
    }

    const renderStatus = (col) => {
        const kind = classifyColumn(col);
        if (kind === 'organization') {
            return (
                <ColumnLegend>
                    {AUTO_SESSION_LEGEND}
                    {organizationName ? ` · ${organizationName}` : ''}
                </ColumnLegend>
            );
        }
        if (kind === 'primary_key') {
            return <ColumnLegend>{AUTO_DB_LEGEND}</ColumnLegend>;
        }
        if (kind === 'audit') {
            return <ColumnLegend>{AUTO_AUDIT_LEGEND}</ColumnLegend>;
        }
        if (kind === 'auto') {
            const editor = columnEditors[col.name];
            if (editor) {
                return (
                    <div className="flex items-center justify-between gap-3 flex-wrap w-full">
                        <ColumnLegend>{AUTO_WIZARD_LEGEND}</ColumnLegend>
                        <Button
                            type="button"
                            variant="secondary"
                            size="sm"
                            onClick={editor.onToggle}
                        >
                            {editor.expanded ? 'Ocultar' : 'Editar'}
                        </Button>
                    </div>
                );
            }
            return <ColumnLegend>{AUTO_WIZARD_LEGEND}</ColumnLegend>;
        }
        return (
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between w-full">
                <div className="flex flex-col gap-1">
                    {mappableLegend ? (
                        <ColumnLegend>{mappableLegend}</ColumnLegend>
                    ) : null}
                    <RequiredColumnToggle
                        checked={Boolean(columnRequired[col.name])}
                        onChange={(value) => onRequiredChange(col.name, value)}
                        disabled={readOnly || requiredLockedColumns.includes(col.name)}
                    />
                </div>
            </div>
        );
    };

    const defaultFooter = (
        <>
            Las columnas PK, <code className="font-mono">organization_id</code> y auditoría no se configuran:
            se asignan automáticamente. Las columnas NOT NULL en la BD se marcan obligatorias
            por defecto; puedes cambiarlo con el toggle.
        </>
    );

    return (
        <div className="col-span-full overflow-x-auto rounded-lg border border-[#e2e8f0] dark:border-[#334155]">
            <table className="w-full text-sm">
                <thead className="bg-slate-50 dark:bg-slate-900/50 text-left">
                    <tr>
                        <th className="px-4 py-2.5 font-medium text-slate-700 dark:text-slate-200">Columna</th>
                        <th className="px-4 py-2.5 font-medium text-slate-700 dark:text-slate-200">Tipo</th>
                        <th className="px-4 py-2.5 font-medium text-slate-700 dark:text-slate-200">Mapping (paso 2)</th>
                    </tr>
                </thead>
                <tbody className="divide-y divide-[#e2e8f0] dark:divide-[#334155]">
                    {schemaColumns.map((col) => {
                        const kind = classifyColumn(col);
                        const isPk = kind === 'primary_key';
                        const isAuto = kind !== 'mappable';
                        const editor = columnEditors[col.name];
                        return (
                            <React.Fragment key={col.name}>
                                <tr
                                    className={
                                        isAuto
                                            ? 'bg-slate-50/80 dark:bg-slate-900/30'
                                            : 'bg-white dark:bg-slate-800'
                                    }
                                >
                                    <td className="px-4 py-3 font-mono text-slate-800 dark:text-slate-100">
                                        {col.name}
                                        {isPk && (
                                            <span className="ml-2 text-xs font-sans text-amber-600 dark:text-amber-400">
                                                PK
                                            </span>
                                        )}
                                    </td>
                                    <td className="px-4 py-3 text-slate-500 dark:text-slate-400">
                                        {col.type}
                                        {!col.nullable ? ' · NOT NULL' : ''}
                                    </td>
                                    <td className="px-4 py-3">{renderStatus(col)}</td>
                                </tr>
                                {editor?.expanded && (
                                    <tr className="bg-slate-50/80 dark:bg-slate-900/30">
                                        <td
                                            colSpan={3}
                                            className="px-4 py-4 border-t border-[#e2e8f0] dark:border-[#334155]"
                                        >
                                            {editor.panel}
                                        </td>
                                    </tr>
                                )}
                            </React.Fragment>
                        );
                    })}
                </tbody>
            </table>
            <p className="px-4 py-2 text-xs text-slate-500 dark:text-slate-400 border-t border-[#e2e8f0] dark:border-[#334155]">
                {footerNote || defaultFooter}
            </p>
        </div>
    );
};
