import React, { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { History } from 'lucide-react';
import { Button, PageHeader, LoadingSpinner, Alert, FormField, Input } from '../components/ui';
import { useAuth } from '../context/AuthContext';
import { fetchTargetTableColumns } from '../services/catalogAdminService';
import {
    HISTORY_TABLE_META,
    HISTORY_TARGET_SCHEMA,
    HISTORY_TARGET_TABLE,
} from '../constants/historyConfig';
import { buildColumnRequiredMap, classifyHistoryColumn } from '../utils/catalogColumnRules';
import {
    HISTORY_TABS,
    CatalogColumnsEditor,
    ChipListEditor,
    ConfigTabs,
} from '../components/admin/CatalogConfigEditors';

const HISTORY_FOOTER_NOTE = (
    <>
        Las columnas PK, <code className="font-mono">organization_id</code>,{' '}
        <code className="font-mono">granularity</code>, <code className="font-mono">source</code> y{' '}
        <code className="font-mono">sales_channel</code> se asignan automáticamente en el wizard.
        Las columnas NOT NULL en la BD se marcan obligatorias por defecto.
    </>
);

const HistoryAdmin = () => {
    const { user } = useAuth();
    const organizationName = user?.organization_name || '';

    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [tab, setTab] = useState('general');
    const [schemaColumns, setSchemaColumns] = useState([]);
    const [columnRequired, setColumnRequired] = useState({});

    const loadSchemaColumns = useCallback(async () => {
        try {
            setLoading(true);
            setError('');
            const cols = await fetchTargetTableColumns(HISTORY_TARGET_SCHEMA, HISTORY_TARGET_TABLE);
            setSchemaColumns(cols);
            setColumnRequired(
                buildColumnRequiredMap(
                    cols,
                    HISTORY_TABLE_META.required_mapping_columns,
                    HISTORY_TABLE_META.optional_columns
                )
            );
        } catch (err) {
            setError(err.response?.data?.detail || 'No se pudieron cargar las columnas de historia');
            setSchemaColumns([]);
            setColumnRequired({});
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        loadSchemaColumns();
    }, [loadSchemaColumns]);

    const handleRequiredChange = () => {
        // Placeholder: la persistencia de configuración se añadirá más adelante.
    };

    if (loading) {
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
                        Reglas de columnas para el mapping de cargas históricas. Destino fijo:{' '}
                        <code className="font-mono text-sm">
                            {HISTORY_TARGET_SCHEMA}.{HISTORY_TARGET_TABLE}
                        </code>
                        . Usado en <Link to="/upload/history">Carga de historia</Link>.
                    </>
                }
            />

            {error && <Alert variant="error">{error}</Alert>}

            <Alert variant="info">
                La edición y guardado de esta configuración estará disponible próximamente.
                Por ahora puedes revisar las columnas y reglas actuales del sistema.
            </Alert>

            <div className="grid grid-cols-1 lg:grid-cols-[280px_1fr] gap-4 items-start">
                <aside className="rounded-md border border-[#e2e8f0] bg-white shadow-sm dark:border-[#334155] dark:bg-slate-800 p-4">
                    <h2 className="text-sm font-semibold text-slate-800 dark:text-slate-100 mb-3">Destinos</h2>
                    <button
                        type="button"
                        className="block w-full text-left p-2.5 rounded-lg border border-brand-500 bg-blue-50 dark:bg-blue-950/30"
                    >
                        <strong>{HISTORY_TABLE_META.label}</strong>
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
                                <Input value={HISTORY_TABLE_META.label} readOnly disabled />
                            </FormField>
                            <FormField label="Schema destino">
                                <Input value={HISTORY_TARGET_SCHEMA} readOnly disabled />
                            </FormField>
                            <FormField label="Tabla destino">
                                <Input value={HISTORY_TARGET_TABLE} readOnly disabled />
                            </FormField>
                            <FormField label="Tipo de carga" className="md:col-span-2">
                                <Input value="Historia de ventas (agregación semanal/mensual)" readOnly disabled />
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
                                readOnly
                                footerNote={HISTORY_FOOTER_NOTE}
                            />
                            <ChipListEditor
                                label="Notas de validación (UI del wizard)"
                                value={HISTORY_TABLE_META.validation_hints || []}
                                readOnly
                            />
                        </div>
                    )}

                    <div className="flex flex-wrap gap-3 mt-5">
                        <Button variant="primary" disabled title="Próximamente">
                            Guardar cambios
                        </Button>
                    </div>
                </section>
            </div>
        </div>
    );
};

export default HistoryAdmin;
