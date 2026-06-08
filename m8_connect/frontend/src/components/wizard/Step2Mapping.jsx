import React, { useState, useEffect } from 'react';
import { getTableColumns } from '../../services/systemService';
import { saveColumnMapping } from '../../services/wizardService';
import { useAuth } from '../../context/AuthContext';
import Button from '../Button';
import LoadingSpinner from '../LoadingSpinner';
import {
    isExcludedMappingTarget,
    isIgnoredFileHeader,
    isRequiredMappingTargetColumn,
    isSystemManagedTargetColumn,
    getCatalogRequiredTargetColumns,
    historyHasSkuMapping,
    normalizeHeader,
} from '../../utils/catalogMapping';
import { HISTORY_LOGICAL_COLUMN_DEFS } from '../../constants/historyConfig';
import './Step2Mapping.css';

const ORG_MAPPING_KEY = '__fixed_organization_id__';

const Step2Mapping = ({ wizardData, updateWizardData, nextStep, prevStep }) => {
    const { user } = useAuth();
    const organizationId = user?.organization_id || wizardData.organizationId || '';
    const organizationName =
        user?.organization_name || wizardData.organizationName || '';

    const [productionColumns, setProductionColumns] = useState([]);
    const [columnMappings, setColumnMappings] = useState({});
    const [columnToggles, setColumnToggles] = useState({});
    const [showProductionColumns, setShowProductionColumns] = useState(false);
    const [customColumns, setCustomColumns] = useState(wizardData.customColumns || []);
    const [loading, setLoading] = useState(false);
    const [saving, setSaving] = useState(false);

    // Sync custom columns to wizardData on unmount/next? No, better keep local state sync or just use wizardData directly if we passed updateWizardData.
    // Let's rely on local state and update on submit.

    const addNewColumn = () => {
        setCustomColumns([...customColumns, { name: '', target: '', defaultValue: '' }]);
    };

    const removeCustomColumn = (index) => {
        const newCols = [...customColumns];
        newCols.splice(index, 1);
        setCustomColumns(newCols);
    };

    const handleCustomColumnChange = (index, field, value) => {
        const newCols = [...customColumns];
        newCols[index] = { ...newCols[index], [field]: value };
        setCustomColumns(newCols);
    };
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
    };

    const ignoreFileHeader = (fileCol) =>
        isIgnoredFileHeader(fileCol, mappingCtx);

    // Load production table columns on mount
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
                // sku_code solo si la tabla no tiene columna «sku»
                if (!existing.has('sku')) {
                    HISTORY_LOGICAL_COLUMN_DEFS.forEach((logical) => {
                        if (!existing.has(logical.name)) {
                            cols = [...cols, logical];
                        }
                    });
                }
            }
            setProductionColumns(cols);

            // Auto-map columns
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
                    default_value: '',
                    auto_mapped: false,
                };
                return;
            }

            toggles[fileCol] = true;

            let matchName = null;
            const prodNames = new Set(prodColumns.map((c) => c.name));
            const fileNorm = normalizeHeader(fileCol);
            const fileLower = String(fileCol).toLowerCase();

            // 1) Coincidencia exacta con columna destino (prioridad sobre alias)
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

            // 2) Alias solo hacia columnas que existen en el destino (evita sku → sku_code cuando hay columna sku)
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
                    default_value: '',
                    auto_mapped: true,
                };
            } else {
                mappings[fileCol] = {
                    target: '',
                    default_value: '',
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
                          mappingCtx.catalogMeta
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

            // Ensure required targets appear even if schema metadata is incomplete
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

            // Validar que todas las columnas custom tengan nombre, destino y un valor fijo
            const invalidCustomCols = customColumns.filter(
                (c) =>
                    !c.name?.trim() ||
                    !c.target ||
                    !c.defaultValue?.trim()
            );

            if (invalidCustomCols.length > 0) {
                setError(
                    'Todas las columnas personalizadas (Custom) deben tener un nombre de origen, una columna de destino y un valor fijo asignado.'
                );
                setSaving(false);
                return;
            }

            const missingCols = requiredCols.filter((reqCol) => {
                const mappedFromFile = getMappedFileHeaders().some(
                    (fileCol) => columnMappings[fileCol]?.target === reqCol.name
                );
                const mappedFromCustom = customColumns.some(
                    (c) =>
                        c.target === reqCol.name &&
                        !isExcludedMappingTarget(c.target, productionColumns, mappingCtx)
                );
                return !mappedFromFile && !mappedFromCustom;
            });

            if (missingCols.length > 0) {
                setError(
                    `Debes mapear las columnas obligatorias de destino: ${missingCols.map((c) => c.name).join(', ')}`
                );
                setSaving(false);
                return;
            }

            if (wizardData.loadMode === 'history') {
                const mappedTargets = [
                    ...getMappedFileHeaders()
                        .filter((fc) => columnToggles[fc] !== false)
                        .map((fc) => columnMappings[fc]?.target)
                        .filter(Boolean),
                    ...customColumns.map((c) => c.target).filter(Boolean),
                ];
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
                return !target || target === 'organization_id';
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

            customColumns.forEach((c, idx) => {
                if (
                    c.target &&
                    c.target !== 'organization_id' &&
                    !isExcludedMappingTarget(c.target, productionColumns, mappingCtx)
                ) {
                    const customKey = `__custom_${idx}__${c.name || 'fixed'}`;
                    finalMappings[customKey] = {
                        target: c.target,
                        default_value: c.defaultValue || '',
                        auto_mapped: false,
                        is_custom: true
                    };
                    finalToggles[customKey] = true;
                }
            });

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

            // Save to backend
            await saveColumnMapping(
                wizardData.batchId,
                mappingData,
                wizardData.loadMode === 'history' ? wizardData.processType : null,
                wizardData.loadMode || 'history'
            );

            // Update wizard data
            updateWizardData({
                columnMappings: finalMappings,
                columnToggles: finalToggles,
                organizationId,
                organizationName,
                productionColumns,
                customColumns // Keep for UI persistence
            });

            // Move to next step
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
        const customMapped = customColumns.filter(
            (c) =>
                c.target &&
                c.target !== 'organization_id' &&
                !isExcludedMappingTarget(c.target, productionColumns, mappingCtx)
        ).length;
        return fileMapped + customMapped + (organizationId && tableHasOrganizationId ? 1 : 0);
    };

    const getActiveColumnsCount = () => {
        return getMappedCount();
    };

    const getSelectableTargetColumns = () => {
        return productionColumns
            .filter((col) => col?.name && !isSystemManagedTargetColumn(col, mappingCtx))
            .sort((a, b) => a.name.localeCompare(b.name, 'es'));
    };

    const getAutoFilledTargetColumns = () => {
        const autoNames = new Set(
            mappingCtx.catalogMeta?.non_mappable_targets || []
        );
        autoNames.delete('id');
        autoNames.delete('organization_id');
        return productionColumns.filter((col) => col?.name && autoNames.has(col.name));
    };

    const selectableTargetColumns = getSelectableTargetColumns();
    const autoFilledTargetColumns = getAutoFilledTargetColumns();

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
            <h2>Step 2: Map Columns</h2>
            <p className="step-description">
                {wizardData.loadMode === 'catalog'
                    ? 'Solo se auto-mapean columnas cuyo nombre en el Excel coincide exactamente con la columna de la tabla. Si el nombre es distinto (ej. país vs country), asígnalo manualmente en el desplegable.'
                    : wizardData.loadMode === 'history'
                      ? 'Mapea hacia public.sales_history. Obligatorios: location_code, period_start, quantity, pieces y producto (sku / sku_code). granularity, source y sales_channel (SELL_IN) se asignan automáticamente.'
                      : 'Map your file columns to production table columns. Toggled columns will be included in the import.'}
            </p>

            {organizationId && tableHasOrganizationId && (
                <div className="org-fixed-banner">
                    <span className="org-fixed-label">Organización</span>
                    <span className="org-fixed-value">
                        {organizationName || 'Organización asignada'}
                    </span>
                    <span className="org-fixed-hint">
                        Se aplicará automáticamente a todas las filas (no editable).
                    </span>
                </div>
            )}

            {wizardData.loadMode === 'history' && autoFilledTargetColumns.length > 0 && (
                <div className="org-fixed-banner history-auto-fields-banner">
                    <span className="org-fixed-label">Campos automáticos</span>
                    <span className="org-fixed-value">
                        {autoFilledTargetColumns.map((c) => c.name).join(', ')}
                    </span>
                    <span className="org-fixed-hint">
                        granularity según {wizardData.processType || 'Weekly/Monthly'}; source según
                        extensión del archivo ({wizardData.fileName?.split('.').pop() || '—'});
                        sales_channel = SELL_IN.
                        Aparecerán en la vista previa sin mapear.
                    </span>
                </div>
            )}

            <div className="mapping-stats">
                <div className="stat">
                    <span className="stat-value">{getActiveColumnsCount()}</span>
                    <span className="stat-label">Active Columns</span>
                </div>
                <div className="stat">
                    <span className="stat-value">{getMappedCount()}</span>
                    <span className="stat-label">Mapped</span>
                </div>
                <div className="stat">
                    <span className="stat-value">{selectableTargetColumns.length}</span>
                    <span className="stat-label">Target Columns</span>
                </div>
            </div>

            {wizardData.loadMode === 'history' && (
                <p className="mapping-target-hint">
                    {selectableTargetColumns.length} columnas disponibles en{' '}
                    <strong>public.sales_history</strong> (todas las de la tabla excepto id y
                    organization_id).
                </p>
            )}

            <div className="mapping-container">
                {/* File Columns (Left) */}
                {/* Mapping (Center - Expanded) */}
                <div className="mapping-section full-width">
                    <h3>Column Mapping</h3>

                    <div className="mapping-actions">
                        <Button variant="secondary" size="small" onClick={() => setShowProductionColumns(!showProductionColumns)}>
                            {showProductionColumns ? 'Hide Target Columns' : 'Show Target Columns'}
                        </Button>
                    </div>

                    <div className="mappings-list">
                        {/* Headers */}
                        <div className="mapping-header-row">
                            <div className="col-source">File Column</div>
                            <div className="col-arrow"></div>
                            <div className="col-target">Target Column</div>
                            <div className="col-default">Default Value</div>
                            <div className="col-action"></div>
                        </div>

                        {getVisibleFileHeaders().length === 0 && (
                            <div className="no-matches-hint">
                                No hay columnas del archivo para mapear.
                                Usa &quot;Agregar columna&quot; para valores fijos.
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
                                        <select
                                            value={mapping.target || ''}
                                            onChange={(e) => handleMappingChange(fileCol, 'target', e.target.value)}
                                            className={mapping.target ? 'mapped-select' : ''}
                                            disabled={!isActive}
                                        >
                                            <option value="">-- Ignore / Select --</option>
                                            {selectableTargetColumns.map(col => (
                                                <option key={col.name} value={col.name}>
                                                    {col.name} ({col.type})
                                                </option>
                                            ))}
                                        </select>
                                    </div>
                                    <div className="mapping-default">
                                        <input
                                            type="text"
                                            placeholder="Default value"
                                            value={mapping.default_value || ''}
                                            onChange={(e) => handleMappingChange(fileCol, 'default_value', e.target.value)}
                                            disabled={!isActive}
                                        />
                                    </div>
                                    <div className="mapping-action">
                                        {/* Action column for custom rows only typically, but we need structure */}
                                    </div>
                                </div>
                            );
                        })}

                        {/* Custom Added Columns */}
                        {customColumns.map((customCol, idx) => (
                            <div key={`custom-${idx}`} className="mapping-row active-row custom-row">
                                <div className="mapping-source">
                                    <span className="source-label">Custom:</span>
                                    <input
                                        type="text"
                                        value={customCol.name}
                                        onChange={(e) => handleCustomColumnChange(idx, 'name', e.target.value)}
                                        placeholder="Col Name"
                                        className="custom-col-input"
                                    />
                                </div>
                                <div className="mapping-arrow">→</div>
                                <div className="mapping-target">
                                    <select
                                        value={customCol.target || ''}
                                        onChange={(e) => handleCustomColumnChange(idx, 'target', e.target.value)}
                                        className="mapped-select"
                                    >
                                        <option value="">-- Select Target --</option>
                                        {selectableTargetColumns.map(col => (
                                            <option key={col.name} value={col.name}>
                                                {col.name} ({col.type})
                                            </option>
                                        ))}
                                    </select>
                                </div>
                                <div className="mapping-default">
                                    <input
                                        type="text"
                                        placeholder="Fixed Value"
                                        value={customCol.defaultValue || ''}
                                        onChange={(e) => handleCustomColumnChange(idx, 'defaultValue', e.target.value)}
                                    />
                                </div>
                                <div className="mapping-action">
                                    <button className="btn-icon danger" onClick={() => removeCustomColumn(idx)}>×</button>
                                </div>
                            </div>
                        ))}

                        {/* Add Custom Column Button - Bottom of List */}
                        <div className="add-column-row">
                            <Button variant="secondary" size="small" onClick={addNewColumn} className="add-col-btn full-width-btn">
                                + Add Custom Column
                            </Button>
                        </div>
                    </div>
                </div>

                {/* Production Columns (Right) - Conditionally Rendered */}
                {showProductionColumns && (
                    <div className="production-columns-section floating-panel">
                        <div className="panel-header">
                            <h3>Target Schema</h3>
                            <button onClick={() => setShowProductionColumns(false)}>×</button>
                        </div>
                        <div className="columns-list">
                            {selectableTargetColumns.map((col, idx) => {
                                const isMapped = Object.values(columnMappings).some(m => m.target === col.name) ||
                                    customColumns.some(c => c.target === col.name);
                                const isRequired = isRequiredMappingTargetColumn(col, mappingCtx);

                                return (
                                    <div key={idx} className={`column-item ${isMapped ? 'mapped' : ''}`}>
                                        <span className="column-name">
                                            {col.name}
                                            {isRequired && <span className="required-badge">*</span>}
                                        </span>
                                        <span className="column-type">{col.type}</span>
                                        {isMapped && <span className="mapped-badge">✓</span>}
                                    </div>
                                );
                            })}
                        </div>
                    </div>
                )}
            </div>

            {error && (
                <div className="error-message">
                    {error}
                </div>
            )}

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
                            <LoadingSpinner size="small" />
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
