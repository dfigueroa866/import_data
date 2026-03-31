import api from './api';

export const uploadService = {
    // Upload a file
    uploadFile: async (file, sourceName = null) => {
        const formData = new FormData();
        formData.append('file', file);
        if (sourceName) {
            formData.append('source_name', sourceName);
        }

        const response = await api.post('/api/v1/upload/file', formData, {
            headers: {
                'Content-Type': 'multipart/form-data',
            },
            onUploadProgress: (progressEvent) => {
                const percentCompleted = Math.round(
                    (progressEvent.loaded * 100) / progressEvent.total
                );
                console.log(`Upload Progress: ${percentCompleted}%`);
            },
        });

        return response.data;
    },

    // Get batch status
    getBatchStatus: async (batchId) => {
        const response = await api.get(`/api/v1/upload/batch/${batchId}/status`);
        return response.data;
    },

    // List batches
    listBatches: async (params = {}) => {
        const response = await api.get('/api/v1/upload/batches', { params });
        return response.data;
    },

    // Process batch
    processBatch: async (batchId, config = {}) => {
        const response = await api.post(`/api/v1/upload/process/${batchId}`, config);
        return response.data;
    },

    // Resume Partially Promoted batch
    resumePromotion: async (batchId) => {
        const response = await api.post(`/api/v1/upload/staging/promote/${batchId}/resume`);
        return response.data;
    },
};
