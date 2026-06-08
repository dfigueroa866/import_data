import api from './api';

/**
 * System service for schemas and tables
 */

/**
 * Get list of available database schemas
 */
export const getSchemas = async () => {
    try {
        const response = await api.get('/api/v1/system/schemas');
        return response.data;
    } catch (error) {
        console.error('Error getting schemas:', error);
        throw error;
    }
};

/**
 * Get tables for a specific schema
 */
export const getTables = async (schema) => {
    try {
        const response = await api.get(`/api/v1/system/tables?schema=${schema}`);
        return response.data;
    } catch (error) {
        console.error('Error getting tables:', error);
        throw error;
    }
};

/**
 * Get columns for a specific table
 */
export const getTableColumns = async (schema, table) => {
    try {
        const response = await api.get(`/api/v1/system/table-columns?schema=${schema}&table=${table}`);
        return response.data;
    } catch (error) {
        console.error('Error getting table columns:', error);
        throw error;
    }
};
