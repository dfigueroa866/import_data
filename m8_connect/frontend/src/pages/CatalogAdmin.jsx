import React, { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { Settings2 } from 'lucide-react';
import { Button, PageHeader, LoadingSpinner, Alert, FormField, Input, Select, Textarea, Chip } from '../components/ui';
import {
    listCatalogDefinitions,
    getCatalogDefinition,
    createCatalogDefinition,
    updateCatalogDefinition,
    deleteCatalogDefinition,
    fetchTargetTableColumns,
    emptyCatalogForm,
    catalogToForm,
} from '../services/catalogAdminService';
import { getSchemas, getTables } from '../services/systemService';

const TABS = [
    { id: 'general', label: 'General' },
    { id: 'columns', label: 'Columnas' },
    { id: 'mapping', label: 'Mapping' },
    { id: 'advanced', label: 'Avanzado' },
];

const ChipListEditor = ({ label, value, onChange, hint }) => {
    const [draft, setDraft] = useState('');

    const addChip = () => {
        const v = draft.trim();
        if (!v || value.includes(v)) return;
        onChange([...value, v]);
        setDraft('');
    };

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

const ColumnListEditor = ({ label, value, onChange, schemaColumns, hint, excludeColumns = [] }) => {
    const allowedNames = new Set(schemaColumns.map((c) => c.name));
    const colByName = Object.fromEntries(schemaColumns.map((c) => [c.name, c]));

    const available = schemaColumns
        .map((c) => c.name)
        .filter((name) => !value.includes(name) && !excludeColumns.includes(name));

    const addColumn = (colName) => {
        if (!allowedNames.has(colName) || value.includes(colName)) return;
        onChange([...value, colName]);
    };

    const columnTitle = (name) => {
        const col = colByName[name];
        if (!col) return 'Columna no presente en la tabla destino';
        return `${col.type}${col.nullable ? '' : ' NOT NULL'}`;
    };

    return (
        <FormField label={label} hint={hint} className="md:col-span-2">
            {schemaColumns.length === 0 ? (
                <p className="text-xs text-slate-500 dark:text-slate-400">
                    Selecciona schema y tabla destino en General para listar columnas disponibles.
                </p>
            ) : (
                <>
                    <div className="flex flex-wrap gap-1.5 p-3 rounded-lg border border-[#e2e8f0] bg-white shadow-sm dark:border-[#334155] dark:bg-slate-800 min-h-[3rem]">
                        {value.length === 0 && (
                            <span className="text-xs text-slate-400">Ninguna columna seleccionada</span>
                        )}
                        {value.map((chip) => (
                            <span key={chip} title={columnTitle(chip)}>
                                <Chip
                                    invalid={!allowedNames.has(chip)}
                                    onRemove={() => onChange(value.filter((c) => c !== chip))}
                                >
                                    {chip}
                                </Chip>
                            </span>
                        ))}
                    </div>
                    {available.length > 0 ? (
                        <div className="flex flex-wrap gap-1.5 mt-2">
                            {available.map((name) => (
                                <button
                                    key={name}
                                    type="button"
                                    title={columnTitle(name)}
                                    onClick={() => addColumn(name)}
                                    className="text-xs px-2 py-1 rounded-full border border-[#e2e8f0] bg-slate-50 text-slate-600 transition-colors hover:border-brand-500 hover:bg-blue-50 hover:text-brand-700 dark:border-[#334155] dark:bg-slate-700 dark:text-slate-300 dark:hover:bg-blue-950/30"
                                >
                                    + {name}
                                </button>
                            ))}
                        </div>
                    ) : (
                        <p className="text-xs text-slate-500 dark:text-slate-400 mt-2">
                            Todas las columnas de la tabla ya están asignadas.
                        </p>
                    )}
                </>
            )}
        </FormField>
    );
};

const CatalogAdmin = () => {
    const [catalogs, setCatalogs] = useState([]);
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState('');
    const [selectedName, setSelectedName] = useState(null);
    const [isNew, setIsNew] = useState(false);
    const [tab, setTab] = useState('general');
    const [form, setForm] = useState(emptyCatalogForm());
    const [schemaColumns, setSchemaColumns] = useState([]);
    const [aliasesJson, setAliasesJson] = useState('{}');
    const [enumsJson, setEnumsJson] = useState('{}');
    const [defaultsJson, setDefaultsJson] = useState('{}');
    const [dbSchemas, setDbSchemas] = useState([]);
    const [dbTables, setDbTables] = useState([]);
    const [loadingDbMeta, setLoadingDbMeta] = useState(false);

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

    const fetchSchemaColumns = useCallback(async (schema, table) => {
        if (!schema || !table) {
            setSchemaColumns([]);
            return [];
        }
        try {
            const cols = await fetchTargetTableColumns(schema, table);
            setSchemaColumns(cols);
            return cols;
        } catch {
            setSchemaColumns([]);
            return [];
        }
    }, []);

    useEffect(() => {
        fetchSchemaColumns(form.target_schema, form.target_table);
    }, [form.target_schema, form.target_table, fetchSchemaColumns]);

    useEffect(() => {
        if (schemaColumns.length === 0) return;
        const allowed = new Set(schemaColumns.map((c) => c.name));
        setForm((prev) => {
            const required_columns = prev.required_columns.filter((c) => allowed.has(c));
            const optional_columns = prev.optional_columns.filter((c) => allowed.has(c));
            if (
                required_columns.length === prev.required_columns.length &&
                optional_columns.length === prev.optional_columns.length
            ) {
                return prev;
            }
            return { ...prev, required_columns, optional_columns };
        });
    }, [schemaColumns]);

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
            setDefaultsJson(JSON.stringify(f.defaults, null, 2));
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
        setDefaultsJson('{}');
        setSchemaColumns([]);
        setTab('general');
    };

    const reloadSchemaColumns = async () => {
        if (!form.target_schema || !form.target_table) {
            setError('Indica schema y tabla destino');
            return;
        }
        try {
            setError('');
            const cols = await fetchSchemaColumns(form.target_schema, form.target_table);
            if (cols.length === 0) {
                setError(`No se encontraron columnas en ${form.target_schema}.${form.target_table}`);
            }
        } catch (err) {
            setError(err.response?.data?.detail || 'No se pudieron cargar columnas');
        }
    };

    const buildPayload = () => {
        let column_aliases = {};
        let enums = {};
        let defaults = {};
        try {
            column_aliases = JSON.parse(aliasesJson || '{}');
            enums = JSON.parse(enumsJson || '{}');
            defaults = JSON.parse(defaultsJson || '{}');
        } catch {
            throw new Error('JSON inválido en aliases, enums o defaults');
        }
        return {
            ...form,
            target_table: form.target_table || form.name,
            config_file: form.config_file || `${form.name}_config.json`,
            column_aliases,
            enums,
            defaults,
        };
    };

    const handleSave = async () => {
        try {
            setSaving(true);
            setError('');
            const payload = buildPayload();
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
        if (!selectedName || !window.confirm(`¿Desactivar catálogo "${selectedName}"?`)) return;
        try {
            await deleteCatalogDefinition(selectedName, false);
            await loadList();
            setSelectedName(null);
            setForm(emptyCatalogForm());
        } catch (err) {
            setError(err.response?.data?.detail || 'Error al desactivar');
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
                        Define tablas destino, columnas mapeables y reglas. Los catálogos activos aparecen en{' '}
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
                            <div className="flex flex-wrap gap-2 mb-4">
                                {TABS.map((t) => (
                                    <button
                                        key={t.id}
                                        type="button"
                                        className={`px-3 py-1.5 rounded-lg border text-sm transition-colors ${tab === t.id ? 'border-brand-600 bg-blue-50 text-brand-700 dark:bg-blue-950/30' : 'border-[#e2e8f0] dark:border-[#334155] text-slate-600'}`}
                                        onClick={() => setTab(t.id)}
                                    >
                                        {t.label}
                                    </button>
                                ))}
                            </div>

                            {tab === 'general' && (
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                    <FormField label="Nombre (slug)" required>
                                        <Input
                                            value={form.name}
                                            onChange={(e) => updateForm('name', e.target.value)}
                                            disabled={!isNew}
                                            placeholder="ej. skus"
                                        />
                                    </FormField>
                                    <FormField label="Etiqueta" required>
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
                                    <div className="md:col-span-2">
                                        <Button variant="secondary" size="small" onClick={reloadSchemaColumns}>
                                            Recargar columnas desde BD
                                        </Button>
                                        {schemaColumns.length > 0 && (
                                            <p className="text-xs text-slate-500 dark:text-slate-400 mt-2">
                                                {schemaColumns.length} columnas en {form.target_schema}.
                                                {form.target_table} — configúralas en la pestaña Columnas.
                                            </p>
                                        )}
                                    </div>
                                </div>
                            )}

                            {tab === 'columns' && (
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                    <ColumnListEditor
                                        label="Columnas requeridas (datos)"
                                        value={form.required_columns}
                                        onChange={(v) => updateForm('required_columns', v)}
                                        schemaColumns={schemaColumns}
                                        excludeColumns={form.optional_columns}
                                        hint="Clic en una columna de la tabla para añadirla"
                                    />
                                    <ColumnListEditor
                                        label="Columnas opcionales"
                                        value={form.optional_columns}
                                        onChange={(v) => updateForm('optional_columns', v)}
                                        schemaColumns={schemaColumns}
                                        excludeColumns={form.required_columns}
                                        hint="Solo columnas de la tabla destino seleccionada"
                                    />
                                    <ChipListEditor
                                        label="Notas de validación (UI)"
                                        value={form.validation_hints}
                                        onChange={(v) => updateForm('validation_hints', v)}
                                    />
                                </div>
                            )}

                            {tab === 'mapping' && (
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                    <ChipListEditor
                                        label="Obligatorias en paso 2 (mapping)"
                                        value={form.required_mapping_columns}
                                        onChange={(v) => updateForm('required_mapping_columns', v)}
                                        hint="Ej. status en SKUs"
                                    />
                                    <ChipListEditor
                                        label="Cabeceras de archivo ignoradas"
                                        value={form.ignored_file_headers}
                                        onChange={(v) => updateForm('ignored_file_headers', v)}
                                        hint="No aparecen en el mapping (sku_id, created_at…)"
                                    />
                                    <ChipListEditor
                                        label="Destinos no mapeables"
                                        value={form.non_mappable_targets}
                                        onChange={(v) => updateForm('non_mappable_targets', v)}
                                        hint="No en dropdown destino (PK, auditoría)"
                                    />
                                </div>
                            )}

                            {tab === 'advanced' && (
                                <div className="grid grid-cols-1 gap-4">
                                    <FormField label="Aliases (JSON, opcional — no usado en auto-mapeo)">
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
                                    <FormField label="Defaults al transformar (JSON)">
                                        <Textarea
                                            value={defaultsJson}
                                            onChange={(e) => setDefaultsJson(e.target.value)}
                                            className="min-h-[140px]"
                                        />
                                    </FormField>
                                </div>
                            )}

                            <div className="flex flex-wrap gap-3 mt-5">
                                <Button variant="primary" onClick={handleSave} disabled={saving}>
                                    {saving ? 'Guardando…' : isNew ? 'Crear catálogo' : 'Guardar cambios'}
                                </Button>
                                {!isNew && selectedName && (
                                    <Button variant="secondary" onClick={handleDeactivate}>
                                        Desactivar
                                    </Button>
                                )}
                            </div>
                        </>
                    )}
                </section>
            </div>
        </div>
    );
};

export default CatalogAdmin;
