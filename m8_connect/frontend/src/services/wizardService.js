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
 * Start preview generation (async). Poll /progress then GET /preview-result.
 */
export const startPreview = async (batchId, { force = false } = {}) => {
    try {
        const response = await api.post(`/api/v1/upload/batch/${batchId}/preview`, null, {
            timeout: 30000,
            params: force ? { force: true } : undefined,
        });
        return { status: response.status, data: response.data };
    } catch (error) {
        console.error('Error starting preview:', error);
        throw error;
    }
};

/**
 * Fetch completed preview payload.
 */
export const getPreviewResult = async (batchId) => {
    try {
        const response = await api.get(`/api/v1/upload/batch/${batchId}/preview-result`, {
            timeout: 60000,
        });
        return response.data;
    } catch (error) {
        console.error('Error fetching preview result:', error);
        throw error;
    }
};

/**
 * @deprecated Use startPreview + polling + getPreviewResult
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
const parseBlobErrorDetail = async (blob) => {
    if (!(blob instanceof Blob)) {
        return null;
    }
    try {
        const text = await blob.text();
        if (!text) {
            return null;
        }
        try {
            const parsed = JSON.parse(text);
            if (typeof parsed?.detail === 'string') {
                return parsed.detail;
            }
            if (Array.isArray(parsed?.detail)) {
                return parsed.detail.map((item) => item?.msg || String(item)).join('; ');
            }
            return text;
        } catch {
            return text;
        }
    } catch {
        return null;
    }
};

const triggerBlobDownload = (blob, filename) => {
    const data = blob instanceof Blob ? blob : new Blob([blob], { type: 'text/csv;charset=utf-8' });
    const url = window.URL.createObjectURL(data);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    link.rel = 'noopener';
    link.style.display = 'none';
    document.body.appendChild(link);
    link.click();
    window.setTimeout(() => {
        link.remove();
        window.URL.revokeObjectURL(url);
    }, 250);
};

export const downloadRejectedRecords = async (batchId) => {
    if (!batchId) {
        throw new Error('No hay batch activo para descargar rechazados.');
    }

    try {
        const response = await api.get(`/api/v1/upload/staging/batch/${batchId}/rejected/download`, {
            responseType: 'blob',
        });

        const contentType = String(response.headers?.['content-type'] || '');
        if (contentType.includes('application/json')) {
            const detail = await parseBlobErrorDetail(response.data);
            throw new Error(detail || 'No se pudo descargar el archivo de rechazados.');
        }

        if (!response.data || response.data.size === 0) {
            throw new Error('El archivo de rechazados está vacío.');
        }

        triggerBlobDownload(response.data, `rejected_records_${batchId}.csv`);
        return true;
    } catch (error) {
        console.error('Error downloading rejected records:', error);
        if (error.response?.data instanceof Blob) {
            const detail = await parseBlobErrorDetail(error.response.data);
            if (detail) {
                throw new Error(detail);
            }
        }
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
