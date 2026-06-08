import api from './api';

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
    ignored_file_headers: ['created_at', 'updated_at', 'imported_at', 'organization_id'],
    non_mappable_targets: ['organization_id', 'created_at', 'updated_at', 'imported_at'],
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
