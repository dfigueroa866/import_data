import api from './api';

export const stagingService = {
    // List all staging tables
    listTables: async () => {
        const response = await api.get('/api/v1/staging/tables');
        return response.data;
    },

    // Get staging data for a batch
    getStagingData: async (batchId, limit = 100) => {
        const response = await api.get(`/api/v1/staging/batch/${batchId}/staging-data`, {
            params: { limit },
        });
        return response.data;
    },

    // Get rejected records
    getRejectedRecords: async (batchId, limit = 100) => {
        const response = await api.get(`/api/v1/staging/batch/${batchId}/rejected-records`, {
            params: { limit },
        });
        return response.data;
    },

    // Process staging to production
    processToProduction: async (params) => {
        const response = await api.post('/api/v1/staging/process-to-production', null, {
            params,
        });
        return response.data;
    },

    // Get table columns
    getTableColumns: async (schema, table) => {
        const response = await api.get('/api/v1/staging/table-columns', {
            params: { schema, table },
        });
        return response.data;
    },
};
