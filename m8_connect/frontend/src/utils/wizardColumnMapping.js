import {
    isExcludedMappingTarget,
    isIgnoredFileHeader,
    normalizeHeader,
} from './catalogMapping';
import {
    HISTORY_LOGICAL_COLUMN_DEFS,
    HISTORY_SALES_CHANNEL_VALUE,
    granularityFromProcessType,
    sourceFromFileName,
} from '../constants/historyConfig';

export const ORG_MAPPING_KEY = '__fixed_organization_id__';
export const GRANULARITY_MAPPING_KEY = '__fixed_granularity__';
export const SOURCE_MAPPING_KEY = '__fixed_source__';
export const SALES_CHANNEL_MAPPING_KEY = '__fixed_sales_channel__';
export const MANUAL_MAPPING_PREFIX = '__manual__';

/**
 * Columnas virtuales fijas (historia):
 * | Clave                      | Target           | Fuente                          |
 * | __fixed_organization_id__  | organization_id  | sesión / login                  |
 * | __fixed_granularity__      | granularity      | processType (paso 1)            |
 * | __fixed_source__           | source           | source_extension (archivo)    |
 * | __fixed_sales_channel__    | sales_channel    | default SELL_IN                 |
 */
export const HISTORY_FIXED_VIRTUAL_COLUMNS = [
    { key: ORG_MAPPING_KEY, target: 'organization_id', source: 'from_organization_id' },
    { key: GRANULARITY_MAPPING_KEY, target: 'granularity', source: 'from_process_type' },
    { key: SOURCE_MAPPING_KEY, target: 'source', source: 'from_source_file' },
    { key: SALES_CHANNEL_MAPPING_KEY, target: 'sales_channel', source: 'default_value' },
];

export const isManualMappingKey = (key) =>
    String(key || '').startsWith(MANUAL_MAPPING_PREFIX);

export const isSystemVirtualMappingKey = (key) =>
    key === ORG_MAPPING_KEY
    || key === GRANULARITY_MAPPING_KEY
    || key === SOURCE_MAPPING_KEY
    || key === SALES_CHANNEL_MAPPING_KEY;

/** Columnas fijas cuyo valor viene del contexto (login / paso 1), no de default_value en mapeo. */
export const isMetadataDrivenFixedMappingKey = (key) =>
    key === ORG_MAPPING_KEY
    || key === GRANULARITY_MAPPING_KEY
    || key === SOURCE_MAPPING_KEY;

export const createManualMappingKey = () =>
    `${MANUAL_MAPPING_PREFIX}${Date.now()}_${Math.random().toString(36).slice(2, 9)}__`;

export const getManualMappingEntries = (columnMappings) =>
    Object.entries(columnMappings || {}).filter(([key]) => isManualMappingKey(key));

export const isManualMappingComplete = (mapping) =>
    Boolean(mapping?.target) && String(mapping?.default_value ?? '').trim() !== '';

export const isOrganizationFileColumn = (fileCol) =>
    String(fileCol || '').toLowerCase() === 'organization_id';

export const buildMappingContext = (wizardData) => {
    const historyMeta =
        wizardData.loadMode === 'history' ? wizardData.historyTableMeta : null;
    return {
        targetTable:
            wizardData.selectedTable ||
            wizardData.catalogTable ||
            wizardData.catalogTableMeta?.name ||
            historyMeta?.name,
        catalogMeta: wizardData.catalogTableMeta || historyMeta,
        loadMode: wizardData.loadMode || 'history',
    };
};

export const getVisibleFileHeaders = (fileHeaders, mappingCtx) =>
    (fileHeaders || []).filter(
        (fileCol) =>
            !isOrganizationFileColumn(fileCol)
            && !isIgnoredFileHeader(fileCol, mappingCtx),
    );

export const buildAutoColumnMappings = (fileHeaders, prodColumns, mappingCtx) => {
    const mappings = {};
    const toggles = {};

    (fileHeaders || []).forEach((fileCol) => {
        if (isOrganizationFileColumn(fileCol) || isIgnoredFileHeader(fileCol, mappingCtx)) {
            toggles[fileCol] = false;
            mappings[fileCol] = { target: '', auto_mapped: false };
            return;
        }

        toggles[fileCol] = true;

        let matchName = null;
        const prodNames = new Set(prodColumns.map((c) => c.name));
        const fileNorm = normalizeHeader(fileCol);
        const fileLower = String(fileCol).toLowerCase();

        const exact = prodColumns.find(
            (prodCol) => prodCol.name.toLowerCase() === fileLower,
        );
        if (
            exact
            && exact.name !== 'organization_id'
            && !isExcludedMappingTarget(exact.name, prodColumns, mappingCtx)
        ) {
            matchName = exact.name;
        }

        if (!matchName) {
            const aliases = mappingCtx.catalogMeta?.column_aliases;
            if (aliases && Object.keys(aliases).length > 0) {
                for (const [target, aliasList] of Object.entries(aliases)) {
                    if (!prodNames.has(target)) continue;
                    if (isExcludedMappingTarget(target, prodColumns, mappingCtx)) {
                        continue;
                    }
                    const candidates = [target, ...(aliasList || [])];
                    if (
                        candidates.some(
                            (a) =>
                                fileLower === String(a).toLowerCase()
                                || normalizeHeader(a) === fileNorm,
                        )
                    ) {
                        matchName = target;
                        break;
                    }
                }
            }
        }

        mappings[fileCol] = matchName
            ? { target: matchName, auto_mapped: true }
            : { target: '', auto_mapped: false };
    });

    return { mappings, toggles };
};

export const appendFixedOrganizationMapping = (
    mappings,
    toggles,
    { organizationId, tableHasOrganizationId },
) => {
    if (!organizationId || !tableHasOrganizationId) {
        return { mappings, toggles };
    }
    const nextMappings = { ...mappings };
    const nextToggles = { ...toggles };
    Object.keys(nextMappings).forEach((fileCol) => {
        if (nextMappings[fileCol]?.target === 'organization_id') {
            delete nextMappings[fileCol];
            nextToggles[fileCol] = false;
        }
    });
    nextMappings[ORG_MAPPING_KEY] = {
        target: 'organization_id',
        auto_mapped: false,
        is_fixed: true,
        from_organization_id: true,
    };
    nextToggles[ORG_MAPPING_KEY] = true;
    return { mappings: nextMappings, toggles: nextToggles };
};

export const appendFixedHistoryAutoMappings = (
    mappings,
    toggles,
    wizardData,
) => {
    if (wizardData.loadMode !== 'history') {
        return { mappings, toggles };
    }

    const nextMappings = { ...mappings };
    const nextToggles = { ...toggles };
    const autoTargets = [
        'granularity',
        'source',
        'sales_channel',
        'iso_year',
        'iso_week',
        'stockout_flag',
        'markdown_pct',
        'promo_flag',
    ];

    Object.keys(nextMappings).forEach((fileCol) => {
        if (autoTargets.includes(nextMappings[fileCol]?.target)) {
            delete nextMappings[fileCol];
            nextToggles[fileCol] = false;
        }
    });

    const processTypes = wizardData.historyTableMeta?.process_types;
    const granularity = granularityFromProcessType(wizardData.processType, processTypes);
    if (!wizardData.processType || !granularity) {
        return {
            mappings: nextMappings,
            toggles: nextToggles,
            error: 'Falta el tipo de proceso (granularidad) del paso 1.',
        };
    }

    const sourceExt = sourceFromFileName(wizardData.fileName);
    if (!sourceExt || sourceExt === 'unknown') {
        return {
            mappings: nextMappings,
            toggles: nextToggles,
            error: 'No se pudo determinar source desde el archivo original (extensión).',
        };
    }

    nextMappings[GRANULARITY_MAPPING_KEY] = {
        target: 'granularity',
        auto_mapped: false,
        is_fixed: true,
        from_process_type: true,
    };
    nextToggles[GRANULARITY_MAPPING_KEY] = true;
    nextMappings[SOURCE_MAPPING_KEY] = {
        target: 'source',
        auto_mapped: false,
        is_fixed: true,
        from_source_file: true,
    };
    nextToggles[SOURCE_MAPPING_KEY] = true;
    const salesChannelDefault =
        wizardData.historyTableMeta?.sales_channel_default || HISTORY_SALES_CHANNEL_VALUE;
    nextMappings[SALES_CHANNEL_MAPPING_KEY] = {
        target: 'sales_channel',
        default_value: salesChannelDefault,
        auto_mapped: false,
        is_fixed: true,
    };
    nextToggles[SALES_CHANNEL_MAPPING_KEY] = true;

    return { mappings: nextMappings, toggles: nextToggles };
};

export const mergeHistoryProductionColumns = (columns) => {
    let cols = columns || [];
    const existing = new Set(cols.map((c) => c.name));
    if (!existing.has('sku')) {
        HISTORY_LOGICAL_COLUMN_DEFS.forEach((logical) => {
            if (!existing.has(logical.name)) {
                cols = [...cols, logical];
            }
        });
    }
    return cols;
};

export const mappingsFingerprint = (mappings, toggles) =>
    JSON.stringify({ mappings, toggles });

export const buildFinalMappingsPayload = ({
    fileHeaders,
    columnMappings,
    columnToggles,
    productionColumns,
    mappingCtx,
    wizardData,
    organizationId,
}) => {
    const visibleHeaders = getVisibleFileHeaders(fileHeaders, mappingCtx);
    const finalMappings = {};
    const finalToggles = {};

    visibleHeaders.forEach((fileCol) => {
        if (columnToggles[fileCol] === false) {
            return;
        }
        const mapping = columnMappings[fileCol];
        if (
            !mapping?.target
            || isExcludedMappingTarget(mapping.target, productionColumns, mappingCtx)
        ) {
            return;
        }
        finalMappings[fileCol] = mapping;
        finalToggles[fileCol] = columnToggles[fileCol] !== false;
    });

    const tableHasOrganizationId = productionColumns.some(
        (col) => col.name === 'organization_id',
    );

    const withOrg = appendFixedOrganizationMapping(finalMappings, finalToggles, {
        organizationId,
        tableHasOrganizationId,
    });
    Object.assign(finalMappings, withOrg.mappings);
    Object.assign(finalToggles, withOrg.toggles);

    const withHistoryAuto = appendFixedHistoryAutoMappings(
        finalMappings,
        finalToggles,
        wizardData,
    );
    if (withHistoryAuto.error) {
        return { error: withHistoryAuto.error };
    }
    Object.assign(finalMappings, withHistoryAuto.mappings);
    Object.assign(finalToggles, withHistoryAuto.toggles);

    getManualMappingEntries(columnMappings).forEach(([manualKey, mapping]) => {
        if (columnToggles[manualKey] === false) {
            return;
        }
        if (!isManualMappingComplete(mapping)) {
            return;
        }
        if (isExcludedMappingTarget(mapping.target, productionColumns, mappingCtx)) {
            return;
        }
        finalMappings[manualKey] = {
            ...mapping,
            is_manual: true,
            auto_mapped: false,
        };
        finalToggles[manualKey] = true;
    });

    return { mappings: finalMappings, toggles: finalToggles };
};
