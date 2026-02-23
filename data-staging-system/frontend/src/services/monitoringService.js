import api from './api';

export const monitoringService = {
    // Get system status
    getSystemStatus: async () => {
        const response = await api.get('/api/v1/monitoring/system-status');
        return response.data;
    },

    // Get metrics
    getMetrics: async (hours = 24) => {
        const response = await api.get('/api/v1/monitoring/metrics', {
            params: { hours },
        });
        return response.data;
    },

    // Get detailed health
    getDetailedHealth: async () => {
        const response = await api.get('/api/v1/monitoring/health-detailed');
        return response.data;
    },

    // Get health
    getHealth: async () => {
        const response = await api.get('/health');
        return response.data;
    },

    // List data sources
    listSources: async () => {
        const response = await api.get('/api/v1/sources');
        return response.data;
    },
};
