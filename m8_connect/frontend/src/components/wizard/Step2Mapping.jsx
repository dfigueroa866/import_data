import React, { useState, useEffect } from 'react';
import { Trash2 } from 'lucide-react';
import { getTableColumns } from '../../services/systemService';
import { saveColumnMapping, waitForMappingValidation } from '../../services/wizardService';
import { useAuth } from '../../context/AuthContext';
import { Button, LoadingSpinner, Alert, Select, Input, inputMappedClasses } from '../ui';
import { cn } from '../../lib/utils';
import {
    isExcludedMappingTarget,
    isIgnoredFileHeader,
    isRequiredMappingTargetColumn,
    isSystemManagedTargetColumn,
    getCatalogRequiredTargetColumns,
    historyHasSkuMapping,
} from '../../utils/catalogMapping';
import {
    buildAutoColumnMappings,
    buildFinalMappingsPayload,
    buildMappingContext,
    createManualMappingKey,
    getManualMappingEntries,
    getVisibleFileHeaders as getVisibleHeaders,
    isManualMappingComplete,
    mappingsFingerprint,
    mergeHistoryProductionColumns,
} from '../../utils/wizardColumnMapping';
import useSessionLoadGuard from '../../hooks/useSessionLoadGuard';
import { formatNumber } from '../../lib/format';
import './Step2Mapping.css';

const Step2Mapping = ({ wizardData, updateWizardData, nextStep, prevStep }) => {
    const { user } = useAuth();
    const organizationId = user?.organization_id || wizardData.organizationId || '';
    const organizationName =
        user?.organization_name || wizardData.organizationName || '';

    const [productionColumns, setProductionColumns] = useState(
        wizardData.productionColumns || [],
    );
    const [columnMappings, setColumnMappings] = useState(wizardData.columnMappings || {});
    const [columnToggles, setColumnToggles] = useState(wizardData.columnToggles || {});
    const [loading, setLoading] = useState(false);
    const [saving, setSaving] = useState(false);
    const [revalidating, setRevalidating] = useState(false);
    const [validationProgress, setValidationProgress] = useState(null);
    const [error, setError] = useState('');

    useSessionLoadGuard(saving || revalidating);

    const mappingCtx = buildMappingContext(wizardData);

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
                cols = mergeHistoryProductionColumns(cols);
            }
            setProductionColumns(cols);

            const hasSavedMappings =
                wizardData.columnMappings
                && Object.keys(wizardData.columnMappings).length > 0;
            if (hasSavedMappings) {
                setColumnMappings(wizardData.columnMappings);
                setColumnToggles(wizardData.columnToggles || {});
            } else {
                autoMapColumns(wizardData.fileHeaders, cols);
            }
        } catch (err) {
            setError('Failed to load production table columns');
            console.error(err);
        } finally {
            setLoading(false);
        }
    };

    const autoMapColumns = (fileHeaders, prodColumns) => {
        const { mappings, toggles } = buildAutoColumnMappings(
            fileHeaders,
            prodColumns,
            mappingCtx,
        );
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

    const handleAddManualColumn = () => {
        const manualCount = getManualMappingEntries(columnMappings).length;
        const key = createManualMappingKey();
        setColumnMappings((prev) => ({
            ...prev,
            [key]: {
                target: '',
                default_value: '',
                label: `Columna ${manualCount + 1}`,
                is_manual: true,
                auto_mapped: false,
            },
        }));
        setColumnToggles((prev) => ({ ...prev, [key]: true }));
    };

    const handleRemoveManualColumn = (manualKey) => {
        setColumnMappings((prev) => {
            const next = { ...prev };
            delete next[manualKey];
            return next;
        });
        setColumnToggles((prev) => {
            const next = { ...prev };
            delete next[manualKey];
            return next;
        });
    };

    const handleManualMappingChange = (manualKey, field, value) => {
        setColumnMappings((prev) => ({
            ...prev,
            [manualKey]: {
                ...prev[manualKey],
                [field]: value,
                is_manual: true,
                auto_mapped: false,
            },
        }));
    };

    const getVisibleFileHeaders = () =>
        getVisibleHeaders(wizardData.fileHeaders, mappingCtx);

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

    const getActiveManualMappings = () =>
        getManualMappingEntries(columnMappings).filter(
            ([manualKey]) => columnToggles[manualKey] !== false,
        );

    const getAllMappedTargets = () => {
        const fromFile = getMappedFileHeaders()
            .map((fileCol) => columnMappings[fileCol]?.target)
            .filter(Boolean);
        const fromManual = getActiveManualMappings()
            .map(([, mapping]) => mapping?.target)
            .filter(Boolean);
        return [...fromFile, ...fromManual];
    };

    const tableHasOrganizationId = productionColumns.some(
        (col) => col.name === 'organization_id'
    );

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
                const mappedTargets = new Set(getAllMappedTargets());
                return !mappedTargets.has(reqCol.name);
            });

            if (missingCols.length > 0) {
                setError(
                    `Debes mapear las columnas obligatorias de destino: ${missingCols.map((c) => c.name).join(', ')}`
                );
                setSaving(false);
                return;
            }

            if (wizardData.loadMode === 'history') {
                const mappedTargets = getAllMappedTargets();
                if (!historyHasSkuMapping(mappedTargets, mappingCtx.catalogMeta)) {
                    setError(
                        'Debes mapear el producto a sku o sku_code, y location_code'
                    );
                    setSaving(false);
                    return;
                }
            }

            const incompleteManual = getActiveManualMappings().filter(
                ([, mapping]) => !isManualMappingComplete(mapping),
            );
            if (incompleteManual.length > 0) {
                setError(
                    'Completa el campo destino y el valor fijo en todas las columnas manuales agregadas.',
                );
                setSaving(false);
                return;
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

            const built = buildFinalMappingsPayload({
                fileHeaders: wizardData.fileHeaders,
                columnMappings,
                columnToggles,
                productionColumns,
                mappingCtx,
                wizardData,
                organizationId,
            });
            if (built.error) {
                setError(built.error);
                setSaving(false);
                return;
            }
            const finalMappings = built.mappings;
            const finalToggles = built.toggles;

            const mappingChanged =
                mappingsFingerprint(finalMappings, finalToggles)
                !== mappingsFingerprint(
                    wizardData.columnMappings || {},
                    wizardData.columnToggles || {},
                );

            if (
                !mappingChanged
                && wizardData.validationComplete
            ) {
                updateWizardData({
                    columnMappings: finalMappings,
                    columnToggles: finalToggles,
                    organizationId,
                    organizationName,
                    productionColumns,
                });
                nextStep();
                return;
            }

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

            const triggerValidation = mappingChanged;

            await saveColumnMapping(
                wizardData.batchId,
                mappingData,
                wizardData.loadMode === 'history' ? wizardData.processType : null,
                wizardData.loadMode || 'history',
                { triggerValidation },
            );

            updateWizardData({
                columnMappings: finalMappings,
                columnToggles: finalToggles,
                organizationId,
                organizationName,
                productionColumns,
                validationComplete: triggerValidation ? false : wizardData.validationComplete,
            });

            if (triggerValidation) {
                setSaving(false);
                setRevalidating(true);
                setValidationProgress(null);
                try {
                    await waitForMappingValidation(wizardData.batchId, {
                        onProgress: (p) => setValidationProgress(p),
                        estimatedRows: wizardData.estimatedRows,
                    });
                    updateWizardData({ validationComplete: true });
                } finally {
                    setRevalidating(false);
                }
            }

            nextStep();

        } catch (err) {
            setError(
                err.response?.data?.detail
                    || err.message
                    || 'No se pudo guardar el mapeo'
            );
            console.error(err);
        } finally {
            setSaving(false);
        }
    };

    const getMappedCount = () => {
        const fileMapped = getMappedFileHeaders().length;
        const manualMapped = getActiveManualMappings().filter(([, mapping]) =>
            isManualMappingComplete(mapping),
        ).length;
        return fileMapped + manualMapped + (organizationId && tableHasOrganizationId ? 1 : 0);
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

    if (revalidating) {
        const pct = Math.min(100, Math.max(0, Number(validationProgress?.progress_percentage) || 0));
        const operation = validationProgress?.current_operation || 'Revalidando filas con el mapeo actualizado…';
        const processed = validationProgress?.processed_rows ?? 0;
        const total = validationProgress?.total_rows ?? 0;
        const showRowCounts = total > 0;

        return (
            <div className="step2-loading">
                <LoadingSpinner />
                <p>{operation}</p>
                <div className="step2-progress">
                    <div className="step2-progress__bar">
                        <div
                            className="step2-progress__fill"
                            style={{ width: `${pct}%` }}
                        />
                    </div>
                    {showRowCounts && (
                        <p className="step2-progress__rows">
                            {formatNumber(processed)} de {formatNumber(total)} filas
                        </p>
                    )}
                </div>
                <p className="step2-loading__hint">
                    Archivos grandes pueden tardar varios minutos. Puedes dejar esta ventana abierta.
                </p>
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

                    <div className="manual-mapping-section">
                        <div className="manual-mapping-section__header">
                            <h4>Columnas con valor fijo</h4>
                            <p className="manual-mapping-section__hint">
                                Agrega campos de destino que no vienen en el archivo; el mismo valor
                                se aplicará a todas las filas (p. ej. pieces → 1).
                            </p>
                        </div>

                        {getActiveManualMappings().length > 0 && (
                            <div className="mapping-header-row mapping-header-row--manual">
                                <div className="col-source">Etiqueta</div>
                                <div className="col-arrow"></div>
                                <div className="col-target">Campo destino</div>
                                <div className="col-default">Valor fijo</div>
                                <div className="col-actions"></div>
                            </div>
                        )}

                        {getActiveManualMappings().map(([manualKey, mapping]) => (
                            <div key={manualKey} className="mapping-row mapping-row--manual active-row">
                                <div className="mapping-source">
                                    <span className="source-name text-highlight">
                                        {mapping.label || 'Columna manual'}
                                    </span>
                                    <span className="auto-badge manual-badge">Valor fijo</span>
                                </div>
                                <div className="mapping-arrow">→</div>
                                <div className="mapping-target">
                                    <Select
                                        value={mapping.target || ''}
                                        onChange={(e) =>
                                            handleManualMappingChange(manualKey, 'target', e.target.value)
                                        }
                                        className={cn(mapping.target && inputMappedClasses)}
                                    >
                                        <option value="">-- Seleccionar campo --</option>
                                        {selectableTargetColumns.map((col) => (
                                            <option key={col.name} value={col.name}>
                                                {col.name} ({col.type})
                                            </option>
                                        ))}
                                    </Select>
                                </div>
                                <div className="mapping-default">
                                    <Input
                                        type="text"
                                        value={mapping.default_value ?? ''}
                                        onChange={(e) =>
                                            handleManualMappingChange(
                                                manualKey,
                                                'default_value',
                                                e.target.value,
                                            )
                                        }
                                        placeholder="Ej. 1"
                                        className={cn(
                                            String(mapping.default_value ?? '').trim() && inputMappedClasses,
                                        )}
                                    />
                                </div>
                                <div className="mapping-actions-cell">
                                    <button
                                        type="button"
                                        className="btn-icon danger"
                                        title="Eliminar columna manual"
                                        aria-label="Eliminar columna manual"
                                        onClick={() => handleRemoveManualColumn(manualKey)}
                                    >
                                        <Trash2 className="h-4 w-4" aria-hidden="true" />
                                    </button>
                                </div>
                            </div>
                        ))}

                        <div className="add-column-row">
                            <Button
                                type="button"
                                variant="secondary"
                                className="add-col-btn"
                                onClick={handleAddManualColumn}
                            >
                                + Añadir columna con valor fijo
                            </Button>
                        </div>
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
                    loading={saving}
                    loadingLabel="Guardando mapeo…"
                    disabled={revalidating || getMappedCount() === 0}
                >
                    Continuar a vista previa →
                </Button>
            </div>
        </div>
    );
};

export default Step2Mapping;
