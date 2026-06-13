/** Shared rules for catalog/history column mapping in Step 2. */

import {
    AUDIT_COLUMN_NAMES,
    getCatalogRequiredMappingColumnNames,
} from './catalogColumnRules';

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

function isCatalogLoad({ loadMode, catalogMeta } = {}) {
    return loadMode === 'catalog' && Boolean(catalogMeta?.name);
}

/** True when the catalog definition explicitly defines this list (even if empty). */
function catalogDefinesList(catalogMeta, key) {
    return Boolean(catalogMeta && Array.isArray(catalogMeta[key]));
}

/**
 * @param {string} fileCol
 * @param {{ targetTable?: string, catalogMeta?: object, loadMode?: string }} [options]
 */
export function isIgnoredFileHeader(fileCol, { targetTable, catalogMeta, loadMode } = {}) {
    const lower = String(fileCol || '').toLowerCase();
    const norm = normalizeHeader(fileCol);

    if (isCatalogLoad({ loadMode, catalogMeta })) {
        for (const h of catalogMeta.ignored_file_headers || []) {
            const hNorm = normalizeHeader(h);
            if (lower === h.toLowerCase() || norm === hNorm) return true;
        }
        if (lower === 'organization_id' || norm === 'organizationid') return true;
        return false;
    }

    if (catalogDefinesList(catalogMeta, 'ignored_file_headers')) {
        for (const h of catalogMeta.ignored_file_headers) {
            const hNorm = normalizeHeader(h);
            if (lower === h.toLowerCase() || norm === hNorm) return true;
        }
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

export function isSystemManagedTargetColumn(col, { targetTable, catalogMeta, loadMode } = {}) {
    if (!col?.name) return false;

    if (isCatalogLoad({ loadMode, catalogMeta })) {
        if ((catalogMeta.non_mappable_targets || []).includes(col.name)) return true;
        if (col.name === 'organization_id') return true;
        return false;
    }

    if (catalogDefinesList(catalogMeta, 'non_mappable_targets')) {
        if (catalogMeta.non_mappable_targets.includes(col.name)) return true;
        if (col.name === 'organization_id') return true;
        if (col.name === 'granularity' || col.name === 'source' || col.name === 'sales_channel') return true;
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

export function getCatalogRequiredMappingColumns(targetTable, catalogMeta, loadMode) {
    if (isCatalogLoad({ loadMode, catalogMeta })) {
        return getCatalogRequiredMappingColumnNames(catalogMeta);
    }
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

/** Required destination columns for catalog mapping validation (step 2). */
export function getCatalogRequiredTargetColumns(targetTable, catalogMeta, loadMode) {
    if (isCatalogLoad({ loadMode, catalogMeta })) {
        return getCatalogRequiredMappingColumnNames(catalogMeta);
    }

    const names = new Set();
    if (catalogMeta?.required_columns?.length) {
        catalogMeta.required_columns.forEach((name) => names.add(name));
    }
    if (catalogDefinesList(catalogMeta, 'required_mapping_columns')) {
        catalogMeta.required_mapping_columns.forEach((name) => names.add(name));
    } else if (catalogMeta?.required_mapping_columns?.length) {
        catalogMeta.required_mapping_columns.forEach((name) => names.add(name));
    } else {
        getCatalogRequiredMappingColumns(targetTable, catalogMeta, loadMode).forEach((name) =>
            names.add(name)
        );
    }
    return [...names];
}

export function isRequiredMappingTargetColumn(col, { targetTable, catalogMeta, loadMode } = {}) {
    if (!col?.name || isSystemManagedTargetColumn(col, { targetTable, catalogMeta, loadMode })) {
        return false;
    }

    if (isCatalogLoad({ loadMode, catalogMeta })) {
        return getCatalogRequiredMappingColumnNames(catalogMeta).includes(col.name);
    }

    if (catalogDefinesList(catalogMeta, 'required_mapping_columns')) {
        return catalogMeta.required_mapping_columns.includes(col.name);
    }
    if (catalogMeta?.required_mapping_columns?.length) {
        return catalogMeta.required_mapping_columns.includes(col.name);
    }

    if (catalogMeta?.required_columns?.includes(col.name)) {
        return true;
    }

    if (getCatalogRequiredMappingColumns(targetTable, catalogMeta, loadMode).includes(col.name)) {
        return true;
    }

    return col.nullable === false;
}

export function historyHasSkuMapping(mappedTargets, catalogMeta) {
    const names = catalogMeta?.sku_mapping_targets || ['sku_code', 'sku', 'sku_id'];
    return mappedTargets.some((t) => names.includes(t));
}

export function isExcludedMappingTarget(
    targetName,
    productionColumns,
    { targetTable, catalogMeta, loadMode } = {}
) {
    if (!targetName) return true;
    if (isCatalogLoad({ loadMode, catalogMeta })) {
        if ((catalogMeta.non_mappable_targets || []).includes(targetName)) return true;
        if (targetName === 'organization_id') return true;
        return false;
    }
    if (catalogDefinesList(catalogMeta, 'non_mappable_targets')) {
        if (catalogMeta.non_mappable_targets.includes(targetName)) return true;
        if (targetName === 'organization_id') return true;
        if (targetName === 'granularity' || targetName === 'source' || targetName === 'sales_channel') return true;
        const col = productionColumns.find((c) => c.name === targetName);
        return col ? isSystemManagedTargetColumn(col, { targetTable, catalogMeta, loadMode }) : false;
    }
    if (catalogMeta?.non_mappable_targets?.includes(targetName)) return true;
    const col = productionColumns.find((c) => c.name === targetName);
    if (col && isSystemManagedTargetColumn(col, { targetTable, catalogMeta, loadMode })) return true;
    return AUDIT_COLUMN_NAMES.has(targetName);
}

export { normalizeHeader };
