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

const HISTORY_AUTO_COLUMNS = new Set(['granularity', 'source', 'sales_channel']);

/**
 * @param {{ name: string, type?: string, is_primary_key?: boolean }} col
 * @returns {'organization'|'primary_key'|'audit'|'auto'|'mappable'}
 */
export function classifyHistoryColumn(col) {
    const name = col?.name || '';
    if (HISTORY_AUTO_COLUMNS.has(name)) return 'auto';
    return classifyCatalogColumn(col);
}

export function isHistoryColumnMappable(col) {
    return classifyHistoryColumn(col) === 'mappable';
}

/** Mappable columns with NOT NULL in DB default to required when no mapping config exists yet. */
export function isCatalogColumnRequiredBySchema(col) {
    return isCatalogColumnMappable(col) && col.nullable === false;
}

/** Build { [columnName]: boolean } from saved lists; NOT NULL defaults to true if unset. */
export function buildColumnRequiredMap(
    schemaColumns,
    requiredMappingColumns = [],
    optionalColumns = []
) {
    const requiredSet = new Set(requiredMappingColumns || []);
    const optionalSet = new Set(optionalColumns || []);
    const map = {};
    (schemaColumns || []).forEach((col) => {
        if (!isCatalogColumnMappable(col)) return;
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
 * Derive persisted catalog lists from admin column toggles + schema metadata.
 */
export function deriveCatalogMappingFields(schemaColumns, columnRequiredMap = {}) {
    const required_mapping_columns = [];
    const optional_columns = [];
    const non_mappable_targets = [];
    const ignored_file_headers = [];

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
    });

    return {
        required_mapping_columns,
        required_columns: [...required_mapping_columns],
        optional_columns,
        non_mappable_targets,
        ignored_file_headers,
    };
}

export function getCatalogRequiredMappingColumnNames(catalogMeta) {
    if (!catalogMeta) return [];
    if (Array.isArray(catalogMeta.required_mapping_columns)) {
        return catalogMeta.required_mapping_columns;
    }
    return [];
}
