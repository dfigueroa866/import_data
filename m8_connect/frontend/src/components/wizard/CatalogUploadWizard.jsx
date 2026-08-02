import React, { useState, useCallback } from 'react';
import { BookOpen } from 'lucide-react';
import { PageHeader, WizardStepper } from '../ui';
import Step1CatalogUpload from './Step1CatalogUpload';
import Step2Mapping from './Step2Mapping';
import Step3Preview from './Step3Preview';
import Step4Process from './Step4Process';

const STEPS = ['Archivo y tabla', 'Mapear columnas', 'Vista previa', 'Producción'];

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
    validationComplete: false,
    processing: false,
  });
  const [processingComplete, setProcessingComplete] = useState(false);
  const [hasError, setHasError] = useState(false);

  const updateWizardData = useCallback(
    (updates) => setWizardData((prev) => ({ ...prev, ...updates })),
    [],
  );
  const nextStep = () => { if (currentStep < 4) setCurrentStep(currentStep + 1); };
  const prevStep = () => { if (currentStep > 1) { setCurrentStep(currentStep - 1); setHasError(false); } };

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

  const completedSteps = [];
  for (let i = 1; i < currentStep; i++) completedSteps.push(i);
  if (processingComplete) completedSteps.push(4);

  const renderStep = () => {
    const stepProps = { wizardData, updateWizardData, nextStep, prevStep };
    switch (currentStep) {
      case 1: return <Step1CatalogUpload {...stepProps} />;
      case 2: return <Step2Mapping {...stepProps} />;
      case 3: return <Step3Preview {...stepProps} />;
      case 4:
        return (
          <Step4Process
            wizardData={wizardData}
            updateWizardData={updateWizardData}
            resetWizard={resetWizard}
            onComplete={() => { setProcessingComplete(true); setHasError(false); }}
            onError={() => setHasError(true)}
          />
        );
      default: return null;
    }
  };

  return (
    <div className="flex flex-1 flex-col gap-5 overflow-y-auto p-8 max-w-7xl mx-auto w-full scrollbar-thin">
      <PageHeader
        icon={BookOpen}
        title="Carga de catálogos"
        backTo="/upload"
        backLabel="Volver a tipo de carga"
      />
      <WizardStepper
        steps={STEPS}
        currentStep={currentStep}
        completedSteps={completedSteps}
        successStep={processingComplete ? 4 : null}
        errorStep={hasError ? 4 : null}
      />
      <div className="flex-1 min-h-0">{renderStep()}</div>
    </div>
  );
};

export default CatalogUploadWizard;
