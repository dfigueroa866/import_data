import api from './api';
import {
    buildColumnRequiredMap,
    buildColumnDefaultsState,
    deriveCatalogMappingFields,
} from '../utils/catalogColumnRules';

export const listCatalogDefinitions = async () => {
    const { data } = await api.get('/api/v1/catalogs/admin');
    return data.catalogs || [];
};

export const getCatalogDefinition = async (name) => {
    const { data } = await api.get(`/api/v1/catalogs/admin/${encodeURIComponent(name)}`);
    return data;
};

export const createCatalogDefinition = async (payload) => {
    const { data } = await api.post('/api/v1/catalogs/admin', payload);
    return data;
};

export const updateCatalogDefinition = async (name, payload) => {
    const { data } = await api.put(`/api/v1/catalogs/admin/${encodeURIComponent(name)}`, payload);
    return data;
};

export const deleteCatalogDefinition = async (name, hard = false) => {
    const { data } = await api.delete(`/api/v1/catalogs/admin/${encodeURIComponent(name)}`, {
        params: { hard },
    });
    return data;
};

export const fetchTargetTableColumns = async (schema, table) => {
    const { data } = await api.get('/api/v1/catalogs/admin/schema-columns', {
        params: { schema, table },
    });
    return data.columns || [];
};

export const emptyCatalogForm = () => ({
    name: '',
    label: '',
    target_schema: 'public',
    target_table: '',
    config_file: '',
    is_active: true,
    required_columns: [],
    optional_columns: [],
    required_mapping_columns: [],
    unique_keys: [],
    ignored_file_headers: [],
    non_mappable_targets: [],
    column_aliases: {},
    enums: {},
    defaults: {},
    validation_hints: [],
});

export const catalogToForm = (catalog) => ({
    name: catalog.name || '',
    label: catalog.label || '',
    target_schema: catalog.target_schema || 'public',
    target_table: catalog.target_table || catalog.name || '',
    config_file: catalog.config_file || '',
    is_active: catalog.is_active !== false,
    required_columns: [...(catalog.required_columns || [])],
    optional_columns: [...(catalog.optional_columns || [])],
    required_mapping_columns: [...(catalog.required_mapping_columns || [])],
    unique_keys: [...(catalog.unique_keys || [])],
    ignored_file_headers: [...(catalog.ignored_file_headers || [])],
    non_mappable_targets: [...(catalog.non_mappable_targets || [])],
    column_aliases: { ...(catalog.column_aliases || {}) },
    enums: { ...(catalog.enums || {}) },
    defaults: { ...(catalog.defaults || {}) },
    validation_hints: [...(catalog.validation_hints || [])],
});

export { buildColumnRequiredMap, buildColumnDefaultsState, deriveCatalogMappingFields };

export const buildCatalogPayload = (
    form,
    schemaColumns,
    columnRequiredMap,
    aliasesJson,
    enumsJson,
    { isNew = false, columnDefaultEnabledMap = {}, columnDefaultValuesMap = {} } = {}
) => {
    let column_aliases = {};
    let enums = {};
    try {
        column_aliases = JSON.parse(aliasesJson || '{}');
        enums = JSON.parse(enumsJson || '{}');
    } catch {
        throw new Error('JSON inválido en aliases o enums');
    }

    const targetTable = (form.target_table || '').trim();
    const catalogName = isNew ? targetTable : (form.name || targetTable);

    if (schemaColumns.length > 0) {
        for (const col of schemaColumns) {
            const name = col?.name;
            if (!name || !columnDefaultEnabledMap[name]) continue;
            if (!String(columnDefaultValuesMap[name] ?? '').trim()) {
                throw new Error(
                    `La columna "${name}" tiene "Usar default" activo pero el valor está vacío`
                );
            }
        }
    }

    const derived =
        schemaColumns.length > 0
            ? deriveCatalogMappingFields(
                  schemaColumns,
                  columnRequiredMap,
                  columnDefaultEnabledMap,
                  columnDefaultValuesMap
              )
            : {
                  required_mapping_columns: form.required_mapping_columns,
                  required_columns: form.required_columns,
                  optional_columns: form.optional_columns,
                  non_mappable_targets: form.non_mappable_targets,
                  ignored_file_headers: form.ignored_file_headers,
                  defaults: form.defaults || {},
              };

    return {
        ...form,
        ...derived,
        name: catalogName,
        target_table: targetTable,
        config_file: form.config_file || `${targetTable}_config.json`,
        column_aliases,
        enums,
        defaults: derived.defaults || {},
    };
};
