import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { History } from 'lucide-react';
import { Button, PageHeader, LoadingSpinner, Alert, FormField, Input } from '../components/ui';
import { useAuth } from '../context/AuthContext';
import { canEditConfig } from '../utils/permissions';
import { fetchTargetTableColumns } from '../services/catalogAdminService';
import {
    listHistoryDefinitions,
    getHistoryDefinition,
    updateHistoryDefinition,
    buildHistorySavePayload,
    DEFAULT_PROCESS_TYPES,
    DEFAULT_SALES_CHANNEL,
} from '../services/historyAdminService';
import {
    buildHistoryColumnRequiredMap,
    buildHistoryColumnDefaultsState,
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

const SALES_HISTORY_FOOTER_NOTE = (
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

const INVENTORY_SNAPSHOT_FOOTER_NOTE = (
    <>
        <code className="font-mono">snapshot_date</code>, <code className="font-mono">sku</code>,{' '}
        <code className="font-mono">location_code</code> y <code className="font-mono">on_hand_qty</code> son el
        mínimo a mapear desde el archivo.
        {' '}
        <code className="font-mono">organization_id</code>, <code className="font-mono">snapshot_id</code> y{' '}
        <code className="font-mono">created_at</code> los genera la base de datos. Sin agregación semanal/mensual.
    </>
);

const HISTORY_MAPPABLE_LEGEND = 'Mapeable desde el archivo (paso 2)';

const requiredLockedForTable = (tableName) => {
    if (tableName === 'inventory_snapshot') {
        return ['snapshot_date', 'location_code'];
    }
    return HISTORY_ALWAYS_REQUIRED_MAPPING;
};

const footerNoteForTable = (tableName) => {
    if (tableName === 'inventory_snapshot') {
        return INVENTORY_SNAPSHOT_FOOTER_NOTE;
    }
    return SALES_HISTORY_FOOTER_NOTE;
};

const HistoryAdmin = () => {
    const { user } = useAuth();
    const readOnly = !canEditConfig(user);
    const organizationName = user?.organization_name || '';

    const [tables, setTables] = useState([]);
    const [selectedName, setSelectedName] = useState(null);
    const [loading, setLoading] = useState(true);
    const [detailLoading, setDetailLoading] = useState(false);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState('');
    const [tab, setTab] = useState('general');
    const [definition, setDefinition] = useState(null);
    const [processTypes, setProcessTypes] = useState(DEFAULT_PROCESS_TYPES);
    const [schemaColumns, setSchemaColumns] = useState([]);
    const [columnRequired, setColumnRequired] = useState({});
    const [columnDefaultEnabled, setColumnDefaultEnabled] = useState({});
    const [columnDefaultValues, setColumnDefaultValues] = useState({});
    const [granularityEditorOpen, setGranularityEditorOpen] = useState(false);
    const [salesChannelEditorOpen, setSalesChannelEditorOpen] = useState(false);
    const [salesChannelDefault, setSalesChannelDefault] = useState(DEFAULT_SALES_CHANNEL);

    const loadList = useCallback(async () => {
        try {
            setLoading(true);
            setError('');
            const list = await listHistoryDefinitions();
            setTables(list);
            return list;
        } catch (err) {
            setError(err.response?.data?.detail || 'No se pudo cargar la lista de tablas de historia');
            return [];
        } finally {
            setLoading(false);
        }
    }, []);

    const selectTable = useCallback(async (tableName) => {
        if (!tableName) return;
        try {
            setDetailLoading(true);
            setError('');
            setSelectedName(tableName);
            const data = await getHistoryDefinition(tableName);
            setDefinition(data);
            setProcessTypes(
                data.process_types?.length ? data.process_types : DEFAULT_PROCESS_TYPES
            );
            setSalesChannelDefault(data.sales_channel_default || DEFAULT_SALES_CHANNEL);

            const schema = data.target_schema || 'public';
            const physicalTable = data.target_table || tableName;
            const cols = await fetchTargetTableColumns(schema, physicalTable);
            setSchemaColumns(cols);
            setColumnRequired(
                buildHistoryColumnRequiredMap(
                    cols,
                    data.required_mapping_columns || [],
                    data.optional_columns || []
                )
            );
            const defaultsState = buildHistoryColumnDefaultsState(cols, data.defaults || {});
            setColumnDefaultEnabled(defaultsState.enabled);
            setColumnDefaultValues(defaultsState.values);
        } catch (err) {
            setError(err.response?.data?.detail || 'No se pudo cargar la configuración de historia');
        } finally {
            setDetailLoading(false);
        }
    }, []);

    useEffect(() => {
        let cancelled = false;
        (async () => {
            const list = await loadList();
            if (cancelled || list.length === 0) return;
            const initial =
                list.find((t) => t.name === 'sales_history')?.name || list[0].name;
            await selectTable(initial);
        })();
        return () => {
            cancelled = true;
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    const features = definition?.features || {};
    const targetSchema = definition?.target_schema || 'public';
    const targetTable = definition?.target_table || selectedName || '';
    const label = definition?.label || selectedName || '';

    const columnEditors = useMemo(() => {
        const editors = {};
        if (features.auto_granularity !== false) {
            editors.granularity = {
                expanded: granularityEditorOpen,
                onToggle: () => setGranularityEditorOpen((open) => !open),
                panel: (
                    <ProcessTypesEditor
                        embedded
                        value={processTypes}
                        onChange={setProcessTypes}
                    />
                ),
            };
        }
        if (features.auto_sales_channel !== false) {
            editors.sales_channel = {
                expanded: salesChannelEditorOpen,
                onToggle: () => setSalesChannelEditorOpen((open) => !open),
                panel: (
                    <SalesChannelDefaultEditor
                        value={salesChannelDefault}
                        onChange={setSalesChannelDefault}
                    />
                ),
            };
        }
        return editors;
    }, [
        features.auto_granularity,
        features.auto_sales_channel,
        granularityEditorOpen,
        salesChannelEditorOpen,
        processTypes,
        salesChannelDefault,
    ]);

    const handleRequiredChange = (colName, required) => {
        if (requiredLockedForTable(selectedName).includes(colName)) return;
        setColumnRequired((prev) => ({ ...prev, [colName]: required }));
    };

    const handleDefaultEnabledChange = (colName, enabled) => {
        setColumnDefaultEnabled((prev) => ({ ...prev, [colName]: enabled }));
    };

    const handleDefaultValueChange = (colName, value) => {
        setColumnDefaultValues((prev) => ({ ...prev, [colName]: value }));
    };

    const handleSave = async () => {
        if (!selectedName) return;
        try {
            setSaving(true);
            setError('');
            const mappingFields = deriveHistoryMappingFields(
                schemaColumns,
                columnRequired,
                columnDefaultEnabled,
                columnDefaultValues
            );
            const payload = buildHistorySavePayload(definition, {
                processTypes,
                salesChannelDefault,
                mappingFields,
                columnDefaultEnabledMap: columnDefaultEnabled,
                columnDefaultValuesMap: columnDefaultValues,
                schemaColumns,
            });
            const updated = await updateHistoryDefinition(selectedName, payload);
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
            const defaultsState = buildHistoryColumnDefaultsState(
                schemaColumns,
                updated.defaults || {}
            );
            setColumnDefaultEnabled(defaultsState.enabled);
            setColumnDefaultValues(defaultsState.values);
            await loadList();
        } catch (err) {
            setError(err.response?.data?.detail || err.message || 'Error al guardar');
        } finally {
            setSaving(false);
        }
    };

    if (loading && tables.length === 0) {
        return (
            <div className="page-container">
                <LoadingSpinner />
            </div>
        );
    }

    return (
        <div className="flex flex-1 flex-col gap-5 overflow-y-auto p-8 max-w-6xl mx-auto w-full scrollbar-thin">
            <PageHeader
                icon={History}
                title="Configuración de historia"
                subtitle={
                    <>
                        Reglas de columnas y granularidad por tabla destino. Las tablas activas aparecen en{' '}
                        <Link to="/upload/history">Carga de historia</Link>.
                    </>
                }
            />

            {error && <Alert variant="error">{error}</Alert>}

            <div className="grid grid-cols-1 lg:grid-cols-[280px_1fr] gap-4 items-start">
                <aside className="rounded-md border border-[#e2e8f0] bg-white shadow-sm dark:border-[#334155] dark:bg-slate-800 p-4">
                    <h2 className="text-sm font-semibold text-slate-800 dark:text-slate-100 mb-3">
                        Destinos ({tables.length})
                    </h2>
                    {tables.map((table) => (
                        <button
                            key={table.name}
                            type="button"
                            className={`block w-full text-left p-2.5 mb-1 rounded-lg border transition-colors ${
                                selectedName === table.name
                                    ? 'border-brand-500 bg-blue-50 dark:bg-blue-950/30'
                                    : 'border-[#e2e8f0] dark:border-[#334155] hover:border-brand-500'
                            } ${table.is_active === false ? 'opacity-55' : ''}`}
                            onClick={() => selectTable(table.name)}
                        >
                            <strong>{table.label || table.name}</strong>
                            <small>
                                {table.target_schema || 'public'}.{table.target_table || table.name}
                                {table.is_active === false ? ' · inactivo' : ''}
                            </small>
                        </button>
                    ))}
                </aside>

                <section className="rounded-md border border-[#e2e8f0] bg-white shadow-sm dark:border-[#334155] dark:bg-slate-800 p-5">
                    {!selectedName ? (
                        <div className="text-center py-8 text-slate-500">
                            <p>Selecciona una tabla de historia.</p>
                        </div>
                    ) : detailLoading ? (
                        <LoadingSpinner />
                    ) : (
                        <>
                            <ConfigTabs tabs={HISTORY_TABS} activeTab={tab} onTabChange={setTab} />

                            {tab === 'general' && (
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                    <FormField label="Etiqueta" className="md:col-span-2">
                                        <Input value={label} readOnly disabled />
                                    </FormField>
                                    <FormField label="Schema destino">
                                        <Input value={targetSchema} readOnly disabled />
                                    </FormField>
                                    <FormField label="Tabla destino">
                                        <Input value={targetTable} readOnly disabled />
                                    </FormField>
                                    <FormField label="Agregación" className="md:col-span-2">
                                        <Input
                                            value={
                                                definition?.supports_aggregation === false
                                                    ? 'No (snapshot fila a fila)'
                                                    : 'Sí (semanal / mensual)'
                                            }
                                            readOnly
                                            disabled
                                        />
                                    </FormField>
                                </div>
                            )}

                            {tab === 'columns' && (
                                <div className="grid grid-cols-1 gap-4">
                                    <CatalogColumnsEditor
                                        schemaColumns={schemaColumns}
                                        columnRequired={columnRequired}
                                        onRequiredChange={handleRequiredChange}
                                        columnDefaultEnabled={columnDefaultEnabled}
                                        columnDefaultValues={columnDefaultValues}
                                        onDefaultEnabledChange={handleDefaultEnabledChange}
                                        onDefaultValueChange={handleDefaultValueChange}
                                        organizationName={organizationName}
                                        classifyColumn={classifyHistoryColumn}
                                        mappableLegend={HISTORY_MAPPABLE_LEGEND}
                                        requiredLockedColumns={requiredLockedForTable(selectedName)}
                                        footerNote={footerNoteForTable(selectedName)}
                                        columnEditors={columnEditors}
                                    />
                                    <ChipListEditor
                                        label="Notas de validación (UI del wizard)"
                                        value={definition?.validation_hints || []}
                                        readOnly
                                    />
                                    <div className="flex flex-wrap gap-3">
                                        {!readOnly ? (
                                            <Button variant="primary" onClick={handleSave} disabled={saving}>
                                                {saving ? 'Guardando…' : 'Guardar cambios'}
                                            </Button>
                                        ) : (
                                            <p className="text-sm text-slate-500">Modo solo lectura</p>
                                        )}
                                    </div>
                                </div>
                            )}
                        </>
                    )}
                </section>
            </div>
        </div>
    );
};

export default HistoryAdmin;
