import React, { useState, useEffect } from 'react';
import { getTableColumns } from '../../services/systemService';
import { saveColumnMapping } from '../../services/wizardService';
import { useAuth } from '../../context/AuthContext';
import { Button, LoadingSpinner, Alert, Select, inputMappedClasses } from '../ui';
import { cn } from '../../lib/utils';
import {
    isExcludedMappingTarget,
    isIgnoredFileHeader,
    isRequiredMappingTargetColumn,
    isSystemManagedTargetColumn,
    getCatalogRequiredTargetColumns,
    historyHasSkuMapping,
    normalizeHeader,
} from '../../utils/catalogMapping';
import { HISTORY_LOGICAL_COLUMN_DEFS, HISTORY_SALES_CHANNEL_VALUE, granularityFromProcessType, sourceFromFileName } from '../../constants/historyConfig';
import './Step2Mapping.css';

const ORG_MAPPING_KEY = '__fixed_organization_id__';
const GRANULARITY_MAPPING_KEY = '__fixed_granularity__';
const SOURCE_MAPPING_KEY = '__fixed_source__';
const SALES_CHANNEL_MAPPING_KEY = '__fixed_sales_channel__';

const Step2Mapping = ({ wizardData, updateWizardData, nextStep, prevStep }) => {
    const { user } = useAuth();
    const organizationId = user?.organization_id || wizardData.organizationId || '';
    const organizationName =
        user?.organization_name || wizardData.organizationName || '';

    const [productionColumns, setProductionColumns] = useState([]);
    const [columnMappings, setColumnMappings] = useState({});
    const [columnToggles, setColumnToggles] = useState({});
    const [loading, setLoading] = useState(false);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState('');

    const historyMeta =
        wizardData.loadMode === 'history' ? wizardData.historyTableMeta : null;
    const mappingCtx = {
        targetTable:
            wizardData.selectedTable ||
            wizardData.catalogTable ||
            wizardData.catalogTableMeta?.name ||
            historyMeta?.name,
        catalogMeta: wizardData.catalogTableMeta || historyMeta,
        loadMode: wizardData.loadMode || 'history',
    };

    const ignoreFileHeader = (fileCol) =>
        isIgnoredFileHeader(fileCol, mappingCtx);

    useEffect(() => {
        if (wizardData.selectedSchema && wizardData.selectedTable) {
            loadProductionColumns();
        }
    }, []);

    const loadProductionColumns = async () => {
        try {
            setLoading(true);
            const data = await getTableColumns(wizardData.selectedSchema, wizardData.selectedTable);
            let cols = data.columns || [];
            if (wizardData.loadMode === 'history') {
                const existing = new Set(cols.map((c) => c.name));
                if (!existing.has('sku')) {
                    HISTORY_LOGICAL_COLUMN_DEFS.forEach((logical) => {
                        if (!existing.has(logical.name)) {
                            cols = [...cols, logical];
                        }
                    });
                }
            }
            setProductionColumns(cols);
            autoMapColumns(wizardData.fileHeaders, cols);
        } catch (err) {
            setError('Failed to load production table columns');
            console.error(err);
        } finally {
            setLoading(false);
        }
    };

    const isOrganizationFileColumn = (fileCol) =>
        String(fileCol || '').toLowerCase() === 'organization_id';

    const autoMapColumns = (fileHeaders, prodColumns) => {
        const mappings = {};
        const toggles = {};

        fileHeaders.forEach((fileCol) => {
            if (isOrganizationFileColumn(fileCol) || ignoreFileHeader(fileCol)) {
                toggles[fileCol] = false;
                mappings[fileCol] = {
                    target: '',
                    auto_mapped: false,
                };
                return;
            }

            toggles[fileCol] = true;

            let matchName = null;
            const prodNames = new Set(prodColumns.map((c) => c.name));
            const fileNorm = normalizeHeader(fileCol);
            const fileLower = String(fileCol).toLowerCase();

            const exact = prodColumns.find(
                (prodCol) => prodCol.name.toLowerCase() === fileLower
            );
            if (
                exact &&
                exact.name !== 'organization_id' &&
                !isExcludedMappingTarget(exact.name, prodColumns, mappingCtx)
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
                                    fileLower === String(a).toLowerCase() ||
                                    normalizeHeader(a) === fileNorm
                            )
                        ) {
                            matchName = target;
                            break;
                        }
                    }
                }
            }

            if (matchName) {
                mappings[fileCol] = {
                    target: matchName,
                    auto_mapped: true,
                };
            } else {
                mappings[fileCol] = {
                    target: '',
                    auto_mapped: false,
                };
            }
        });

        setColumnMappings(mappings);
        setColumnToggles(toggles);
    };

    const handleToggleChange = (fileCol, value) => {
        setColumnToggles(prev => ({
            ...prev,
            [fileCol]: value
        }));
    };

    const handleMappingChange = (fileCol, field, value) => {
        setColumnMappings(prev => ({
            ...prev,
            [fileCol]: {
                ...prev[fileCol],
                [field]: value,
                auto_mapped: field === 'target' ? false : prev[fileCol]?.auto_mapped
            }
        }));
    };

    const getVisibleFileHeaders = () =>
        (wizardData.fileHeaders || []).filter(
            (fileCol) =>
                !isOrganizationFileColumn(fileCol) && !ignoreFileHeader(fileCol)
        );

    const getMappedFileHeaders = () =>
        getVisibleFileHeaders().filter((fileCol) => {
            if (columnToggles[fileCol] === false) {
                return false;
            }
            const target = columnMappings[fileCol]?.target;
            return (
                target &&
                target !== 'organization_id' &&
                !isExcludedMappingTarget(target, productionColumns, mappingCtx)
            );
        });

    const tableHasOrganizationId = productionColumns.some(
        (col) => col.name === 'organization_id'
    );

    const appendFixedOrganizationMapping = (mappings, toggles) => {
        if (!organizationId || !tableHasOrganizationId) return { mappings, toggles };
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
            default_value: organizationId,
            auto_mapped: false,
            is_fixed: true,
        };
        nextToggles[ORG_MAPPING_KEY] = true;
        return { mappings: nextMappings, toggles: nextToggles };
    };

    const appendFixedHistoryAutoMappings = (mappings, toggles) => {
        if (wizardData.loadMode !== 'history') {
            return { mappings, toggles };
        }

        const nextMappings = { ...mappings };
        const nextToggles = { ...toggles };
        const autoTargets = ['granularity', 'source', 'sales_channel'];

        Object.keys(nextMappings).forEach((fileCol) => {
            if (autoTargets.includes(nextMappings[fileCol]?.target)) {
                delete nextMappings[fileCol];
                nextToggles[fileCol] = false;
            }
        });

        const granularity = granularityFromProcessType(wizardData.processType);
        if (!granularity) {
            return { mappings: nextMappings, toggles: nextToggles, error: 'Falta el tipo de proceso (Weekly/Monthly) del paso 1.' };
        }

        const sourceExt = sourceFromFileName(wizardData.fileName);
        nextMappings[GRANULARITY_MAPPING_KEY] = {
            target: 'granularity',
            default_value: granularity,
            auto_mapped: false,
            is_fixed: true,
        };
        nextToggles[GRANULARITY_MAPPING_KEY] = true;
        nextMappings[SOURCE_MAPPING_KEY] = {
            target: 'source',
            default_value: sourceExt,
            auto_mapped: false,
            is_fixed: true,
        };
        nextToggles[SOURCE_MAPPING_KEY] = true;
        nextMappings[SALES_CHANNEL_MAPPING_KEY] = {
            target: 'sales_channel',
            default_value: HISTORY_SALES_CHANNEL_VALUE,
            auto_mapped: false,
            is_fixed: true,
        };
        nextToggles[SALES_CHANNEL_MAPPING_KEY] = true;

        return { mappings: nextMappings, toggles: nextToggles };
    };

    const handleSubmit = async () => {
        try {
            setSaving(true);
            setError('');

            if (tableHasOrganizationId && !organizationId) {
                setError('No se encontró organization_id del usuario. Vuelve a iniciar sesión.');
                setSaving(false);
                return;
            }

            const catalogRequiredNames =
                wizardData.loadMode === 'catalog'
                    ? getCatalogRequiredTargetColumns(
                          mappingCtx.targetTable,
                          mappingCtx.catalogMeta,
                          mappingCtx.loadMode
                      )
                    : [];

            const historyRequiredNames =
                wizardData.loadMode === 'history'
                    ? mappingCtx.catalogMeta?.required_mapping_columns || []
                    : [];

            const requiredNames = [...catalogRequiredNames, ...historyRequiredNames];

            const requiredCols = productionColumns.filter(
                (col) =>
                    isRequiredMappingTargetColumn(col, mappingCtx) ||
                    requiredNames.includes(col.name)
            );

            requiredNames.forEach((colName) => {
                if (!requiredCols.some((c) => c.name === colName)) {
                    const fromProd = productionColumns.find((c) => c.name === colName);
                    if (fromProd) {
                        requiredCols.push(fromProd);
                    } else {
                        requiredCols.push({ name: colName, nullable: false, default: null });
                    }
                }
            });

            const missingCols = requiredCols.filter((reqCol) => {
                const mappedFromFile = getMappedFileHeaders().some(
                    (fileCol) => columnMappings[fileCol]?.target === reqCol.name
                );
                return !mappedFromFile;
            });

            if (missingCols.length > 0) {
                setError(
                    `Debes mapear las columnas obligatorias de destino: ${missingCols.map((c) => c.name).join(', ')}`
                );
                setSaving(false);
                return;
            }

            if (wizardData.loadMode === 'history') {
                const mappedTargets = getMappedFileHeaders()
                    .filter((fc) => columnToggles[fc] !== false)
                    .map((fc) => columnMappings[fc]?.target)
                    .filter(Boolean);
                if (!historyHasSkuMapping(mappedTargets, mappingCtx.catalogMeta)) {
                    setError(
                        'Debes mapear el producto a sku o sku_code, y location_code'
                    );
                    setSaving(false);
                    return;
                }
            }

            const activeWithoutTarget = getVisibleFileHeaders().filter((fileCol) => {
                if (columnToggles[fileCol] === false) return false;
                const target = columnMappings[fileCol]?.target;
                return (
                    !target
                    || target === 'organization_id'
                    || target === 'granularity'
                    || target === 'source'
                    || target === 'sales_channel'
                );
            });
            if (activeWithoutTarget.length > 0) {
                setError(
                    `Asigna una columna de destino o desactiva estas columnas del archivo: ${activeWithoutTarget.join(', ')}`
                );
                setSaving(false);
                return;
            }

            const finalMappings = {};
            const finalToggles = {};

            getVisibleFileHeaders().forEach((fileCol) => {
                if (columnToggles[fileCol] === false) {
                    return;
                }
                const mapping = columnMappings[fileCol];
                if (
                    !mapping?.target ||
                    isExcludedMappingTarget(mapping.target, productionColumns, mappingCtx)
                ) {
                    return;
                }
                finalMappings[fileCol] = mapping;
                finalToggles[fileCol] = columnToggles[fileCol] !== false;
            });

            const withOrg = appendFixedOrganizationMapping(finalMappings, finalToggles);
            Object.assign(finalMappings, withOrg.mappings);
            Object.assign(finalToggles, withOrg.toggles);

            const withHistoryAuto = appendFixedHistoryAutoMappings(finalMappings, finalToggles);
            if (withHistoryAuto.error) {
                setError(withHistoryAuto.error);
                setSaving(false);
                return;
            }
            Object.assign(finalMappings, withHistoryAuto.mappings);
            Object.assign(finalToggles, withHistoryAuto.toggles);

            const catalogSlug =
                wizardData.loadMode === 'catalog'
                    ? wizardData.catalogTable ||
                      wizardData.catalogTableMeta?.name ||
                      wizardData.selectedTable
                    : null;
            const physicalTable =
                wizardData.catalogTableMeta?.target_table || wizardData.selectedTable;

            const mappingData = {
                target_schema: wizardData.selectedSchema,
                target_table:
                    wizardData.loadMode === 'catalog' ? catalogSlug : wizardData.selectedTable,
                column_mappings: finalMappings,
                column_toggles: finalToggles,
                ...(wizardData.loadMode === 'catalog' && physicalTable
                    ? { production_table: physicalTable }
                    : {}),
            };

            await saveColumnMapping(
                wizardData.batchId,
                mappingData,
                wizardData.loadMode === 'history' ? wizardData.processType : null,
                wizardData.loadMode || 'history'
            );

            updateWizardData({
                columnMappings: finalMappings,
                columnToggles: finalToggles,
                organizationId,
                organizationName,
                productionColumns,
            });

            nextStep();

        } catch (err) {
            setError(err.response?.data?.detail || 'Failed to save mappings');
            console.error(err);
        } finally {
            setSaving(false);
        }
    };

    const getMappedCount = () => {
        const fileMapped = getMappedFileHeaders().length;
        return fileMapped + (organizationId && tableHasOrganizationId ? 1 : 0);
    };

    const getSelectableTargetColumns = () => {
        return productionColumns
            .filter((col) => col?.name && !isSystemManagedTargetColumn(col, mappingCtx))
            .sort((a, b) => a.name.localeCompare(b.name, 'es'));
    };

    const selectableTargetColumns = getSelectableTargetColumns();

    if (loading) {
        return (
            <div className="step2-loading">
                <LoadingSpinner />
                <p>Loading production table columns...</p>
            </div>
        );
    }

    return (
        <div className="step2-mapping">
            <div className="mapping-container">
                <div className="mapping-section full-width">
                    <h3>Column Mapping</h3>

                    <div className="mappings-list">
                        <div className="mapping-header-row">
                            <div className="col-source">File Column</div>
                            <div className="col-arrow"></div>
                            <div className="col-target">Target Column</div>
                        </div>

                        {getVisibleFileHeaders().length === 0 && (
                            <div className="no-matches-hint">
                                No hay columnas del archivo para mapear.
                            </div>
                        )}

                        {getVisibleFileHeaders().map((fileCol, idx) => {
                            const isActive = columnToggles[fileCol];
                            const mapping = columnMappings[fileCol] || {};

                            return (
                                <div key={`file-${idx}`} className={`mapping-row ${isActive ? 'active-row' : 'inactive-row'}`}>
                                    <div className="mapping-source">
                                        <div className="toggle-wrapper">
                                            <label className="toggle-switch">
                                                <input
                                                    type="checkbox"
                                                    checked={isActive || false}
                                                    onChange={(e) => handleToggleChange(fileCol, e.target.checked)}
                                                />
                                                <span className="toggle-slider"></span>
                                            </label>
                                        </div>
                                        <span className={`source-name ${isActive ? 'text-highlight' : 'text-muted'}`}>
                                            {fileCol}
                                        </span>
                                        {mapping.auto_mapped && <span className="auto-badge">Auto</span>}
                                    </div>
                                    <div className="mapping-arrow">→</div>
                                    <div className="mapping-target">
                                        <Select
                                            value={mapping.target || ''}
                                            onChange={(e) => handleMappingChange(fileCol, 'target', e.target.value)}
                                            className={cn(mapping.target && inputMappedClasses)}
                                            disabled={!isActive}
                                        >
                                            <option value="">-- Ignore / Select --</option>
                                            {selectableTargetColumns.map(col => (
                                                <option key={col.name} value={col.name}>
                                                    {col.name} ({col.type})
                                                </option>
                                            ))}
                                        </Select>
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                </div>
            </div>

            {error && <Alert variant="error">{error}</Alert>}

            <div className="step-actions">
                <Button variant="secondary" onClick={prevStep}>
                    ← Back
                </Button>
                <Button
                    variant="primary"
                    onClick={handleSubmit}
                    disabled={saving || getMappedCount() === 0}
                >
                    {saving ? (
                        <>
                            <LoadingSpinner size="sm" />
                            Saving...
                        </>
                    ) : (
                        'Next: Preview Data →'
                    )}
                </Button>
            </div>
        </div>
    );
};

export default Step2Mapping;
