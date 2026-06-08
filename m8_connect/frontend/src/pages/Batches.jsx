import React, { useState, useEffect, useMemo, useRef } from 'react';
import { createPortal } from 'react-dom';
import { useNavigate } from 'react-router-dom';
import {
    Search,
    RefreshCw,
    Eye,
    Play,
    XCircle,
    Layers,
    Loader2,
    CheckCircle2,
    AlertTriangle,
    ArrowUp,
    ArrowDown,
    ArrowUpDown,
    Trash2,
    ChevronLeft,
    ChevronRight,
} from 'lucide-react';
import StatusBadge from '../components/StatusBadge';
import LoadingSpinner from '../components/LoadingSpinner';
import Button from '../components/Button';
import Modal from '../components/Modal';
import { uploadService } from '../services/uploadService';
import useSessionLoadGuard from '../hooks/useSessionLoadGuard';
import '../components/wizard/Step3Preview.css';
import './Batches.css';

const ACTIVE_STATUSES = ['PROCESSING', 'PENDING', 'PENDING_PROCESS', 'PENDING_MAPPING', 'PENDING_PREVIEW'];
const RESUMABLE_STATUSES = ['FAILED', 'PARTIALLY_PROMOTED'];
const MONITOR_STATUSES = [...ACTIVE_STATUSES, 'COMPLETED', ...RESUMABLE_STATUSES];
const CANCELLABLE_STATUSES = [...ACTIVE_STATUSES, ...RESUMABLE_STATUSES];
const SUCCESS_STATUSES = ['COMPLETED', 'PROMOTED', 'PARTIALLY_PROMOTED'];

const getBatchDisplayDate = (batch) =>
    batch?.display_at || batch?.created_at || batch?.started_at || batch?.completed_at || null;

const formatDate = (value) => {
    if (value == null || value === '') return '—';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return '—';
    return date.toLocaleString('es-MX', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
    });
};

const getBatchDateMs = (batch) => {
    const raw = getBatchDisplayDate(batch);
    if (!raw) return 0;
    const ms = new Date(raw).getTime();
    return Number.isNaN(ms) ? 0 : ms;
};

const PAGE_SIZE = 10;

const SORTABLE_COLUMNS = [
    { key: 'batch_id', label: 'Batch ID', getValue: (b) => (b.batch_id || '').toLowerCase() },
    {
        key: 'organization_name',
        label: 'Organización',
        getValue: (b) => (b.organization_name || b.organization_id || '').toLowerCase(),
    },
    { key: 'source_name', label: 'Fuente', getValue: (b) => (b.source_name || '').toLowerCase() },
    { key: 'status', label: 'Estado', getValue: (b) => (b.status || '').toLowerCase() },
    {
        key: 'records_count',
        label: 'Registros',
        getValue: (b) => Number(b.records_count) || 0,
        numeric: true,
    },
    {
        key: 'file_size',
        label: 'Tamaño',
        getValue: (b) => Number(b.file_size) || 0,
        numeric: true,
    },
    {
        key: 'created_at',
        label: 'Fecha',
        getValue: (b) => getBatchDateMs(b),
        numeric: true,
    },
    {
        key: 'duration_seconds',
        label: 'Tiempo carga',
        getValue: (b) => Number(b.duration_seconds) || 0,
        numeric: true,
    },
];

const SortableTh = ({ columnKey, label, sortKey, sortDir, onSort, className = '' }) => {
    const active = sortKey === columnKey;
    const Icon = active ? (sortDir === 'asc' ? ArrowUp : ArrowDown) : ArrowUpDown;
    return (
        <th className={className}>
            <button
                type="button"
                className={`batches-sort-btn${active ? ' batches-sort-btn--active' : ''}`}
                onClick={() => onSort(columnKey)}
                aria-sort={active ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}
            >
                <span>{label}</span>
                <Icon size={14} className="batches-sort-btn__icon" aria-hidden />
            </button>
        </th>
    );
};

const formatFileSize = (bytes) => {
    if (!bytes) return '—';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(2)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
};

const formatDurationSeconds = (seconds) => {
    const total = Math.max(0, Math.floor(Number(seconds) || 0));
    if (total < 60) return `${total}s`;
    if (total < 3600) {
        const minutes = Math.floor(total / 60);
        const secs = total % 60;
        return secs ? `${minutes}m ${secs}s` : `${minutes}m`;
    }
    const hours = Math.floor(total / 3600);
    const minutes = Math.floor((total % 3600) / 60);
    const secs = total % 60;
    const parts = [`${hours}h`];
    if (minutes) parts.push(`${minutes}m`);
    if (secs && hours < 2) parts.push(`${secs}s`);
    return parts.join(' ');
};

const getBatchDurationLabel = (batch) => {
    if (batch?.duration_label) return batch.duration_label;
    if (batch?.duration_seconds == null) return '—';
    const label = formatDurationSeconds(batch.duration_seconds);
    return batch?.duration_in_progress ? `${label}…` : label;
};

const getBatchDurationTitle = (batch) => {
    const start = batch?.started_at || batch?.created_at;
    const end = batch?.duration_in_progress
        ? 'En curso'
        : batch?.completed_at || '—';
    if (!start) return 'Sin registro de inicio';
    return `Inicio: ${formatDate(start)} · Fin: ${typeof end === 'string' ? formatDate(end) : end}`;
};

const POPOVER_WIDTH = 320;
const POPOVER_GAP = 8;

const BatchStatusCell = ({ status, errorMessage }) => {
    const triggerRef = useRef(null);
    const [open, setOpen] = useState(false);
    const [position, setPosition] = useState({ top: 0, left: 0 });

    const showPopover = Boolean(errorMessage && status !== 'PROMOTED');

    const updatePosition = () => {
        if (!triggerRef.current) return;
        const rect = triggerRef.current.getBoundingClientRect();
        const left = Math.min(
            Math.max(12, rect.left),
            window.innerWidth - POPOVER_WIDTH - 12
        );
        let top = rect.bottom + POPOVER_GAP;
        const estimatedHeight = 160;
        if (top + estimatedHeight > window.innerHeight - 12) {
            top = Math.max(12, rect.top - estimatedHeight - POPOVER_GAP);
        }
        setPosition({ top, left });
    };

    const handleEnter = () => {
        if (!showPopover) return;
        updatePosition();
        setOpen(true);
    };

    const handleLeave = () => setOpen(false);

    return (
        <div className="batch-status-cell">
            <div
                ref={triggerRef}
                className={`batch-status-trigger${showPopover ? ' batch-status-trigger--interactive' : ''}`}
                onMouseEnter={handleEnter}
                onMouseLeave={handleLeave}
                onFocus={handleEnter}
                onBlur={handleLeave}
                tabIndex={showPopover ? 0 : undefined}
                aria-describedby={open && showPopover ? 'batch-error-popover' : undefined}
            >
                <StatusBadge status={status} />
            </div>
            {showPopover &&
                open &&
                createPortal(
                    <div
                        id="batch-error-popover"
                        className="batch-error-popover"
                        style={{ top: position.top, left: position.left, width: POPOVER_WIDTH }}
                        role="tooltip"
                        onMouseEnter={handleEnter}
                        onMouseLeave={handleLeave}
                    >
                        <div className="batch-error-popover__title">Detalle del error</div>
                        <pre className="batch-error-popover__body">{errorMessage}</pre>
                    </div>,
                    document.body
                )}
        </div>
    );
};

const Batches = () => {
    const navigate = useNavigate();
    const [batches, setBatches] = useState([]);
    const [loading, setLoading] = useState(true);
    const [filter, setFilter] = useState('');
    const [searchQuery, setSearchQuery] = useState('');
    const [statusFilter, setStatusFilter] = useState('');
    const [page, setPage] = useState(1);
    const [total, setTotal] = useState(0);
    const [totalPages, setTotalPages] = useState(1);
    const [selectedIds, setSelectedIds] = useState(() => new Set());
    const [cancellingId, setCancellingId] = useState(null);
    const [deleting, setDeleting] = useState(false);
    const [actionMessage, setActionMessage] = useState(null);
    const [sortKey, setSortKey] = useState('created_at');
    const [sortDir, setSortDir] = useState('desc');
    const [confirmModal, setConfirmModal] = useState({
        isOpen: false,
        title: '',
        message: '',
        confirmText: 'Aceptar',
        cancelText: 'Cancelar',
        variant: 'primary',
        onConfirm: null,
    });

    useEffect(() => {
        const t = setTimeout(() => setSearchQuery(filter.trim()), 400);
        return () => clearTimeout(t);
    }, [filter]);

    useEffect(() => {
        setPage(1);
    }, [statusFilter, searchQuery]);

    const loadBatches = async ({ silent = false } = {}) => {
        try {
            if (!silent) setLoading(true);
            const params = {
                limit: PAGE_SIZE,
                offset: (page - 1) * PAGE_SIZE,
            };
            if (statusFilter) params.status = statusFilter;
            if (searchQuery) params.search = searchQuery;
            const data = await uploadService.listBatches(params);
            setBatches(data.batches || []);
            setTotal(data.total ?? 0);
            setTotalPages(data.total_pages ?? 1);
            if (!silent) setSelectedIds(new Set());
        } catch (error) {
            console.error('Error loading batches:', error);
        } finally {
            if (!silent) setLoading(false);
        }
    };

    useEffect(() => {
        loadBatches();
    }, [statusFilter, searchQuery, page]);

    const hasInProgressLoads = useMemo(
        () => batches.some((b) => b.duration_in_progress),
        [batches]
    );

    useSessionLoadGuard(hasInProgressLoads);

    useEffect(() => {
        if (!hasInProgressLoads) return undefined;
        const timer = setInterval(() => {
            loadBatches({ silent: true });
        }, 20000);
        return () => clearInterval(timer);
    }, [hasInProgressLoads, statusFilter, searchQuery, page]);

    const handleSort = (key) => {
        if (sortKey === key) {
            setSortDir((prev) => (prev === 'asc' ? 'desc' : 'asc'));
        } else {
            setSortKey(key);
            setSortDir(key === 'created_at' ? 'desc' : 'asc');
        }
    };

    const sortedBatches = useMemo(() => {
        const col = SORTABLE_COLUMNS.find((c) => c.key === sortKey);
        if (!col) return batches;

        const sorted = [...batches];
        const dir = sortDir === 'asc' ? 1 : -1;

        sorted.sort((a, b) => {
            const va = col.getValue(a);
            const vb = col.getValue(b);
            if (col.numeric) {
                return (va - vb) * dir;
            }
            if (va < vb) return -1 * dir;
            if (va > vb) return 1 * dir;
            return 0;
        });
        return sorted;
    }, [batches, sortKey, sortDir]);

    const stats = useMemo(() => {
        const active = batches.filter((b) => ACTIVE_STATUSES.includes(b.status)).length;
        const success = batches.filter((b) => SUCCESS_STATUSES.includes(b.status)).length;
        const failed = batches.filter((b) => b.status === 'FAILED').length;
        const records = batches.reduce((sum, b) => sum + (b.records_count || 0), 0);
        return { total, active, success, failed, records };
    }, [batches, total]);

    const pageIds = useMemo(() => sortedBatches.map((b) => b.batch_id), [sortedBatches]);
    const allPageSelected =
        pageIds.length > 0 && pageIds.every((id) => selectedIds.has(id));
    const somePageSelected = pageIds.some((id) => selectedIds.has(id));

    const toggleSelectAll = () => {
        setSelectedIds((prev) => {
            const next = new Set(prev);
            if (allPageSelected) {
                pageIds.forEach((id) => next.delete(id));
            } else {
                pageIds.forEach((id) => next.add(id));
            }
            return next;
        });
    };

    const toggleSelectOne = (batchId) => {
        setSelectedIds((prev) => {
            const next = new Set(prev);
            if (next.has(batchId)) next.delete(batchId);
            else next.add(batchId);
            return next;
        });
    };

    const handleDeleteSelected = () => {
        const ids = [...selectedIds];
        if (ids.length === 0) return;
        setConfirmModal({
            isOpen: true,
            title: 'Confirmar Eliminación',
            message: `¿Eliminar ${ids.length} batch${ids.length !== 1 ? 'es' : ''} seleccionado${ids.length !== 1 ? 's' : ''}? Esta acción no se puede deshacer.`,
            confirmText: 'Eliminar',
            cancelText: 'Cancelar',
            variant: 'danger',
            onConfirm: () => executeDeleteSelected(ids),
        });
    };

    const executeDeleteSelected = async (ids) => {
        setConfirmModal((prev) => ({ ...prev, isOpen: false }));
        setDeleting(true);
        setActionMessage(null);
        let shouldReload = false;
        let goPrevPage = false;
        try {
            const result = await uploadService.deleteBatches(ids);
            setActionMessage({
                type: 'success',
                text: result.message || `${result.deleted} batch(es) eliminado(s).`,
            });
            shouldReload = true;
            goPrevPage = page > 1 && ids.length >= batches.length;
        } catch (err) {
            setActionMessage({
                type: 'error',
                text: err.response?.data?.detail || 'No se pudieron eliminar los batches.',
            });
        } finally {
            setDeleting(false);
        }
        if (shouldReload) {
            if (goPrevPage) setPage((p) => Math.max(1, p - 1));
            else loadBatches();
        }
    };

    const handleDeleteAll = () => {
        if (total === 0) return;
        const scope = statusFilter || searchQuery ? ' que coincidan con los filtros actuales' : '';
        setConfirmModal({
            isOpen: true,
            title: 'Confirmar Eliminación',
            message: `¿Eliminar todos los batches${scope} (${total})? Esta acción no se puede deshacer.`,
            confirmText: 'Eliminar todos',
            cancelText: 'Cancelar',
            variant: 'danger',
            onConfirm: executeDeleteAll,
        });
    };

    const executeDeleteAll = async () => {
        setConfirmModal((prev) => ({ ...prev, isOpen: false }));
        setDeleting(true);
        setActionMessage(null);
        let shouldReload = false;
        try {
            const filters = {};
            if (statusFilter) filters.status = statusFilter;
            if (searchQuery) filters.search = searchQuery;
            const result = await uploadService.deleteAllBatches(filters);
            setActionMessage({
                type: 'success',
                text: result.message || `${result.deleted} batch(es) eliminado(s).`,
            });
            shouldReload = true;
        } catch (err) {
            const detail = err.response?.data?.detail;
            const message =
                typeof detail === 'string'
                    ? detail
                    : err.code === 'ECONNABORTED' || err.message?.includes('timeout')
                      ? 'La operación tardó demasiado. Revisa el listado; puede que ya se hayan eliminado.'
                      : 'No se pudieron eliminar los batches.';
            setActionMessage({ type: 'error', text: message });
        } finally {
            setDeleting(false);
        }
        if (shouldReload) {
            setPage(1);
            loadBatches();
        }
    };

    const handleViewProgress = (batchId) => {
        navigate(`/batches/${batchId}`);
    };

    const handleResume = async (batchId) => {
        try {
            await uploadService.resumePromotion(batchId);
            navigate(`/batches/${batchId}`);
        } catch (err) {
            console.error('API Error resuming batch:', err);
            alert(err.response?.data?.detail || 'No se pudo reanudar la promoción.');
        }
    };

    const handleCancel = (batchId, event) => {
        event?.stopPropagation();
        event?.preventDefault();

        setConfirmModal({
            isOpen: true,
            title: 'Confirmar Cancelación',
            message: '¿Cancelar este batch? Se detendrán los jobs en cola.',
            confirmText: 'Cancelar Batch',
            cancelText: 'Volver',
            variant: 'danger',
            onConfirm: () => executeCancel(batchId),
        });
    };

    const executeCancel = async (batchId) => {
        setConfirmModal((prev) => ({ ...prev, isOpen: false }));
        setActionMessage(null);
        setCancellingId(batchId);
        try {
            await uploadService.cancelBatch(batchId);
            setBatches((prev) =>
                prev.map((b) =>
                    b.batch_id === batchId
                        ? { ...b, status: 'CANCELLED', error_message: b.error_message || 'Cancelado por el usuario' }
                        : b
                )
            );
            setActionMessage({ type: 'success', text: 'Batch cancelado correctamente.' });
            await loadBatches();
        } catch (err) {
            const detail = err.response?.data?.detail;
            const message =
                typeof detail === 'string'
                    ? detail
                    : err.response?.status === 404
                      ? 'No se pudo cancelar: reinicia el backend (python run_app.py) para cargar el endpoint.'
                      : 'No se pudo cancelar el batch.';
            setActionMessage({ type: 'error', text: message });
        } finally {
            setCancellingId(null);
        }
    };

    return (
        <div className="page-container batches-page">
            <header className="batches-header">
                <div>
                    <h1 className="batches-title">Batches</h1>
                    <p className="batches-subtitle">
                        Administra y monitorea las cargas de archivos
                    </p>
                </div>
                <Button icon={RefreshCw} variant="secondary" onClick={loadBatches} loading={loading}>
                    Actualizar
                </Button>
            </header>

            {actionMessage && (
                <div
                    className={`batches-action-banner batches-action-banner--${actionMessage.type}`}
                    role="status"
                >
                    {actionMessage.text}
                    <button
                        type="button"
                        className="batches-action-banner__close"
                        onClick={() => setActionMessage(null)}
                        aria-label="Cerrar"
                    >
                        ×
                    </button>
                </div>
            )}

            <div className="catalog-dashboard batches-dashboard">
                <div className="catalog-dashboard__file summary-block">
                    <span className="summary-block__title">Resumen</span>
                    <div className="catalog-file-stats">
                        <div className="summary-card">
                            <div className="card-label">
                                <Layers size={14} aria-hidden />
                                Total
                            </div>
                            <span className="value">{stats.total.toLocaleString()}</span>
                        </div>
                        <div className="summary-card">
                            <div className="card-label">
                                <Loader2 size={14} aria-hidden />
                                En curso
                            </div>
                            <span className="value">{stats.active.toLocaleString()}</span>
                        </div>
                        <div className="summary-card">
                            <div className="card-label">
                                <CheckCircle2 size={14} aria-hidden />
                                Completados
                            </div>
                            <span className="value">{stats.success.toLocaleString()}</span>
                        </div>
                        <div className={`summary-card ${stats.failed > 0 ? 'batches-stat--failed' : ''}`}>
                            <div className="card-label">
                                <AlertTriangle size={14} aria-hidden />
                                Fallidos
                            </div>
                            <span className="value">{stats.failed.toLocaleString()}</span>
                        </div>
                    </div>
                </div>
                <div className="catalog-dashboard__target summary-block batches-filters-block">
                    <span className="summary-block__title">Filtros</span>
                    <div className="batches-filters">
                        <div className="batches-search">
                            <Search size={16} className="batches-search__icon" aria-hidden />
                            <input
                                type="text"
                                className="batches-search__input"
                                placeholder="Buscar por ID o fuente…"
                                value={filter}
                                onChange={(e) => setFilter(e.target.value)}
                            />
                        </div>
                        <select
                            className="batches-filter-select"
                            value={statusFilter}
                            onChange={(e) => setStatusFilter(e.target.value)}
                        >
                            <option value="">Todos los estados</option>
                            <option value="PENDING">Pending</option>
                            <option value="PENDING_PROCESS">Pending Process</option>
                            <option value="PROCESSING">Processing</option>
                            <option value="COMPLETED">Completed</option>
                            <option value="PARTIALLY_PROMOTED">Partially Promoted</option>
                            <option value="FAILED">Failed</option>
                            <option value="CANCELLED">Cancelled</option>
                            <option value="PROMOTED">Promoted</option>
                        </select>
                    </div>
                    <div className="batches-filters-meta">
                        <span>
                            {total} batch{total !== 1 ? 'es' : ''} en total
                            {total > 0 && ` · página ${page} de ${totalPages}`}
                        </span>
                        {stats.records > 0 && (
                            <span>{stats.records.toLocaleString()} registros en esta página</span>
                        )}
                    </div>
                </div>
            </div>

            {loading ? (
                <div className="batches-loading">
                    <LoadingSpinner message="Cargando batches…" />
                </div>
            ) : batches.length > 0 || total > 0 ? (
                <div className="preview-table-container batches-table-panel">
                    <div className="preview-table-header batches-table-header">
                        <div>
                            <h3>Listado de batches</h3>
                            <span className="preview-table-meta">
                                {sortedBatches.length} fila{sortedBatches.length !== 1 ? 's' : ''} ·{' '}
                                {PAGE_SIZE} por página
                            </span>
                        </div>
                        <div className="batches-bulk-actions">
                            <Button
                                variant="secondary"
                                icon={Trash2}
                                onClick={handleDeleteSelected}
                                disabled={selectedIds.size === 0 || deleting}
                                loading={deleting}
                            >
                                Eliminar seleccionados
                                {selectedIds.size > 0 ? ` (${selectedIds.size})` : ''}
                            </Button>
                            <Button
                                variant="danger"
                                icon={Trash2}
                                onClick={handleDeleteAll}
                                disabled={total === 0 || deleting}
                                loading={deleting}
                            >
                                Eliminar todos
                            </Button>
                        </div>
                    </div>
                    <div className="table-wrapper batches-table-wrapper">
                        <table className="preview-table batches-table">
                            <thead>
                                <tr>
                                    <th className="batches-th-checkbox">
                                        <input
                                            type="checkbox"
                                            className="batches-checkbox"
                                            checked={allPageSelected}
                                            ref={(el) => {
                                                if (el) el.indeterminate = somePageSelected && !allPageSelected;
                                            }}
                                            onChange={toggleSelectAll}
                                            aria-label="Seleccionar todos en esta página"
                                            disabled={deleting || pageIds.length === 0}
                                        />
                                    </th>
                                    <th className="preview-table__row-num">#</th>
                                    {SORTABLE_COLUMNS.map((col) => (
                                        <SortableTh
                                            key={col.key}
                                            columnKey={col.key}
                                            label={col.label}
                                            sortKey={sortKey}
                                            sortDir={sortDir}
                                            onSort={handleSort}
                                            className={
                                                col.numeric ? 'batch-numeric batches-th--numeric' : ''
                                            }
                                        />
                                    ))}
                                    <th className="batches-table__actions-col">Acciones</th>
                                </tr>
                            </thead>
                            <tbody>
                                {sortedBatches.map((batch, index) => {
                                    const canMonitor = MONITOR_STATUSES.includes(batch.status);
                                    const canResume = RESUMABLE_STATUSES.includes(batch.status);
                                    const canCancel = CANCELLABLE_STATUSES.includes(batch.status);
                                    const rowNum = (page - 1) * PAGE_SIZE + index + 1;

                                    return (
                                        <tr
                                            key={batch.batch_id}
                                            className={
                                                selectedIds.has(batch.batch_id)
                                                    ? 'batches-row--selected'
                                                    : ''
                                            }
                                        >
                                            <td className="batches-td-checkbox">
                                                <input
                                                    type="checkbox"
                                                    className="batches-checkbox"
                                                    checked={selectedIds.has(batch.batch_id)}
                                                    onChange={() => toggleSelectOne(batch.batch_id)}
                                                    aria-label={`Seleccionar batch ${batch.batch_id}`}
                                                    disabled={deleting}
                                                />
                                            </td>
                                            <td className="preview-table__row-num">{rowNum}</td>
                                            <td>
                                                <code
                                                    className="batch-id-code"
                                                    title={batch.batch_id}
                                                >
                                                    {batch.batch_id.substring(0, 8)}…
                                                </code>
                                            </td>
                                            <td
                                                className="batch-organization"
                                                title={batch.organization_name || batch.organization_id || ''}
                                            >
                                                {batch.organization_name || '—'}
                                            </td>
                                            <td className="batch-source" title={batch.source_name}>
                                                {batch.source_name || '—'}
                                            </td>
                                            <td>
                                                <BatchStatusCell
                                                    status={batch.status}
                                                    errorMessage={batch.error_message}
                                                />
                                            </td>
                                            <td className="batch-numeric">
                                                {batch.records_count?.toLocaleString() ?? 0}
                                            </td>
                                            <td className="batch-numeric">
                                                {formatFileSize(batch.file_size)}
                                            </td>
                                            <td className="batch-date" title={getBatchDisplayDate(batch) || ''}>
                                                {formatDate(getBatchDisplayDate(batch))}
                                            </td>
                                            <td
                                                className={`batch-numeric batch-duration${
                                                    batch.duration_in_progress
                                                        ? ' batch-duration--live'
                                                        : ''
                                                }`}
                                                title={getBatchDurationTitle(batch)}
                                            >
                                                {getBatchDurationLabel(batch)}
                                            </td>
                                            <td>
                                                <div className="batch-actions">
                                                    {canMonitor && (
                                                        <button
                                                            type="button"
                                                            className="batch-action-btn batch-action-btn--view"
                                                            onClick={() => handleViewProgress(batch.batch_id)}
                                                            title="Ver progreso"
                                                            aria-label="Ver progreso"
                                                        >
                                                            <Eye size={16} aria-hidden />
                                                        </button>
                                                    )}
                                                    {canResume && (
                                                        <button
                                                            type="button"
                                                            className="batch-action-btn batch-action-btn--resume"
                                                            onClick={() => handleResume(batch.batch_id)}
                                                            title="Reanudar promoción"
                                                            aria-label="Reanudar promoción"
                                                        >
                                                            <Play size={16} aria-hidden />
                                                        </button>
                                                    )}
                                                    {canCancel && (
                                                        <button
                                                            type="button"
                                                            className="batch-action-btn batch-action-btn--cancel"
                                                            onClick={(e) => handleCancel(batch.batch_id, e)}
                                                            title="Cancelar batch"
                                                            aria-label="Cancelar batch"
                                                            disabled={cancellingId === batch.batch_id}
                                                        >
                                                            {cancellingId === batch.batch_id ? (
                                                                <Loader2 size={16} className="batch-action-btn__spin" aria-hidden />
                                                            ) : (
                                                                <XCircle size={16} aria-hidden />
                                                            )}
                                                        </button>
                                                    )}
                                                    {!canMonitor && !canResume && !canCancel && (
                                                        <span className="batch-no-actions">—</span>
                                                    )}
                                                </div>
                                            </td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    </div>
                    {totalPages > 1 && (
                        <nav className="batches-pagination" aria-label="Paginación de batches">
                            <Button
                                variant="secondary"
                                icon={ChevronLeft}
                                onClick={() => setPage((p) => Math.max(1, p - 1))}
                                disabled={page <= 1 || loading}
                            >
                                Anterior
                            </Button>
                            <span className="batches-pagination__info">
                                Página {page} de {totalPages}
                            </span>
                            <Button
                                variant="secondary"
                                icon={ChevronRight}
                                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                                disabled={page >= totalPages || loading}
                            >
                                Siguiente
                            </Button>
                        </nav>
                    )}
                </div>
            ) : (
                <div className="preview-table-container preview-table-container--empty batches-empty">
                    <h3>Sin batches</h3>
                    <p>No se encontraron batches con los filtros actuales.</p>
                </div>
            )}

            {/* Modal de confirmación custom del sistema */}
            <Modal
                isOpen={confirmModal.isOpen}
                onClose={() => setConfirmModal(prev => ({ ...prev, isOpen: false }))}
                title={confirmModal.title}
                footer={
                    <>
                        <Button
                            variant="secondary"
                            onClick={() => setConfirmModal(prev => ({ ...prev, isOpen: false }))}
                        >
                            {confirmModal.cancelText}
                        </Button>
                        <Button
                            variant={confirmModal.variant}
                            onClick={confirmModal.onConfirm}
                        >
                            {confirmModal.confirmText}
                        </Button>
                    </>
                }
            >
                <div style={{ padding: '8px 0', fontSize: '15px', color: 'var(--color-text-secondary)', lineHeight: '1.5' }}>
                    {confirmModal.message}
                </div>
            </Modal>
        </div>
    );
};

export default Batches;
