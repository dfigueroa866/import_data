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

function isHistoryLoad({ loadMode, catalogMeta } = {}) {
    return loadMode === 'history' && Boolean(catalogMeta?.name);
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

/** Non-empty config defaults for mappable columns (excludes system targets). */
export function getCatalogColumnDefaults(catalogMeta) {
    if (!catalogMeta || typeof catalogMeta.defaults !== 'object' || !catalogMeta.defaults) {
        return {};
    }
    const skip = new Set(catalogMeta.non_mappable_targets || []);
    skip.add('organization_id');
    const out = {};
    for (const [key, value] of Object.entries(catalogMeta.defaults)) {
        const name = String(key || '').trim();
        if (!name || skip.has(name)) continue;
        const text = value == null ? '' : String(value).trim();
        if (!text) continue;
        out[name] = text;
    }
    return out;
}

/**
 * Required targets that still need a wizard file/manual mapping
 * (config default covers the rest).
 */
export function getCatalogRequiredTargetsNeedingMapping(catalogMeta) {
    const defaults = getCatalogColumnDefaults(catalogMeta);
    return getCatalogConfigRequiredTargets(catalogMeta).filter((c) => !(c in defaults));
}

/**
 * Required destination columns from history config.
 * Excludes organization_id and non_mappable_targets.
 */
export function getHistoryConfigRequiredTargets(historyMeta) {
    if (!historyMeta) return [];
    const skip = new Set(historyMeta.non_mappable_targets || []);
    skip.add('organization_id');
    const seen = new Set();
    const out = [];
    for (const col of historyMeta.required_mapping_columns || []) {
        const name = String(col || '').trim();
        if (!name || skip.has(name) || seen.has(name)) continue;
        seen.add(name);
        out.push(name);
    }
    return out;
}

/** Non-empty config defaults for mappable history columns (excludes system targets). */
export function getHistoryColumnDefaults(historyMeta) {
    if (!historyMeta || typeof historyMeta.defaults !== 'object' || !historyMeta.defaults) {
        return {};
    }
    const skip = new Set(historyMeta.non_mappable_targets || []);
    skip.add('organization_id');
    const out = {};
    for (const [key, value] of Object.entries(historyMeta.defaults)) {
        const name = String(key || '').trim();
        if (!name || skip.has(name)) continue;
        const text = value == null ? '' : String(value).trim();
        if (!text) continue;
        out[name] = text;
    }
    return out;
}

/**
 * Required history targets that still need a wizard file/manual mapping
 * (config default covers the rest).
 */
export function getHistoryRequiredTargetsNeedingMapping(historyMeta) {
    const defaults = getHistoryColumnDefaults(historyMeta);
    return getHistoryConfigRequiredTargets(historyMeta).filter((c) => !(c in defaults));
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
        return getCatalogRequiredTargetsNeedingMapping(catalogMeta);
    }
    if (isHistoryLoad({ loadMode, catalogMeta })) {
        return getHistoryRequiredTargetsNeedingMapping(catalogMeta);
    }
    if (catalogDefinesList(catalogMeta, 'required_mapping_columns')) {
        return catalogMeta.required_mapping_columns;
    }
    if (catalogMeta?.required_mapping_columns?.length) {
        return catalogMeta.required_mapping_columns;
    }
    return [];
}

/** Required destination columns that still need mapping (step 2). */
export function getCatalogRequiredTargetColumns(targetTable, catalogMeta, loadMode) {
    if (isCatalogLoad({ loadMode, catalogMeta })) {
        return getCatalogRequiredTargetsNeedingMapping(catalogMeta);
    }
    if (isHistoryLoad({ loadMode, catalogMeta })) {
        return getHistoryRequiredTargetsNeedingMapping(catalogMeta);
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
        return getCatalogRequiredTargetsNeedingMapping(catalogMeta).includes(col.name);
    }

    if (isHistoryLoad({ loadMode, catalogMeta })) {
        return getHistoryRequiredTargetsNeedingMapping(catalogMeta).includes(col.name);
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

/**
 * Column keys for catalog Step 3 preview table (visual only).
 * Shows mapped targets present in the sample rows, plus organization_id.
 * Hides batch bookkeeping columns (names starting with '_').
 */
export function getCatalogPreviewColumnKeys(
    rows,
    columnMappings = {},
    columnToggles = {},
) {
    if (!rows?.length) return [];
    const rowKeys = Object.keys(rows[0] || {});
    const rowKeySet = new Set(rowKeys);

    const mapped = new Set();
    for (const [fileCol, config] of Object.entries(columnMappings || {})) {
        if (columnToggles?.[fileCol] === false) continue;
        const target = config?.target;
        if (!target || target === '__new__' || target === 'organization_id') continue;
        if (String(target).startsWith('_')) continue;
        if (rowKeySet.has(target)) mapped.add(target);
    }

    if (mapped.size === 0) {
        return rowKeys.filter((k) => !String(k).startsWith('_'));
    }

    return rowKeys.filter((k) => {
        if (String(k).startsWith('_')) return false;
        if (k === 'organization_id') return true;
        return mapped.has(k);
    });
}
