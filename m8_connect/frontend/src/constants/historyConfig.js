/**
 * Carga de historia: destino fijo public.sales_history
 */
export const HISTORY_TARGET_SCHEMA = 'public';
export const HISTORY_TARGET_TABLE = 'sales_history';
export const HISTORY_SALES_CHANNEL_VALUE = 'SELL_IN';

/** Tipos de proceso por defecto si el API no responde. */
export const FALLBACK_PROCESS_TYPES = [
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

export const granularityFromProcessType = (processType, processTypes = null) => {
    const list = processTypes || FALLBACK_PROCESS_TYPES;
    const found = list.find((pt) => pt.key === processType);
    if (found?.granularity) return found.granularity;
    if (processType === 'Weekly') return 'week';
    if (processType === 'Monthly') return 'month';
    return '';
};

/** Orden sugerido de columnas en vista previa (incluye campos automáticos). */
export const HISTORY_PREVIEW_COLUMN_ORDER = [
    'location_code',
    'pieces',
    'sku',
    'period_start',
    'iso_year',
    'iso_week',
    'organization_id',
    'quantity',
    'sales_channel',
    'granularity',
    'source',
    'stockout_flag',
    'markdown_pct',
    'promo_flag',
];

/** Extensión del archivo original (p. ej. csv, xlsx). */
export const sourceFromFileName = (fileName) => {
    const match = String(fileName || '').match(/\.([^.]+)$/i);
    return match ? match[1].toLowerCase() : 'unknown';
};

/** Columnas de destino que el wizard rellena automáticamente (no mapear desde archivo). */
export const HISTORY_AUTO_MAPPING_COLUMNS = [
    'organization_id',
    'granularity',
    'source',
    'sales_channel',
    'iso_year',
    'iso_week',
    'stockout_flag',
    'markdown_pct',
    'promo_flag',
];

/**
 * Añade organization_id a filas de preview cuando aplica (contexto de sesión).
 */
export const enrichHistoryPreviewRows = (rows, { organizationId } = {}) => {
    return (rows || []).map((row) => ({
        ...row,
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
        'organization_id',
        'location_code',
        'sku',
        'period_start',
    //    'granularity',
        'quantity'
    //    'source',
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
    non_mappable_targets: [
        'granularity',
        'source',
        'sales_channel',
        'iso_year',
        'iso_week',
        'stockout_flag',
        'markdown_pct',
        'promo_flag',
    ],
    optional_columns: ['pieces'],
    column_aliases: {
        period_start: ['period_start', 'start_date', 'fecha', 'date', 'week_monday'],
        quantity: ['quantity', 'qty', 'cantidad', 'amount'],
        location_code: ['location_code', 'loc', 'location', 'store', 'tienda'],
        sku_code: ['sku_code', 'dmd_unit', 'sku', 'product_code', 'code', 'item'],
        sales_channel: ['sales_channel', 'channel', 'canal', 'sales channel'],
        pieces: ['pieces', 'piezas', 'units', 'unidades'],
    },
    validation_hints: [
        'Destino: public.sales_history',
        'Mapea location_code, sku (o sku_code) y period_start, quantity, pieces',
        'UPSERT: organization_id + location_code + sku + period_start + granularity',
        'granularity se toma del campo Granularidad (tipo de proceso) del paso 1',
        'source se toma de la extensión del archivo subido',
        'sales_channel se aplica automáticamente como SELL_IN',
        'organization_id se aplica automáticamente del usuario',
        'iso_year e iso_week se derivan de period_start (tras agregación)',
        'stockout_flag=false, markdown_pct=0, promo_flag=false (automáticos)',
    ],
    process_types: FALLBACK_PROCESS_TYPES,
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

export const INVENTORY_SNAPSHOT_TABLE_META = {
    name: 'inventory_snapshot',
    label: 'Inventario (snapshot)',
    target_schema: HISTORY_TARGET_SCHEMA,
    target_table: 'inventory_snapshot',
    supports_aggregation: false,
    period_column: 'snapshot_date',
    required_mapping_columns: ['snapshot_date', 'sku', 'location_code', 'on_hand_qty'],
    optional_columns: [
        'allocated_qty',
        'reserved_qty',
        'blocked_qty',
        'quarantine_qty',
        'supplier_id',
        'lead_time_days',
        'review_period_days',
        'moq',
        'lot_multiple',
        'unit_cost',
        'currency',
    ],
    sku_mapping_targets: ['sku'],
    logical_columns: ['sku_code'],
    unique_keys: ['organization_id', 'sku', 'location_code', 'snapshot_date'],
    ignored_file_headers: ['snapshot_id', 'organization_id', 'created_at'],
    non_mappable_targets: ['organization_id', 'snapshot_id', 'created_at'],
    features: {
        auto_granularity: false,
        auto_source: false,
        auto_sales_channel: false,
        derived_iso_flags: false,
    },
    process_types: [
        {
            key: 'Snapshot',
            label: 'Snapshot (sin agregación)',
            granularity: 'snapshot',
            date_truncate: '1d',
        },
    ],
    validation_hints: [
        'Destino: public.inventory_snapshot',
        'Mapea snapshot_date, sku, location_code y on_hand_qty como mínimo',
        'snapshot_id y created_at los genera la base de datos',
        'organization_id se aplica automáticamente del usuario',
    ],
};

export const FALLBACK_HISTORY_TABLES = [HISTORY_TABLE_META, INVENTORY_SNAPSHOT_TABLE_META];
