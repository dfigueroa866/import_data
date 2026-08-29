import api from './api';

export const DEFAULT_PROCESS_TYPES = [
    {
        key: 'Weekly',
        label: 'Weekly (agrupa por semana)',
        granularity: 'week',
        date_truncate: '1w',
    },
    {
        key: 'Monthly',
        label: 'Monthly (agrupa por mes)',
        granularity: 'month',
        date_truncate: '1mo',
    },
];

export const emptyProcessType = () => ({
    key: '',
    label: '',
    granularity: '',
    date_truncate: '1w',
});

export const listHistoryDefinitions = async () => {
    const { data } = await api.get('/api/v1/history/admin');
    return data?.tables || [];
};

export const getHistoryDefinition = async (tableName = 'sales_history') => {
    const { data } = await api.get(`/api/v1/history/admin/${encodeURIComponent(tableName)}`);
    return data;
};

export const updateHistoryDefinition = async (tableName, payload) => {
    const { data } = await api.put(
        `/api/v1/history/admin/${encodeURIComponent(tableName)}`,
        payload,
    );
    return data;
};

export const DEFAULT_SALES_CHANNEL = 'SELL_IN';

export const buildHistorySavePayload = (
    definition,
    {
        processTypes,
        salesChannelDefault,
        mappingFields = {},
        columnDefaultEnabledMap = {},
        columnDefaultValuesMap = {},
        schemaColumns = [],
    }
) => {
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

    return {
        name: definition?.name,
        label: definition?.label,
        unique_keys: definition?.unique_keys || [],
        required_mapping_columns: mappingFields.required_mapping_columns ?? definition?.required_mapping_columns ?? [],
        optional_columns: mappingFields.optional_columns ?? definition?.optional_columns ?? [],
        non_mappable_targets: mappingFields.non_mappable_targets ?? definition?.non_mappable_targets ?? [],
        ignored_file_headers: mappingFields.ignored_file_headers ?? definition?.ignored_file_headers ?? [],
        defaults: mappingFields.defaults ?? definition?.defaults ?? {},
        sku_mapping_targets: definition?.sku_mapping_targets || ['sku'],
        logical_columns: definition?.logical_columns || ['sku_code'],
        sales_channel_default: String(
            salesChannelDefault ?? definition?.sales_channel_default ?? DEFAULT_SALES_CHANNEL
        ).trim() || DEFAULT_SALES_CHANNEL,
        process_types: processTypes,
        validation_hints: definition?.validation_hints || [],
    };
};
