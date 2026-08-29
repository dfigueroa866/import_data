/** Catalog column classification and mapping field derivation (admin + wizard). */

export const AUDIT_COLUMN_NAMES = new Set(['created_at', 'updated_at', 'imported_at']);

const PK_NAME_ALIASES = {
    sku_id: ['sku_id', 'skuid'],
    location_id: ['location_id', 'locationid'],
    id: ['id'],
};

export function isUuidColumnType(type) {
    return String(type || '').toLowerCase().includes('uuid');
}

/**
 * @param {{ name: string, type?: string, is_primary_key?: boolean }} col
 * @returns {'organization'|'primary_key'|'audit'|'mappable'}
 */
export function classifyCatalogColumn(col) {
    const name = col?.name || '';
    if (name === 'organization_id') return 'organization';
    if (AUDIT_COLUMN_NAMES.has(name)) return 'audit';
    if (col.is_primary_key) return 'primary_key';
    return 'mappable';
}

export function isCatalogColumnMappable(col) {
    return classifyCatalogColumn(col) === 'mappable';
}

const HISTORY_AUTO_COLUMNS = new Set([
    'granularity',
    'source',
    'sales_channel',
    'iso_year',
    'iso_week',
    'stockout_flag',
    'markdown_pct',
    'promo_flag',
]);

/** Columnas que se mapean desde el archivo en el paso 2 (aunque formen parte de la clave UPSERT). */
export const HISTORY_FILE_MAPPING_COLUMNS = new Set([
    'location_code',
    'sku',
    'period_start',
    'snapshot_date',
    'quantity',
    'pieces',
    'on_hand_qty',
    'allocated_qty',
    'reserved_qty',
    'blocked_qty',
    'quarantine_qty',
]);

/**
 * @param {{ name: string, type?: string, is_primary_key?: boolean }} col
 * @returns {'organization'|'primary_key'|'audit'|'auto'|'mappable'}
 */
export function classifyHistoryColumn(col) {
    const name = col?.name || '';
    if (HISTORY_AUTO_COLUMNS.has(name)) return 'auto';
    if (HISTORY_FILE_MAPPING_COLUMNS.has(name)) return 'mappable';
    if (name === 'id') return 'primary_key';
    return classifyCatalogColumn(col);
}

export function isHistoryColumnMappable(col) {
    return classifyHistoryColumn(col) === 'mappable';
}

/** Columnas que siempre deben mapearse desde archivo en paso 2. */
export const HISTORY_ALWAYS_REQUIRED_MAPPING = ['location_code'];

/** Build required map for history admin (uses history column classification). */
export function buildHistoryColumnRequiredMap(
    schemaColumns,
    requiredMappingColumns = [],
    optionalColumns = []
) {
    const requiredSet = new Set(requiredMappingColumns || []);
    const optionalSet = new Set(optionalColumns || []);
    const alwaysRequired = new Set(HISTORY_ALWAYS_REQUIRED_MAPPING);
    const map = {};
    (schemaColumns || []).forEach((col) => {
        if (!isHistoryColumnMappable(col)) return;
        if (alwaysRequired.has(col.name)) {
            map[col.name] = true;
            return;
        }
        if (requiredSet.has(col.name)) {
            map[col.name] = true;
        } else if (optionalSet.has(col.name)) {
            map[col.name] = false;
        } else {
            map[col.name] = col.nullable === false;
        }
    });
    return map;
}

/**
 * Derive persisted history mapping lists from admin column toggles.
 */
export function deriveHistoryMappingFields(
    schemaColumns,
    columnRequiredMap = {},
    columnDefaultEnabledMap = {},
    columnDefaultValuesMap = {}
) {
    const required_mapping_columns = [];
    const optional_columns = [];
    const non_mappable_targets = [];
    const ignored_file_headers = ['id'];
    const defaults = {};

    (schemaColumns || []).forEach((col) => {
        const kind = classifyHistoryColumn(col);
        const name = col.name;

        if (kind === 'organization') {
            non_mappable_targets.push(name);
            ignored_file_headers.push(name);
            return;
        }

        if (kind === 'auto' || kind === 'audit' || kind === 'primary_key') {
            non_mappable_targets.push(name);
            if (name === 'id' || kind === 'primary_key') {
                ignored_file_headers.push(name);
            }
            return;
        }

        if (columnRequiredMap[name]) {
            required_mapping_columns.push(name);
        } else {
            optional_columns.push(name);
        }

        if (columnDefaultEnabledMap[name]) {
            const text = String(columnDefaultValuesMap[name] ?? '').trim();
            if (text) {
                defaults[name] = text;
            }
        }
    });

    HISTORY_ALWAYS_REQUIRED_MAPPING.forEach((colName) => {
        if (!required_mapping_columns.includes(colName)) {
            required_mapping_columns.push(colName);
        }
        const optIdx = optional_columns.indexOf(colName);
        if (optIdx >= 0) {
            optional_columns.splice(optIdx, 1);
        }
    });

    return {
        required_mapping_columns,
        optional_columns,
        non_mappable_targets: [...new Set(non_mappable_targets)],
        ignored_file_headers: [...new Set(ignored_file_headers)],
        defaults,
    };
}

/** Mappable columns with NOT NULL in DB default to required only when no catalog lists exist yet. */
export function isCatalogColumnRequiredBySchema(col) {
    return isCatalogColumnMappable(col) && col.nullable === false;
}

/**
 * Build { [columnName]: boolean } from saved catalog lists.
 * Config is the source of truth: once required/optional lists exist, do not infer from DB NOT NULL.
 * When both lists are empty (new catalog / table just selected), seed from DB nullable.
 */
export function buildColumnRequiredMap(
    schemaColumns,
    requiredMappingColumns = [],
    optionalColumns = [],
    requiredColumns = []
) {
    const requiredSet = new Set([
        ...(requiredColumns || []),
        ...(requiredMappingColumns || []),
    ]);
    requiredSet.delete('organization_id');
    const optionalSet = new Set(optionalColumns || []);
    const hasSavedLists = requiredSet.size > 0 || optionalSet.size > 0;
    const map = {};
    (schemaColumns || []).forEach((col) => {
        if (!isCatalogColumnMappable(col)) return;
        if (requiredSet.has(col.name)) {
            map[col.name] = true;
        } else if (optionalSet.has(col.name)) {
            map[col.name] = false;
        } else if (hasSavedLists) {
            map[col.name] = false;
        } else {
            map[col.name] = col.nullable === false;
        }
    });
    return map;
}

/**
 * Derive persisted catalog lists from admin column toggles + schema metadata.
 * @param {object} [columnDefaultEnabledMap]
 * @param {object} [columnDefaultValuesMap]
 */
export function deriveCatalogMappingFields(
    schemaColumns,
    columnRequiredMap = {},
    columnDefaultEnabledMap = {},
    columnDefaultValuesMap = {}
) {
    const required_mapping_columns = [];
    const optional_columns = [];
    const non_mappable_targets = [];
    const ignored_file_headers = [];
    const defaults = {};

    (schemaColumns || []).forEach((col) => {
        const kind = classifyCatalogColumn(col);
        const name = col.name;

        if (kind === 'organization') {
            non_mappable_targets.push(name);
            ignored_file_headers.push(name);
            return;
        }

        if (kind === 'audit' || kind === 'primary_key') {
            non_mappable_targets.push(name);
            ignored_file_headers.push(name);
            const aliases = PK_NAME_ALIASES[name];
            if (aliases) {
                aliases.forEach((a) => {
                    if (!ignored_file_headers.includes(a)) ignored_file_headers.push(a);
                });
            }
            return;
        }

        if (columnRequiredMap[name]) {
            required_mapping_columns.push(name);
        } else {
            optional_columns.push(name);
        }

        if (columnDefaultEnabledMap[name]) {
            const text = String(columnDefaultValuesMap[name] ?? '').trim();
            if (text) {
                defaults[name] = text;
            }
        }
    });

    return {
        required_mapping_columns,
        required_columns: [...required_mapping_columns],
        optional_columns,
        non_mappable_targets,
        ignored_file_headers,
        defaults,
    };
}

/** Build default enabled/value maps from saved history.defaults. */
export function buildHistoryColumnDefaultsState(schemaColumns, savedDefaults = {}) {
    const enabled = {};
    const values = {};
    const raw = savedDefaults && typeof savedDefaults === 'object' ? savedDefaults : {};
    (schemaColumns || []).forEach((col) => {
        if (!isHistoryColumnMappable(col)) return;
        const text = raw[col.name] == null ? '' : String(raw[col.name]).trim();
        if (text) {
            enabled[col.name] = true;
            values[col.name] = text;
        } else {
            enabled[col.name] = false;
            values[col.name] = '';
        }
    });
    return { enabled, values };
}

/** Build default enabled/value maps from saved catalog.defaults. */
export function buildColumnDefaultsState(schemaColumns, savedDefaults = {}) {
    const enabled = {};
    const values = {};
    const raw = savedDefaults && typeof savedDefaults === 'object' ? savedDefaults : {};
    (schemaColumns || []).forEach((col) => {
        if (!isCatalogColumnMappable(col)) return;
        const text = raw[col.name] == null ? '' : String(raw[col.name]).trim();
        if (text) {
            enabled[col.name] = true;
            values[col.name] = text;
        } else {
            enabled[col.name] = false;
            values[col.name] = '';
        }
    });
    return { enabled, values };
}

export function getCatalogRequiredMappingColumnNames(catalogMeta) {
    if (!catalogMeta) return [];
    const skip = new Set(catalogMeta.non_mappable_targets || []);
    skip.add('organization_id');
    const seen = new Set();
    const out = [];
    for (const col of [
        ...(catalogMeta.required_columns || []),
        ...(catalogMeta.required_mapping_columns || []),
    ]) {
        const name = String(col || '').trim();
        if (!name || skip.has(name) || seen.has(name)) continue;
        seen.add(name);
        out.push(name);
    }
    return out;
}
