import api from './api';
import { FALLBACK_CATALOG_TABLES } from '../constants/catalogTables';

/**
 * Wizard-specific upload service
 */

/**
 * Catalog tables for upload wizard (API + fallback if backend not restarted).
 */
export const getCatalogTables = async () => {
    try {
        const response = await api.get('/api/v1/system/catalog-tables');
        const tables = response.data?.tables;
        if (Array.isArray(tables) && tables.length > 0) {
            return { tables, fromFallback: false };
        }
    } catch (error) {
        const status = error.response?.status;
        if (status && status !== 404 && status !== 502) {
            console.warn('getCatalogTables:', error);
        }
    }

    console.warn(
        'catalog-tables API no disponible; usando lista local. Reinicia el backend: python run_app.py'
    );
    return { tables: FALLBACK_CATALOG_TABLES, fromFallback: true };
};

export const uploadFileTemp = async (
    file,
    targetSchema = null,
    targetTable = null,
    processType = null,
    loadType = 'history'
) => {
    try {
        const formData = new FormData();
        formData.append('file', file);
        if (targetSchema) formData.append('target_schema', targetSchema);
        if (targetTable) formData.append('target_table', targetTable);
        if (processType) formData.append('process_type', processType);
        if (loadType) formData.append('load_type', loadType);

        const response = await api.post('/api/v1/upload/file-temp', formData, {
            headers: {
                'Content-Type': 'multipart/form-data',
            },
        });
        return response.data;
    } catch (error) {
        console.error('Error uploading file (temp):', error);
        throw error;
    }
};

/**
 * Save column mappings for a batch
 * Step 2 - Saves mappings, toggles, and dedup columns
 */
export const saveColumnMapping = async (batchId, mappingData, processType = null, loadType = null) => {
    try {
        if (loadType) {
            mappingData.load_type = loadType;
        }
        if (processType) {
            mappingData.process_type = processType;
        }
        const response = await api.post(`/api/v1/upload/batch/${batchId}/mapping`, mappingData);
        return response.data;
    } catch (error) {
        console.error('Error saving column mapping:', error);
        throw error;
    }
};

/**
 * Generate preview for a batch
 * Step 3 - Applies mappings and returns preview + validation
 */
export const generatePreview = async (batchId) => {
    try {
        const response = await api.post(`/api/v1/upload/batch/${batchId}/preview`, null, {
            timeout: 600000,
        });
        return response.data;
    } catch (error) {
        console.error('Error generating preview:', error);
        throw error;
    }
};

/**
 * Get processing progress for a batch
 * Step 4 - Real-time progress tracking
 */
export const getProcessingProgress = async (batchId) => {
    try {
        const response = await api.get(`/api/v1/upload/batch/${batchId}/progress`);
        return response.data;
    } catch (error) {
        console.error('Error getting progress:', error);
        throw error;
    }
};

/**
 * Start processing a batch
 * Step 4 - Triggers actual data processing
 */
export const startProcessing = async (batchId, options = {}) => {
    try {
        const response = await api.post(`/api/v1/upload/batch/${batchId}/process`, options);
        return response.data;
    } catch (error) {
        console.error('Error starting processing:', error);
        throw error;
    }
};

/**
 * Promote batch to production
 * Step 5 - Triggers promotion job
 */
export const promoteBatch = async (batchId) => {
    try {
        const response = await api.post(`/api/v1/upload/staging/promote/${batchId}`);
        return response.data;
    } catch (error) {
        console.error('Error promoting batch:', error);
        throw error;
    }
};

/**
 * Download rejected records CSV
 * Helper for handling rejections
 */
const triggerBlobDownload = (blob, filename) => {
    const url = window.URL.createObjectURL(new Blob([blob]));
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', filename);
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
};

export const downloadRejectedRecords = async (batchId) => {
    try {
        const response = await api.get(`/api/v1/upload/staging/batch/${batchId}/rejected/download`, {
            responseType: 'blob',
        });
        triggerBlobDownload(response.data, `rejected_records_${batchId}.csv`);
        return true;
    } catch (error) {
        console.error('Error downloading rejected records:', error);
        throw error;
    }
};

export const downloadValidRecords = async (batchId) => {
    try {
        const response = await api.get(`/api/v1/upload/staging/batch/${batchId}/valid/download`, {
            responseType: 'blob',
        });
        triggerBlobDownload(response.data, `valid_records_${batchId}.csv`);
        return true;
    } catch (error) {
        console.error('Error downloading valid records:', error);
        throw error;
    }
};
/**
 * Delete a batch and all associated data
 * For cleaning up failed attempts
 */
export const deleteBatch = async (batchId) => {
    try {
        const response = await api.delete(`/api/v1/upload/batch/${batchId}`);
        return response.data;
    } catch (error) {
        console.error('Error deleting batch:', error);
        throw error;
    }
};
