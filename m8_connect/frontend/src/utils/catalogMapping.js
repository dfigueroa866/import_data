/** Shared rules for catalog/history column mapping in Step 2. */

import { AUDIT_COLUMN_NAMES } from './catalogColumnRules';
const normalizeHeader = (s) =>
    String(s || '')
        .toLowerCase()
        .replace(/[^a-z0-9]/g, '');

export { normalizeHeader };
function isCatalogLoad({ loadMode, catalogMeta } = {}) {
    return loadMode === 'catalog' && Boolean(catalogMeta?.name);
}

/** True when the catalog definition explicitly defines this list (even if empty). */
function catalogDefinesList(catalogMeta, key) {
    return Boolean(catalogMeta && Array.isArray(catalogMeta[key]));
}

/**
 * Required destination columns from catalog config (union of required_* lists).
 * Excludes organization_id and non_mappable_targets.
 */
export function getCatalogConfigRequiredTargets(catalogMeta) {
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

    return false;
}

export function getCatalogRequiredMappingColumns(targetTable, catalogMeta, loadMode) {
    if (isCatalogLoad({ loadMode, catalogMeta })) {
        return getCatalogConfigRequiredTargets(catalogMeta);
    }
    if (catalogDefinesList(catalogMeta, 'required_mapping_columns')) {
        return catalogMeta.required_mapping_columns;
    }
    if (catalogMeta?.required_mapping_columns?.length) {
        return catalogMeta.required_mapping_columns;
    }
    return [];
}

/** Required destination columns for catalog mapping validation (step 2). */
export function getCatalogRequiredTargetColumns(targetTable, catalogMeta, loadMode) {
    if (isCatalogLoad({ loadMode, catalogMeta })) {
        return getCatalogConfigRequiredTargets(catalogMeta);
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
    return [...names].filter((n) => n !== 'organization_id');
}

export function isRequiredMappingTargetColumn(col, { targetTable, catalogMeta, loadMode } = {}) {
    if (!col?.name || isSystemManagedTargetColumn(col, { targetTable, catalogMeta, loadMode })) {
        return false;
    }

    if (isCatalogLoad({ loadMode, catalogMeta })) {
        return getCatalogConfigRequiredTargets(catalogMeta).includes(col.name);
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
    const col = productionColumns.find((c) => c.name === targetName);
    if (!col) return false;
    return isSystemManagedTargetColumn(col, { targetTable, catalogMeta, loadMode });
}
