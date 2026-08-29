import api from './api';
import { FALLBACK_CATALOG_TABLES } from '../constants/catalogTables';
import { FALLBACK_PROCESS_TYPES, FALLBACK_HISTORY_TABLES, HISTORY_TABLE_META } from '../constants/historyConfig';
import {
    MAX_STALE_POLLS,
    POLL_INTERVAL_PROMOTION_MS,
    PROMOTION_BASE_WAIT_MS,
    PROMOTION_CHUNK_ROWS,
    PROMOTION_MS_PER_CHUNK,
} from '../constants/pollConfig';

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

/**
 * History tables for upload wizard.
 */
export const getHistoryTables = async () => {
    try {
        const response = await api.get('/api/v1/system/history-tables');
        const tables = response.data?.tables;
        if (Array.isArray(tables) && tables.length > 0) {
            return { tables, fromFallback: false };
        }
    } catch (error) {
        const status = error.response?.status;
        if (status && status !== 404 && status !== 502) {
            console.warn('getHistoryTables:', error);
        }
    }

    console.warn(
        'history-tables API no disponible; usando lista local. Reinicia el backend: python run_app.py'
    );
    return { tables: FALLBACK_HISTORY_TABLES, fromFallback: true };
};

/**
 * History table metadata for upload wizard (process types, mapping rules).
 */
export const getHistoryTable = async (tableName = 'sales_history') => {
    try {
        const response = await api.get('/api/v1/system/history-table', {
            params: { name: tableName },
        });
        const table = response.data?.table;
        if (table && typeof table === 'object') {
            const fallback =
                FALLBACK_HISTORY_TABLES.find((t) => t.name === tableName) || HISTORY_TABLE_META;
            return {
                table: {
                    ...fallback,
                    ...table,
                    process_types: table.process_types?.length
                        ? table.process_types
                        : fallback.process_types || FALLBACK_PROCESS_TYPES,
                },
                fromFallback: false,
            };
        }
    } catch (error) {
        const status = error.response?.status;
        if (status && status !== 404 && status !== 502) {
            console.warn('getHistoryTable:', error);
        }
    }

    console.warn(
        'history-table API no disponible; usando configuración local. Reinicia el backend: python run_app.py'
    );
    const fallback =
        FALLBACK_HISTORY_TABLES.find((t) => t.name === tableName) || HISTORY_TABLE_META;
    return { table: fallback, fromFallback: true };
};

/** Whether promoted catalog batches exist before history upload. */
export const getHistoryCatalogReadiness = async () => {
    const response = await api.get('/api/v1/upload/history/readiness');
    return response.data;
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
export const saveColumnMapping = async (
    batchId,
    mappingData,
    processType = null,
    loadType = null,
    { triggerValidation = true } = {},
) => {
    try {
        if (loadType) {
            mappingData.load_type = loadType;
        }
        if (processType) {
            mappingData.process_type = processType;
        }
        mappingData.trigger_validation = triggerValidation;
        const response = await api.post(`/api/v1/upload/batch/${batchId}/mapping`, mappingData);
        return response.data;
    } catch (error) {
        console.error('Error saving column mapping:', error);
        throw error;
    }
};

/**
 * Wait until initial mapping validation finishes (VALIDATE_BATCH worker).
 */
const VALIDATION_CHUNK_ROWS = 250_000;
const VALIDATION_MS_PER_CHUNK = 45_000;
const VALIDATION_BASE_MS = 120_000;
const VALIDATION_MIN_WAIT_MS = 600_000;
const VALIDATION_MAX_WAIT_MS = 3_600_000;

/** Escalar timeout según filas estimadas (~45 s/chunk + 2 min base, mín. 10 min). */
export const computeMappingValidationMaxWaitMs = (estimatedRows = 0) => {
    const rows = Math.max(0, Number(estimatedRows) || 0);
    const chunks = rows > 0 ? Math.ceil(rows / VALIDATION_CHUNK_ROWS) : 4;
    const scaled = VALIDATION_BASE_MS + chunks * VALIDATION_MS_PER_CHUNK;
    return Math.min(VALIDATION_MAX_WAIT_MS, Math.max(VALIDATION_MIN_WAIT_MS, scaled));
};

const _validationStillRunning = (progress) => {
    if (!progress) return false;
    if (progress.validation_in_progress || progress.validation_job_active) return true;
    return (
        progress.job_type === 'VALIDATE_BATCH'
        && ['PENDING', 'PROCESSING'].includes(progress.job_status)
    );
};

export const waitForMappingValidation = async (
    batchId,
    { onProgress, maxWaitMs, estimatedRows = 0 } = {},
) => {
    const waitLimit = maxWaitMs ?? computeMappingValidationMaxWaitMs(estimatedRows);
    const start = Date.now();
    const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

    while (Date.now() - start < waitLimit) {
        const progress = await getProcessingProgress(batchId);
        onProgress?.(progress);

        if (progress?.validation_complete) {
            return progress;
        }
        if (progress?.phase === 'mapping_validation_failed') {
            throw new Error(progress?.current_operation || 'Error en la validación del mapeo.');
        }
        if (
            !progress?.validation_in_progress
            && progress?.phase === 'mapping_validation_done'
        ) {
            return progress;
        }

        await delay(1500);
    }

    const last = await getProcessingProgress(batchId).catch(() => null);
    if (last?.validation_complete) {
        return last;
    }
    if (_validationStillRunning(last)) {
        const mins = Math.round(waitLimit / 60_000);
        throw new Error(
            `La validación sigue en curso (${mins} min de espera en pantalla). `
            + 'El worker puede terminar en breve; revisa el progreso en Lotes o espera y recarga.',
        );
    }
    throw new Error(
        'La validación no avanzó. Revisa que los workers estén activos (python run_workers.py).',
    );
};

/** True while a PROMOTE_BATCH job is queued or running. */
export const isPromotionStillRunning = (progress) => {
    if (!progress) return false;
    if (progress.promotion_job_active) return true;
    return (
        progress.job_type === 'PROMOTE_BATCH'
        && ['PENDING', 'PROCESSING'].includes(progress.job_status)
    );
};

/** Scale stale poll threshold for long promotion UPSERT runs (~60s per 500k batch). */
export const computePromotionMaxStalePolls = (estimatedRows = 0) => {
    const rows = Math.max(0, Number(estimatedRows) || 0);
    const chunks = rows > 0 ? Math.ceil(rows / PROMOTION_CHUNK_ROWS) : 4;
    const waitMs = PROMOTION_BASE_WAIT_MS + chunks * PROMOTION_MS_PER_CHUNK;
    const polls = Math.ceil(waitMs / POLL_INTERVAL_PROMOTION_MS);
    return Math.max(MAX_STALE_POLLS, polls);
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
        if (error.response?.status === 202 && error.response?.data?.status === 'validating') {
            return { status: 202, data: error.response.data, validating: true };
        }
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

export const downloadUploadLayouts = async () => {
    const response = await api.get('/api/v1/upload/layouts/download', {
        responseType: 'blob',
    });

    const contentType = String(response.headers?.['content-type'] || '');
    if (contentType.includes('application/json')) {
        const detail = await parseBlobErrorDetail(response.data);
        throw new Error(detail || 'No se pudieron generar los layouts.');
    }

    const disposition = String(response.headers?.['content-disposition'] || '');
    const match = disposition.match(/filename="?([^"]+)"?/i);
    const filename = match?.[1] || 'm8_connect_layouts.zip';
    triggerBlobDownload(response.data, filename);
    return true;
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
