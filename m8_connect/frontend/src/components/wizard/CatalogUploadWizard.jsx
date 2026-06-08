import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import './UploadWizard.css';
import Step1CatalogUpload from './Step1CatalogUpload';
import Step2Mapping from './Step2Mapping';
import Step3Preview from './Step3Preview';
import Step4Process from './Step4Process';

const CatalogUploadWizard = () => {
    const [currentStep, setCurrentStep] = useState(1);
    const [wizardData, setWizardData] = useState({
        loadMode: 'catalog',
        file: null,
        fileName: '',
        fileHeaders: [],
        selectedSchema: 'public',
        selectedTable: '',
        catalogTable: '',
        catalogTableMeta: null,
        sourceName: '',
        batchId: '',
        processType: '',
        columnMappings: {},
        columnToggles: {},
        dedupColumns: '',
        productionColumns: [],
        previewData: null,
        validationSummary: null,
        processing: false,
    });

    const [processingComplete, setProcessingComplete] = useState(false);
    const [hasError, setHasError] = useState(false);

    const updateWizardData = (updates) => {
        setWizardData((prev) => ({ ...prev, ...updates }));
    };

    const nextStep = () => {
        if (currentStep < 4) setCurrentStep(currentStep + 1);
    };

    const prevStep = () => {
        if (currentStep > 1) {
            setCurrentStep(currentStep - 1);
            setHasError(false);
        }
    };

    const resetWizard = () => {
        setCurrentStep(1);
        setProcessingComplete(false);
        setHasError(false);
        setWizardData({
            loadMode: 'catalog',
            file: null,
            fileName: '',
            fileHeaders: [],
            selectedSchema: 'public',
            selectedTable: '',
            catalogTable: '',
            catalogTableMeta: null,
            sourceName: '',
            batchId: '',
            processType: '',
            columnMappings: {},
            columnToggles: {},
            dedupColumns: '',
            productionColumns: [],
            previewData: null,
            validationSummary: null,
            processing: false,
        });
    };

    const renderStep = () => {
        const stepProps = { wizardData, updateWizardData, nextStep, prevStep };
        switch (currentStep) {
            case 1:
                return <Step1CatalogUpload {...stepProps} />;
            case 2:
                return <Step2Mapping {...stepProps} />;
            case 3:
                return <Step3Preview {...stepProps} />;
            case 4:
                return (
                    <Step4Process
                        wizardData={wizardData}
                        updateWizardData={updateWizardData}
                        resetWizard={resetWizard}
                        onComplete={() => {
                            setProcessingComplete(true);
                            setHasError(false);
                        }}
                        onError={() => setHasError(true)}
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
                <h1>Carga de catálogos</h1>
                <p>Productos (SKUs) y ubicaciones en 4 pasos</p>
            </div>

            <div className="wizard-stepper">
                {[
                    'Archivo y tabla',
                    'Mapear columnas',
                    'Vista previa',
                    'Procesar',
                ].map((label, idx) => {
                    const stepNum = idx + 1;
                    return (
                        <div
                            key={label}
                            className={`step ${currentStep >= stepNum ? 'active' : ''} ${currentStep > stepNum ? 'completed' : ''} ${stepNum === 4 && hasError ? 'error' : ''}`}
                        >
                            <div className="step-content">
                                {currentStep > stepNum || (stepNum === 4 && processingComplete) ? (
                                    <span className="step-icon">✓</span>
                                ) : stepNum === 4 && hasError ? (
                                    <span className="step-icon">✕</span>
                                ) : (
                                    <span className="step-number">{stepNum}</span>
                                )}
                                <span className="step-label">{label}</span>
                            </div>
                        </div>
                    );
                })}
            </div>

            <div className="wizard-content">{renderStep()}</div>
        </div>
    );
};

export default CatalogUploadWizard;
