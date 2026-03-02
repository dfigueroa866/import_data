import api from './api';

/**
 * Wizard-specific upload service
 */

/**
 * Upload file for wizard (temp upload with header parsing)
 * Step 1 - Returns batch_id and file headers
 */
export const uploadFileTemp = async (file, targetSchema = null, targetTable = null, processType = null) => {
    try {
        const formData = new FormData();
        formData.append('file', file);
        if (targetSchema) formData.append('target_schema', targetSchema);
        if (targetTable) formData.append('target_table', targetTable);
        if (processType) formData.append('process_type', processType);

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
export const saveColumnMapping = async (batchId, mappingData, processType = null) => {
    try {
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
        const response = await api.post(`/api/v1/upload/batch/${batchId}/preview`);
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
export const downloadRejectedRecords = async (batchId) => {
    try {
        const response = await api.get(`/api/v1/upload/staging/batch/${batchId}/rejected/download`, {
            responseType: 'blob', // Important for file download
        });

        // Create download link
        const url = window.URL.createObjectURL(new Blob([response.data]));
        const link = document.createElement('a');
        link.href = url;
        link.setAttribute('download', `rejected_records_${batchId}.csv`);
        document.body.appendChild(link);
        link.click();
        link.remove();

        return true;
    } catch (error) {
        console.error('Error downloading rejected records:', error);
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
