import React, { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { History } from 'lucide-react';
import { Button, PageHeader, LoadingSpinner, Alert, FormField, Input } from '../components/ui';
import { useAuth } from '../context/AuthContext';
import { fetchTargetTableColumns } from '../services/catalogAdminService';
import {
    getHistoryDefinition,
    updateHistoryDefinition,
    buildHistorySavePayload,
    DEFAULT_PROCESS_TYPES,
    DEFAULT_SALES_CHANNEL,
} from '../services/historyAdminService';
import {
    HISTORY_TARGET_SCHEMA,
    HISTORY_TARGET_TABLE,
} from '../constants/historyConfig';
import {
    buildHistoryColumnRequiredMap,
    classifyHistoryColumn,
    deriveHistoryMappingFields,
    HISTORY_ALWAYS_REQUIRED_MAPPING,
} from '../utils/catalogColumnRules';
import {
    HISTORY_TABS,
    CatalogColumnsEditor,
    ChipListEditor,
    ConfigTabs,
} from '../components/admin/CatalogConfigEditors';
import ProcessTypesEditor from '../components/admin/ProcessTypesEditor';
import SalesChannelDefaultEditor from '../components/admin/SalesChannelDefaultEditor';

const HISTORY_FOOTER_NOTE = (
    <>
        <code className="font-mono">location_code</code>, <code className="font-mono">sku</code>,{' '}
        <code className="font-mono">period_start</code>, <code className="font-mono">quantity</code> y{' '}
        <code className="font-mono">pieces</code> se mapean desde el archivo en el paso 2.
        {' '}
        <code className="font-mono">organization_id</code>, <code className="font-mono">granularity</code>,{' '}
        <code className="font-mono">source</code> y <code className="font-mono">sales_channel</code> se asignan
        automáticamente. <code className="font-mono">location_code</code> es siempre obligatorio en el mapping.
    </>
);

const HISTORY_MAPPABLE_LEGEND = 'Mapeable desde el archivo (paso 2)';

const HistoryAdmin = () => {
    const { user } = useAuth();
    const organizationName = user?.organization_name || '';

    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState('');
    const [tab, setTab] = useState('general');
    const [definition, setDefinition] = useState(null);
    const [processTypes, setProcessTypes] = useState(DEFAULT_PROCESS_TYPES);
    const [schemaColumns, setSchemaColumns] = useState([]);
    const [columnRequired, setColumnRequired] = useState({});
    const [granularityEditorOpen, setGranularityEditorOpen] = useState(false);
    const [salesChannelEditorOpen, setSalesChannelEditorOpen] = useState(false);
    const [salesChannelDefault, setSalesChannelDefault] = useState(DEFAULT_SALES_CHANNEL);

    const loadDefinition = useCallback(async () => {
        try {
            setLoading(true);
            setError('');
            const data = await getHistoryDefinition();
            setDefinition(data);
            setProcessTypes(
                data.process_types?.length ? data.process_types : DEFAULT_PROCESS_TYPES
            );
            setSalesChannelDefault(data.sales_channel_default || DEFAULT_SALES_CHANNEL);

            const cols = await fetchTargetTableColumns(HISTORY_TARGET_SCHEMA, HISTORY_TARGET_TABLE);
            setSchemaColumns(cols);
            setColumnRequired(
                buildHistoryColumnRequiredMap(
                    cols,
                    data.required_mapping_columns || [],
                    data.optional_columns || []
                )
            );
        } catch (err) {
            setError(err.response?.data?.detail || 'No se pudo cargar la configuración de historia');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        loadDefinition();
    }, [loadDefinition]);

    const handleRequiredChange = (colName, required) => {
        if (HISTORY_ALWAYS_REQUIRED_MAPPING.includes(colName)) return;
        setColumnRequired((prev) => ({ ...prev, [colName]: required }));
    };

    const handleSave = async () => {
        try {
            setSaving(true);
            setError('');
            const mappingFields = deriveHistoryMappingFields(schemaColumns, columnRequired);
            const payload = buildHistorySavePayload(definition, {
                processTypes,
                salesChannelDefault,
                mappingFields,
            });
            const updated = await updateHistoryDefinition(payload);
            setDefinition(updated);
            setProcessTypes(updated.process_types || DEFAULT_PROCESS_TYPES);
            setSalesChannelDefault(updated.sales_channel_default || DEFAULT_SALES_CHANNEL);
            setColumnRequired(
                buildHistoryColumnRequiredMap(
                    schemaColumns,
                    updated.required_mapping_columns || [],
                    updated.optional_columns || []
                )
            );
        } catch (err) {
            setError(err.response?.data?.detail || err.message || 'Error al guardar');
        } finally {
            setSaving(false);
        }
    };

    if (loading) {
        return (
            <div className="page-container">
                <LoadingSpinner />
            </div>
        );
    }

    const label = definition?.label || 'Historial de ventas';

    return (
        <div className="flex flex-1 flex-col gap-5 overflow-y-auto p-8 max-w-6xl mx-auto w-full scrollbar-thin">
            <PageHeader
                icon={History}
                title="Configuración de historia"
                subtitle={
                    <>
                        Reglas de columnas y granularidad para cargas históricas. Destino fijo:{' '}
                        <code className="font-mono text-sm">
                            {HISTORY_TARGET_SCHEMA}.{HISTORY_TARGET_TABLE}
                        </code>
                        . Usado en <Link to="/upload/history">Carga de historia</Link>.
                    </>
                }
            />

            {error && <Alert variant="error">{error}</Alert>}

            <div className="grid grid-cols-1 lg:grid-cols-[280px_1fr] gap-4 items-start">
                <aside className="rounded-md border border-[#e2e8f0] bg-white shadow-sm dark:border-[#334155] dark:bg-slate-800 p-4">
                    <h2 className="text-sm font-semibold text-slate-800 dark:text-slate-100 mb-3">Destinos</h2>
                    <button
                        type="button"
                        className="block w-full text-left p-2.5 rounded-lg border border-brand-500 bg-blue-50 dark:bg-blue-950/30"
                    >
                        <strong>{label}</strong>
                        <small>
                            {HISTORY_TARGET_SCHEMA}.{HISTORY_TARGET_TABLE}
                        </small>
                    </button>
                </aside>

                <section className="rounded-md border border-[#e2e8f0] bg-white shadow-sm dark:border-[#334155] dark:bg-slate-800 p-5">
                    <ConfigTabs tabs={HISTORY_TABS} activeTab={tab} onTabChange={setTab} />

                    {tab === 'general' && (
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <FormField label="Etiqueta" className="md:col-span-2">
                                <Input value={label} readOnly disabled />
                            </FormField>
                            <FormField label="Schema destino">
                                <Input value={HISTORY_TARGET_SCHEMA} readOnly disabled />
                            </FormField>
                            <FormField label="Tabla destino">
                                <Input value={HISTORY_TARGET_TABLE} readOnly disabled />
                            </FormField>
                        </div>
                    )}

                    {tab === 'columns' && (
                        <div className="grid grid-cols-1 gap-4">
                            <CatalogColumnsEditor
                                schemaColumns={schemaColumns}
                                columnRequired={columnRequired}
                                onRequiredChange={handleRequiredChange}
                                organizationName={organizationName}
                                classifyColumn={classifyHistoryColumn}
                                mappableLegend={HISTORY_MAPPABLE_LEGEND}
                                requiredLockedColumns={HISTORY_ALWAYS_REQUIRED_MAPPING}
                                footerNote={HISTORY_FOOTER_NOTE}
                                columnEditors={{
                                    granularity: {
                                        expanded: granularityEditorOpen,
                                        onToggle: () => setGranularityEditorOpen((open) => !open),
                                        panel: (
                                            <ProcessTypesEditor
                                                embedded
                                                value={processTypes}
                                                onChange={setProcessTypes}
                                            />
                                        ),
                                    },
                                    sales_channel: {
                                        expanded: salesChannelEditorOpen,
                                        onToggle: () => setSalesChannelEditorOpen((open) => !open),
                                        panel: (
                                            <SalesChannelDefaultEditor
                                                value={salesChannelDefault}
                                                onChange={setSalesChannelDefault}
                                            />
                                        ),
                                    },
                                }}
                            />
                            <ChipListEditor
                                label="Notas de validación (UI del wizard)"
                                value={definition?.validation_hints || []}
                                readOnly
                            />
                            <div className="flex flex-wrap gap-3">
                                <Button variant="primary" onClick={handleSave} disabled={saving}>
                                    {saving ? 'Guardando…' : 'Guardar cambios'}
                                </Button>
                            </div>
                        </div>
                    )}
                </section>
            </div>
        </div>
    );
};

export default HistoryAdmin;
