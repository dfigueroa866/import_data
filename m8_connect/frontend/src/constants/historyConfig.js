/**
 * Carga de historia: destino fijo public.sales_history
 */
export const HISTORY_TARGET_SCHEMA = 'public';
export const HISTORY_TARGET_TABLE = 'sales_history';
export const HISTORY_SALES_CHANNEL_VALUE = 'SELL_IN';

/** Orden sugerido de columnas en vista previa (incluye campos automáticos). */
export const HISTORY_PREVIEW_COLUMN_ORDER = [
    'location_code',
    'pieces',
    'sku',
    'period_start',
    'organization_id',
    'quantity',
    'sales_channel',
    'granularity',
    'source',
];

export const granularityFromProcessType = (processType) => {
    if (processType === 'Weekly') return 'week';
    if (processType === 'Monthly') return 'month';
    return '';
};

/**
 * Añade sales_channel, granularity, source y organization_id a filas de preview.
 */
export const enrichHistoryPreviewRows = (rows, { processType, sourceExtension, organizationId } = {}) => {
    const granularity = granularityFromProcessType(processType);
    const source = (sourceExtension || '').trim().toLowerCase();
    return (rows || []).map((row) => ({
        ...row,
        sales_channel: HISTORY_SALES_CHANNEL_VALUE,
        ...(granularity ? { granularity } : {}),
        ...(source ? { source } : {}),
        ...(organizationId ? { organization_id: organizationId } : {}),
    }));
};

export const getHistoryPreviewColumnKeys = (rows) => {
    const keys = new Set();
    (rows || []).forEach((row) => Object.keys(row || {}).forEach((k) => keys.add(k)));
    const ordered = HISTORY_PREVIEW_COLUMN_ORDER.filter((k) => keys.has(k));
    const rest = [...keys].filter((k) => !ordered.includes(k)).sort();
    return [...ordered, ...rest];
};

export const HISTORY_TABLE_META = {
    name: HISTORY_TARGET_TABLE,
    label: 'Historial de ventas (sales_history)',
    target_schema: HISTORY_TARGET_SCHEMA,
    target_table: HISTORY_TARGET_TABLE,
    required_columns: [
        'id',
        'organization_id',
        'location_code',
        'sku',
        'period_start',
        'granularity',
        'quantity',
        'source',
    ],
    required_mapping_columns: ['location_code', 'period_start', 'quantity', 'pieces'],
    sku_mapping_targets: ['sku_code', 'sku'],
    logical_columns: ['sku_code'],
    unique_keys: [
        'organization_id',
        'location_code',
        'sku',
        'period_start',
        'granularity',
    ],
    ignored_file_headers: ['id'],
    non_mappable_targets: ['id', 'granularity', 'source', 'sales_channel'],
    optional_columns: ['sales_channel', 'pieces', 'source'],
    column_aliases: {
        period_start: ['period_start', 'start_date', 'fecha', 'date', 'week_monday'],
        quantity: ['quantity', 'qty', 'cantidad', 'amount'],
        location_code: ['location_code', 'loc', 'location', 'store', 'tienda'],
        sku_code: ['sku_code', 'dmd_unit', 'sku', 'product_code', 'code', 'item'],
        granularity: ['granularity', 'gran', 'period_type'],
        sales_channel: ['sales_channel', 'channel', 'canal', 'sales channel'],
        pieces: ['pieces', 'piezas', 'units', 'unidades'],
    },
    defaults: {},
    validation_hints: [
        'Destino: public.sales_history',
        'Mapea location_code, sku (o sku_code) y period_start, quantity, pieces',
        'UPSERT: organization_id + location_code + sku + period_start + granularity',
        'sales_channel siempre es SELL_IN (automático)',
        'granularity: week (Weekly) o month (Monthly) según el tipo de proceso',
        'source: extensión del archivo subido (csv, xlsx, etc.)',
        'organization_id se aplica automáticamente',
    ],
};

/** Columna lógica para el dropdown de mapeo (no existe en la tabla física). */
export const HISTORY_LOGICAL_COLUMN_DEFS = [
    {
        name: 'sku_code',
        type: 'text (código SKU → columna sku)',
        nullable: false,
        default: null,
    },
];
