/** Shared rules for catalog/history column mapping in Step 2. */

const AUDIT_COLUMN_NAMES = new Set(['created_at', 'updated_at', 'imported_at']);

const SKUS_PK_NAMES = new Set(['sku_id', 'id']);
const LOCATION_NON_MAPPABLE = new Set(['location_id', 'id']);

const IGNORED_FILE_HEADERS_BY_TABLE = {
    skus: new Set(['sku_id']),
    location: new Set(['location_id', 'organization_id']),
};

const normalizeHeader = (s) =>
    String(s || '')
        .toLowerCase()
        .replace(/[^a-z0-9]/g, '');

/** True when the catalog definition explicitly defines this list (even if empty). */
function catalogDefinesList(catalogMeta, key) {
    return Boolean(catalogMeta && Array.isArray(catalogMeta[key]));
}

/**
 * @param {string} fileCol
 * @param {{ targetTable?: string, catalogMeta?: object }} [options]
 */
export function isIgnoredFileHeader(fileCol, { targetTable, catalogMeta } = {}) {
    const lower = String(fileCol || '').toLowerCase();
    const norm = normalizeHeader(fileCol);

    if (catalogDefinesList(catalogMeta, 'ignored_file_headers')) {
        for (const h of catalogMeta.ignored_file_headers) {
            const hNorm = normalizeHeader(h);
            if (lower === h.toLowerCase() || norm === hNorm) return true;
        }
        // organization_id always comes from session in catalog loads
        if (lower === 'organization_id' || norm === 'organizationid') return true;
        return false;
    }

    if (AUDIT_COLUMN_NAMES.has(lower)) return true;
    if (norm === 'createdat' || norm === 'updatedat' || norm === 'importedat') {
        return true;
    }

    const table = String(targetTable || catalogMeta?.name || '').toLowerCase();
    const tableIgnored = IGNORED_FILE_HEADERS_BY_TABLE[table];
    if (tableIgnored?.has(lower)) return true;
    if (table === 'skus' && (lower === 'sku_id' || norm === 'skuid')) return true;
    if (table === 'location' && (lower === 'location_id' || norm === 'locationid')) {
        return true;
    }
    if (lower === 'organization_id' || norm === 'organizationid') return true;
    return false;
}

export function isSystemManagedTargetColumn(col, { targetTable, catalogMeta } = {}) {
    if (!col?.name) return false;

    if (catalogDefinesList(catalogMeta, 'non_mappable_targets')) {
        if (catalogMeta.non_mappable_targets.includes(col.name)) return true;
        // organization_id is injected automatically, never user-mapped
        if (col.name === 'organization_id') return true;
        return false;
    }

    if (catalogMeta?.non_mappable_targets?.includes(col.name)) {
        return true;
    }

    if (col.name === 'organization_id') return true;
    if (AUDIT_COLUMN_NAMES.has(col.name)) return true;

    const table = String(targetTable || catalogMeta?.name || '').toLowerCase();
    if (table === 'skus' && SKUS_PK_NAMES.has(col.name)) return true;
    if (table === 'location' && LOCATION_NON_MAPPABLE.has(col.name)) return true;

    const colType = String(col.type || '').toLowerCase();
    if (colType.includes('uuid')) {
        if (table === 'skus' && SKUS_PK_NAMES.has(col.name)) return true;
        if (table === 'location' && LOCATION_NON_MAPPABLE.has(col.name)) return true;
    }

    return false;
}

export function getCatalogRequiredMappingColumns(targetTable, catalogMeta) {
    if (catalogDefinesList(catalogMeta, 'required_mapping_columns')) {
        return catalogMeta.required_mapping_columns;
    }
    if (catalogMeta?.required_mapping_columns?.length) {
        return catalogMeta.required_mapping_columns;
    }
    const table = String(targetTable || '').toLowerCase();
    if (table === 'skus') return ['status'];
    return [];
}

/** Union of catalog `required_columns`, `required_mapping_columns`, and legacy fallbacks. */
export function getCatalogRequiredTargetColumns(targetTable, catalogMeta) {
    const names = new Set();

    if (catalogMeta?.required_columns?.length) {
        catalogMeta.required_columns.forEach((name) => names.add(name));
    }

    if (catalogDefinesList(catalogMeta, 'required_mapping_columns')) {
        catalogMeta.required_mapping_columns.forEach((name) => names.add(name));
    } else if (catalogMeta?.required_mapping_columns?.length) {
        catalogMeta.required_mapping_columns.forEach((name) => names.add(name));
    } else {
        getCatalogRequiredMappingColumns(targetTable, catalogMeta).forEach((name) =>
            names.add(name)
        );
    }

    return [...names];
}

export function isRequiredMappingTargetColumn(col, { targetTable, catalogMeta } = {}) {
    if (!col?.name || isSystemManagedTargetColumn(col, { targetTable, catalogMeta })) {
        return false;
    }

    // Si el catálogo define required_mapping_columns, solo esas exigen mapeo manual
    if (catalogDefinesList(catalogMeta, 'required_mapping_columns')) {
        return catalogMeta.required_mapping_columns.includes(col.name);
    }
    if (catalogMeta?.required_mapping_columns?.length) {
        return catalogMeta.required_mapping_columns.includes(col.name);
    }

    if (catalogMeta?.required_columns?.includes(col.name)) {
        return true;
    }

    if (getCatalogRequiredMappingColumns(targetTable, catalogMeta).includes(col.name)) {
        return true;
    }

    if (col.default) return false;
    return col.nullable === false;
}

/** Targets de producto válidos para carga de historia (al menos uno mapeado). */
export function historyHasSkuMapping(mappedTargets, catalogMeta) {
    const names = catalogMeta?.sku_mapping_targets || ['sku_code', 'sku', 'sku_id'];
    return mappedTargets.some((t) => names.includes(t));
}

export function isExcludedMappingTarget(targetName, productionColumns, { targetTable, catalogMeta } = {}) {
    if (!targetName) return true;
    if (catalogDefinesList(catalogMeta, 'non_mappable_targets')) {
        if (catalogMeta.non_mappable_targets.includes(targetName)) return true;
        if (targetName === 'organization_id') return true;
        const col = productionColumns.find((c) => c.name === targetName);
        return col ? isSystemManagedTargetColumn(col, { targetTable, catalogMeta }) : false;
    }
    if (catalogMeta?.non_mappable_targets?.includes(targetName)) return true;
    const col = productionColumns.find((c) => c.name === targetName);
    if (col && isSystemManagedTargetColumn(col, { targetTable, catalogMeta })) return true;
    return AUDIT_COLUMN_NAMES.has(targetName);
}

export { normalizeHeader };
