import React, { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { Settings2 } from 'lucide-react';
import { Button, PageHeader, LoadingSpinner, Alert, FormField, Input, Select, Textarea, ConfirmDialog } from '../components/ui';
import { useAuth } from '../context/AuthContext';
import { canEditConfig } from '../utils/permissions';
import {
    listCatalogDefinitions,
    getCatalogDefinition,
    createCatalogDefinition,
    updateCatalogDefinition,
    deleteCatalogDefinition,
    fetchTargetTableColumns,
    emptyCatalogForm,
    catalogToForm,
    buildColumnRequiredMap,
    buildCatalogPayload,
} from '../services/catalogAdminService';
import { getSchemas, getTables } from '../services/systemService';
import {
    CATALOG_TABS,
    CatalogColumnsEditor,
    ChipListEditor,
    ConfigTabs,
} from '../components/admin/CatalogConfigEditors';

const CatalogAdmin = () => {
    const { user } = useAuth();
    const readOnly = !canEditConfig(user);
    const organizationName = user?.organization_name || '';

    const [catalogs, setCatalogs] = useState([]);
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState('');
    const [selectedName, setSelectedName] = useState(null);
    const [isNew, setIsNew] = useState(false);
    const [tab, setTab] = useState('general');
    const [form, setForm] = useState(emptyCatalogForm());
    const [schemaColumns, setSchemaColumns] = useState([]);
    const [columnRequired, setColumnRequired] = useState({});
    const [aliasesJson, setAliasesJson] = useState('{}');
    const [enumsJson, setEnumsJson] = useState('{}');
    const [dbSchemas, setDbSchemas] = useState([]);
    const [dbTables, setDbTables] = useState([]);
    const [loadingDbMeta, setLoadingDbMeta] = useState(false);
    const [confirmDeactivateOpen, setConfirmDeactivateOpen] = useState(false);

    const syncColumnRequiredFromForm = useCallback((cols, mappingRequired, optionalCols, requiredCols) => {
        setColumnRequired(
            buildColumnRequiredMap(
                cols,
                mappingRequired || [],
                optionalCols || [],
                requiredCols || []
            )
        );
    }, []);

    const loadList = useCallback(async () => {
        try {
            setLoading(true);
            setError('');
            const list = await listCatalogDefinitions();
            setCatalogs(list);
        } catch (err) {
            setError(err.response?.data?.detail || 'No se pudieron cargar los catálogos');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        loadList();
    }, [loadList]);

    useEffect(() => {
        loadDbSchemas();
    }, []);

    const loadDbSchemas = async () => {
        try {
            const data = await getSchemas();
            setDbSchemas(data.schemas || []);
        } catch {
            setDbSchemas([]);
        }
    };

    const loadDbTablesForSchema = async (schema) => {
        if (!schema) {
            setDbTables([]);
            return;
        }
        try {
            setLoadingDbMeta(true);
            const data = await getTables(schema);
            setDbTables(data.tables || []);
        } catch {
            setDbTables([]);
        } finally {
            setLoadingDbMeta(false);
        }
    };

    useEffect(() => {
        if (form.target_schema) {
            loadDbTablesForSchema(form.target_schema);
        } else {
            setDbTables([]);
        }
    }, [form.target_schema]);

    const fetchSchemaColumns = useCallback(async (schema, table, mappingRequired, optionalCols, requiredCols) => {
        if (!schema || !table) {
            setSchemaColumns([]);
            setColumnRequired({});
            return [];
        }
        try {
            const cols = await fetchTargetTableColumns(schema, table);
            setSchemaColumns(cols);
            syncColumnRequiredFromForm(
                cols,
                mappingRequired || [],
                optionalCols || [],
                requiredCols || []
            );
            return cols;
        } catch {
            setSchemaColumns([]);
            setColumnRequired({});
            return [];
        }
    }, [syncColumnRequiredFromForm]);

    useEffect(() => {
        fetchSchemaColumns(
            form.target_schema,
            form.target_table,
            form.required_mapping_columns,
            form.optional_columns,
            form.required_columns
        );
    }, [form.target_schema, form.target_table, fetchSchemaColumns]);

    const selectCatalog = async (name) => {
        try {
            setError('');
            setIsNew(false);
            setSelectedName(name);
            const data = await getCatalogDefinition(name);
            const f = catalogToForm(data);
            setForm(f);
            setAliasesJson(JSON.stringify(f.column_aliases, null, 2));
            setEnumsJson(JSON.stringify(f.enums, null, 2));
            await fetchSchemaColumns(
                f.target_schema,
                f.target_table,
                f.required_mapping_columns,
                f.optional_columns,
                f.required_columns
            );
            setTab('general');
        } catch (err) {
            setError(err.response?.data?.detail || 'Error al cargar catálogo');
        }
    };

    const startNew = () => {
        setIsNew(true);
        setSelectedName(null);
        const f = emptyCatalogForm();
        setForm(f);
        setAliasesJson('{}');
        setEnumsJson('{}');
        setSchemaColumns([]);
        setColumnRequired({});
        setTab('general');
    };

    const handleRequiredChange = (colName, required) => {
        setColumnRequired((prev) => ({ ...prev, [colName]: required }));
    };

    const handleSave = async () => {
        try {
            setSaving(true);
            setError('');
            if (!form.label?.trim()) {
                setError('La etiqueta es obligatoria');
                setSaving(false);
                return;
            }
            if (!form.target_table?.trim()) {
                setError('Selecciona la tabla destino');
                setSaving(false);
                return;
            }
            const payload = buildCatalogPayload(
                form,
                schemaColumns,
                columnRequired,
                aliasesJson,
                enumsJson,
                { isNew }
            );
            if (isNew) {
                await createCatalogDefinition(payload);
            } else {
                await updateCatalogDefinition(selectedName, payload);
            }
            await loadList();
            setIsNew(false);
            setSelectedName(payload.name);
            await selectCatalog(payload.name);
        } catch (err) {
            setError(err.message || err.response?.data?.detail || 'Error al guardar');
        } finally {
            setSaving(false);
        }
    };

    const handleDeactivate = async () => {
        if (!selectedName) return;
        try {
            await deleteCatalogDefinition(selectedName, false);
            await loadList();
            setSelectedName(null);
            setForm(emptyCatalogForm());
            setColumnRequired({});
        } catch (err) {
            setError(err.response?.data?.detail || 'Error al desactivar');
        } finally {
            setConfirmDeactivateOpen(false);
        }
    };

    const updateForm = (field, value) => {
        setForm((prev) => ({ ...prev, [field]: value }));
    };

    if (loading && catalogs.length === 0) {
        return (
            <div className="page-container">
                <LoadingSpinner />
            </div>
        );
    }

    return (
        <div className="flex flex-1 flex-col gap-5 overflow-y-auto p-8 max-w-6xl mx-auto w-full scrollbar-thin">
            <PageHeader
                icon={Settings2}
                title="Configuración de catálogos"
                subtitle={
                    <>
                        Define tablas destino y reglas de columnas para el mapping. Los catálogos activos aparecen en{' '}
                        <Link to="/upload/catalog">Carga de catálogos</Link>.
                    </>
                }
                action={
                    <Button variant="primary" onClick={startNew}>
                        + Nuevo catálogo
                    </Button>
                }
            />

            {error && <Alert variant="error">{error}</Alert>}

            <div className="grid grid-cols-1 lg:grid-cols-[280px_1fr] gap-4 items-start">
                <aside className="rounded-md border border-[#e2e8f0] bg-white shadow-sm dark:border-[#334155] dark:bg-slate-800 p-4">
                    <h2 className="text-sm font-semibold text-slate-800 dark:text-slate-100 mb-3">Catálogos ({catalogs.length})</h2>
                    {catalogs.map((c) => (
                        <button
                            key={c.name}
                            type="button"
                            className={`block w-full text-left p-2.5 mb-1 rounded-lg border transition-colors ${selectedName === c.name ? 'border-brand-500 bg-blue-50 dark:bg-blue-950/30' : 'border-[#e2e8f0] dark:border-[#334155] hover:border-brand-500'} ${!c.is_active ? 'opacity-55' : ''}`}
                            onClick={() => selectCatalog(c.name)}
                        >
                            <strong>{c.label}</strong>
                            <small>
                                {c.target_schema}.{c.target_table}
                                {!c.is_active ? ' · inactivo' : ''}
                            </small>
                        </button>
                    ))}
                </aside>

                <section className="rounded-md border border-[#e2e8f0] bg-white shadow-sm dark:border-[#334155] dark:bg-slate-800 p-5">
                    {!selectedName && !isNew ? (
                        <div className="text-center py-8 text-slate-500">
                            <p>Selecciona un catálogo o crea uno nuevo.</p>
                        </div>
                    ) : (
                        <>
                            <ConfigTabs tabs={CATALOG_TABS} activeTab={tab} onTabChange={setTab} />

                            {tab === 'general' && (
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                    <FormField label="Etiqueta" required className="md:col-span-2">
                                        <Input
                                            value={form.label}
                                            onChange={(e) => updateForm('label', e.target.value)}
                                            placeholder="Productos (SKUs)"
                                        />
                                    </FormField>
                                    <FormField label="Schema destino">
                                        <Select
                                            value={form.target_schema}
                                            onChange={(e) => {
                                                const schema = e.target.value;
                                                setForm((prev) => ({
                                                    ...prev,
                                                    target_schema: schema,
                                                    target_table: '',
                                                }));
                                                setSchemaColumns([]);
                                                setColumnRequired({});
                                            }}
                                            disabled={loadingDbMeta && dbSchemas.length === 0}
                                        >
                                            <option value="">-- Seleccionar esquema --</option>
                                            {dbSchemas.map((s) => (
                                                <option key={s} value={s}>
                                                    {s}
                                                </option>
                                            ))}
                                        </Select>
                                    </FormField>
                                    <FormField label="Tabla destino">
                                        <Select
                                            value={form.target_table}
                                            onChange={(e) => {
                                                updateForm('target_table', e.target.value);
                                                setSchemaColumns([]);
                                                setColumnRequired({});
                                            }}
                                            disabled={!form.target_schema || loadingDbMeta}
                                        >
                                            <option value="">-- Seleccionar tabla --</option>
                                            {dbTables.map((t) => (
                                                <option key={t.table_name} value={t.table_name}>
                                                    {t.table_name}
                                                    {t.column_count != null ? ` (${t.column_count} cols)` : ''}
                                                </option>
                                            ))}
                                        </Select>
                                    </FormField>
                                    <FormField label="Archivo config (validación)">
                                        <Input
                                            value={form.config_file}
                                            onChange={(e) => updateForm('config_file', e.target.value)}
                                            placeholder="skus_config.json"
                                        />
                                    </FormField>
                                    <FormField label="Activo en wizard de carga">
                                        <label className="inline-flex items-center gap-2 text-sm text-slate-700 dark:text-slate-300 cursor-pointer">
                                            <input
                                                type="checkbox"
                                                className="accent-brand-600 h-4 w-4"
                                                checked={form.is_active}
                                                onChange={(e) => updateForm('is_active', e.target.checked)}
                                            />
                                            Catálogo visible en carga
                                        </label>
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
                                    />
                                    <ChipListEditor
                                        label="Notas de validación (UI del wizard)"
                                        value={form.validation_hints}
                                        onChange={(v) => updateForm('validation_hints', v)}
                                    />
                                </div>
                            )}

                            {tab === 'advanced' && (
                                <div className="grid grid-cols-1 gap-4">
                                    <FormField label="Aliases (JSON) — sinónimos de cabeceras para auto-mapeo">
                                        <Textarea
                                            value={aliasesJson}
                                            onChange={(e) => setAliasesJson(e.target.value)}
                                            className="min-h-[140px]"
                                        />
                                    </FormField>
                                    <FormField label="Enums (JSON)">
                                        <Textarea
                                            value={enumsJson}
                                            onChange={(e) => setEnumsJson(e.target.value)}
                                            className="min-h-[140px]"
                                        />
                                    </FormField>
                                </div>
                            )}

                            <div className="flex flex-wrap gap-3 mt-5">
                                {!readOnly && (
                                  <>
                                    <Button variant="primary" onClick={handleSave} disabled={saving}>
                                        {saving ? 'Guardando…' : isNew ? 'Crear catálogo' : 'Guardar cambios'}
                                    </Button>
                                    {!isNew && selectedName && (
                                        <Button variant="secondary" onClick={() => setConfirmDeactivateOpen(true)}>
                                            Desactivar
                                        </Button>
                                    )}
                                  </>
                                )}
                                {readOnly && (
                                  <p className="text-sm text-slate-500">Modo solo lectura</p>
                                )}
                            </div>
                        </>
                    )}
                </section>
            </div>

            <ConfirmDialog
                isOpen={confirmDeactivateOpen}
                onClose={() => setConfirmDeactivateOpen(false)}
                onConfirm={handleDeactivate}
                title="Desactivar catálogo"
                message={`¿Desactivar catálogo "${selectedName || ''}"?`}
                confirmText="Desactivar"
                cancelText="Cancelar"
                variant="danger"
            />
        </div>
    );
};

export default CatalogAdmin;
