import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import './UploadWizard.css';
import Step1Upload from './Step1Upload';
import { HISTORY_TABLE_META, HISTORY_TARGET_SCHEMA, HISTORY_TARGET_TABLE } from '../../constants/historyConfig';
import Step2Mapping from './Step2Mapping';
import Step3Preview from './Step3Preview';
import Step4Process from './Step4Process';

const UploadWizard = () => {
    const [currentStep, setCurrentStep] = useState(1);
    const [wizardData, setWizardData] = useState({
        loadMode: 'history',
        // Step 1 data
        file: null,
        fileName: '',
        fileHeaders: [],
        selectedSchema: HISTORY_TARGET_SCHEMA,
        selectedTable: HISTORY_TARGET_TABLE,
        historyTableMeta: HISTORY_TABLE_META,
        sourceName: '',
        batchId: '',
        processType: '',

        // Step 2 data
        columnMappings: {},
        columnToggles: {},
        dedupColumns: '',
        productionColumns: [],

        // Step 3 data
        previewData: null,
        validationSummary: null,

        // Step 4 data
        processing: false
    });

    const [processingComplete, setProcessingComplete] = useState(false);
    const [hasError, setHasError] = useState(false);

    const updateWizardData = (updates) => {
        setWizardData(prev => ({ ...prev, ...updates }));
    };

    const nextStep = () => {
        if (currentStep < 4) {
            setCurrentStep(currentStep + 1);
        }
    };

    const prevStep = () => {
        if (currentStep > 1) {
            setCurrentStep(currentStep - 1);
            setHasError(false); // Clear error when going back
        }
    };

    const resetWizard = () => {
        setCurrentStep(1);
        setProcessingComplete(false);
        setHasError(false);
        setWizardData({
            loadMode: 'history',
            file: null,
            fileName: '',
            fileHeaders: [],
            selectedSchema: HISTORY_TARGET_SCHEMA,
            selectedTable: HISTORY_TARGET_TABLE,
            historyTableMeta: HISTORY_TABLE_META,
            sourceName: '',
            batchId: '',
            processType: '',
            columnMappings: {},
            columnToggles: {},
            dedupColumns: '',
            productionColumns: [],
            previewData: null,
            validationSummary: null,
            processing: false
        });
    };

    const handleProcessingStart = () => {
        setHasError(false);
        setProcessingComplete(false);
    };

    const handleProcessComplete = () => {
        setProcessingComplete(true);
        setHasError(false);
    };

    const handleProcessError = () => {
        setHasError(true);
    };

    const renderStep = () => {
        switch (currentStep) {
            case 1:
                return (
                    <Step1Upload
                        wizardData={wizardData}
                        updateWizardData={updateWizardData}
                        nextStep={nextStep}
                    />
                );
            case 2:
                return (
                    <Step2Mapping
                        wizardData={wizardData}
                        updateWizardData={updateWizardData}
                        nextStep={nextStep}
                        prevStep={prevStep}
                    />
                );
            case 3:
                return (
                    <Step3Preview
                        wizardData={wizardData}
                        updateWizardData={updateWizardData}
                        nextStep={nextStep}
                        prevStep={prevStep}
                    />
                );
            case 4:
                return (
                    <Step4Process
                        wizardData={wizardData}
                        updateWizardData={updateWizardData}
                        resetWizard={resetWizard}
                        onComplete={handleProcessComplete}
                        onError={handleProcessError}
                        onProcessingStart={handleProcessingStart}
                    />
                );
            default:
                return null;
        }
    };

    return (
        <div className="upload-wizard">
            <div className="wizard-header">
                <Link to="/upload" className="wizard-back-link">
                    ← Volver a tipo de carga
                </Link>
                <h1>Carga de historia</h1>
                <p>Importa ventas históricas a public.sales_history en 4 pasos</p>
            </div>

            {/* Stepper */}
            <div className="wizard-stepper">
                <div className={`step ${currentStep >= 1 ? 'active' : ''} ${currentStep > 1 ? 'completed' : ''}`}>
                    <div className="step-content">
                        {currentStep > 1 ? (
                            <span className="step-icon">✓</span>
                        ) : (
                            <span className="step-number">1</span>
                        )}
                        <span className="step-label">Upload & Select Table</span>
                    </div>
                </div>

                <div className={`step ${currentStep >= 2 ? 'active' : ''} ${currentStep > 2 ? 'completed' : ''}`}>
                    <div className="step-content">
                        {currentStep > 2 ? (
                            <span className="step-icon">✓</span>
                        ) : (
                            <span className="step-number">2</span>
                        )}
                        <span className="step-label">Map Columns</span>
                    </div>
                </div>

                <div className={`step ${currentStep >= 3 ? 'active' : ''} ${currentStep > 3 ? 'completed' : ''}`}>
                    <div className="step-content">
                        {currentStep > 3 ? (
                            <span className="step-icon">✓</span>
                        ) : (
                            <span className="step-number">3</span>
                        )}
                        <span className="step-label">Preview & Validate</span>
                    </div>
                </div>

                <div className={`step ${currentStep >= 4 ? 'active' : ''} ${processingComplete ? 'completed' : ''} ${hasError ? 'error' : ''}`}>
                    <div className="step-content">
                        {processingComplete ? (
                            <span className="step-icon">✓</span>
                        ) : hasError ? (
                            <span className="step-icon">✕</span>
                        ) : (
                            <span className="step-number">4</span>
                        )}
                        <span className="step-label">Process to Production</span>
                    </div>
                </div>
            </div>

            {/* Step Content */}
            <div className="wizard-content">
                {renderStep()}
            </div>
        </div>
    );
};

export default UploadWizard;
