import React, { useState, useEffect } from 'react';
import { getTableColumns } from '../../services/systemService';
import { saveColumnMapping } from '../../services/wizardService';
import Button from '../Button';
import LoadingSpinner from '../LoadingSpinner';
import './Step2Mapping.css';

const Step2Mapping = ({ wizardData, updateWizardData, nextStep, prevStep }) => {
    const [productionColumns, setProductionColumns] = useState([]);
    const [columnMappings, setColumnMappings] = useState({});
    const [columnToggles, setColumnToggles] = useState({});
    const [dedupColumns, setDedupColumns] = useState('');
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
            setProductionColumns(data.columns || []);

            // Auto-map columns
            autoMapColumns(wizardData.fileHeaders, data.columns || []);
        } catch (err) {
            setError('Failed to load production table columns');
            console.error(err);
        } finally {
            setLoading(false);
        }
    };

    const autoMapColumns = (fileHeaders, prodColumns) => {
        const mappings = {};
        const toggles = {};

        fileHeaders.forEach(fileCol => {
            // Initialize toggle to ON by default
            toggles[fileCol] = true;

            // Try to find exact match (case-insensitive)
            const match = prodColumns.find(
                prodCol => prodCol.name.toLowerCase() === fileCol.toLowerCase()
            );

            if (match) {
                mappings[fileCol] = {
                    target: match.name,
                    default_value: '',
                    auto_mapped: true
                };
            } else {
                mappings[fileCol] = {
                    target: '',
                    default_value: '',
                    auto_mapped: false
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

    const handleSubmit = async () => {
        try {
            setSaving(true);
            setError('');

            // 1. Validation: Ensure all required columns are mapped (excluding UUIDs which are DB-generated)
            const requiredCols = productionColumns.filter(col =>
                col.nullable === false &&
                !col.default &&
                !col.type.toLowerCase().includes('uuid')
            );
            const missingCols = requiredCols.filter(reqCol => {
                // Is it mapped from a file column that is toggled ON?
                const mappedFromFile = Object.entries(columnMappings).some(([fileCol, mapping]) =>
                    mapping.target === reqCol.name && columnToggles[fileCol]
                );
                // Is it mapped from a custom column with a target selected?
                const mappedFromCustom = customColumns.some(c => c.target === reqCol.name);

                return !mappedFromFile && !mappedFromCustom;
            });

            if (missingCols.length > 0) {
                setError(`The following required target columns must be mapped: ${missingCols.map(c => c.name).join(', ')}`);
                setSaving(false);
                return;
            }

            // 2. Prepare mapping data (merge file mappings and custom columns)
            const finalMappings = { ...columnMappings };
            const finalToggles = { ...columnToggles };

            customColumns.forEach((c, idx) => {
                if (c.target) {
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

            const mappingData = {
                target_schema: wizardData.selectedSchema,
                target_table: wizardData.selectedTable,
                column_mappings: finalMappings,
                column_toggles: finalToggles,
                dedup_columns: dedupColumns.trim()
            };

            // Save to backend
            await saveColumnMapping(wizardData.batchId, mappingData, wizardData.processType);

            // Update wizard data
            updateWizardData({
                columnMappings: finalMappings,
                columnToggles: finalToggles,
                dedupColumns: dedupColumns.trim(),
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
        return Object.values(columnMappings).filter(m => m.target && m.target !== '').length;
    };

    const getActiveColumnsCount = () => {
        return Object.values(columnToggles).filter(v => v === true).length;
    };

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
                Map your file columns to production table columns. Toggled columns will be included in the import.
            </p>

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
                    <span className="stat-value">{productionColumns.length}</span>
                    <span className="stat-label">Target Columns</span>
                </div>
            </div>

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

                        {wizardData.fileHeaders.map((fileCol, idx) => {
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
                                            {productionColumns.map(col => (
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
                                        {productionColumns.map(col => (
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
                            {productionColumns.map((col, idx) => {
                                const isMapped = Object.values(columnMappings).some(m => m.target === col.name) ||
                                    customColumns.some(c => c.target === col.name);
                                const isRequired = col.nullable === false && !col.default;

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

            {/* Deduplication */}
            <div className="dedup-section">
                <h3>Deduplication (Optional)</h3>
                <p className="dedup-hint">
                    Specify production column names separated by commas to check for duplicates.
                    Leave empty to skip duplicate validation.
                </p>
                <input
                    type="text"
                    className="dedup-input"
                    placeholder="e.g., email, phone or product_code"
                    value={dedupColumns}
                    onChange={(e) => setDedupColumns(e.target.value)}
                />
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
