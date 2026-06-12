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
import {
  Badge,
  LoadingSpinner,
  PageHeader,
  Button,
  Modal,
  Alert,
  Input,
  Select,
  DataTableShell,
  DataTable,
  DataTableHead,
  DataTableBody,
  DataTableRow,
  DataTableTh,
  DataTableTd,
  DataTableRowNum,
  DataTablePagination,
  SummaryGrid,
  SummaryBlock,
} from '../components/ui';
import { formatDate, formatNumber, formatDurationSeconds, EMPTY } from '../lib/format';
import { cn } from '../lib/utils';
import { uploadService } from '../services/uploadService';
import useSessionLoadGuard from '../hooks/useSessionLoadGuard';

const ACTIVE_STATUSES = ['PROCESSING', 'PENDING', 'PENDING_PROCESS', 'PENDING_MAPPING', 'PENDING_PREVIEW'];
const RESUMABLE_STATUSES = ['FAILED', 'PARTIALLY_PROMOTED'];
const MONITOR_STATUSES = [...ACTIVE_STATUSES, 'COMPLETED', ...RESUMABLE_STATUSES];
const CANCELLABLE_STATUSES = [...ACTIVE_STATUSES, ...RESUMABLE_STATUSES];
const SUCCESS_STATUSES = ['COMPLETED', 'PROMOTED', 'PARTIALLY_PROMOTED'];

const getBatchDisplayDate = (batch) =>
    batch?.display_at || batch?.created_at || batch?.started_at || batch?.completed_at || null;

const getBatchDateMs = (batch) => {
    const raw = getBatchDisplayDate(batch);
    if (!raw) return 0;
    const ms = new Date(raw).getTime();
    return Number.isNaN(ms) ? 0 : ms;
};

const PAGE_SIZE = 10;

const SORTABLE_COLUMNS = [
    { key: 'batch_id', label: 'Batch ID', getValue: (b) => (b.batch_id || '').toLowerCase() },
    { key: 'source_name', label: 'Fuente', getValue: (b) => (b.source_name || '').toLowerCase() },
    { key: 'status', label: 'Estado', getValue: (b) => (b.status || '').toLowerCase() },
    {
        key: 'records_count',
        label: 'Registros',
        getValue: (b) => Number(b.records_count) || 0,
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

const SortableTh = ({ columnKey, label, sortKey, sortDir, onSort, numeric }) => {
    const active = sortKey === columnKey;
    const Icon = active ? (sortDir === 'asc' ? ArrowUp : ArrowDown) : ArrowUpDown;
    return (
        <DataTableTh numeric={numeric}>
            <button
                type="button"
                className={cn(
                  'inline-flex items-center gap-1 font-semibold bg-transparent border-0 p-0 cursor-pointer',
                  active ? 'text-brand-600' : 'text-inherit hover:text-brand-600',
                  numeric && 'w-full justify-end'
                )}
                onClick={() => onSort(columnKey)}
                aria-sort={active ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}
            >
                <span>{label}</span>
                <Icon size={14} className={cn('flex-shrink-0', active ? 'opacity-100' : 'opacity-55')} aria-hidden />
            </button>
        </DataTableTh>
    );
};

const getBatchDurationLabel = (batch) => {
    if (batch?.duration_label) return batch.duration_label;
    if (batch?.duration_seconds == null) return EMPTY;
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
                <Badge status={status} />
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
        <div className="flex flex-1 flex-col gap-5 overflow-y-auto p-8 max-w-6xl mx-auto w-full scrollbar-thin">
            <PageHeader
                icon={Layers}
                title="Lotes"
                subtitle="Administra y monitorea las cargas de archivos"
                action={
                    <Button icon={RefreshCw} variant="secondary" onClick={loadBatches} loading={loading}>
                        Actualizar
                    </Button>
                }
            />

            {actionMessage && (
                <Alert variant={actionMessage.type === 'success' ? 'success' : 'error'} onClose={() => setActionMessage(null)}>
                    {actionMessage.text}
                </Alert>
            )}

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <SummaryBlock title="Resumen">
                    <SummaryGrid columns={2} className="lg:grid-cols-4">
                        {[
                            { label: 'Total', value: formatNumber(stats.total), icon: Layers },
                            { label: 'En curso', value: formatNumber(stats.active), icon: Loader2 },
                            { label: 'Completados', value: formatNumber(stats.success), icon: CheckCircle2 },
                            { label: 'Fallidos', value: formatNumber(stats.failed), icon: AlertTriangle, variant: stats.failed > 0 ? 'danger' : 'default' },
                        ].map((s) => (
                            <div key={s.label} className="text-center lg:text-left">
                                <div className="flex items-center justify-center lg:justify-start gap-1 text-xs text-slate-500 mb-1">
                                    <s.icon size={14} />{s.label}
                                </div>
                                <p className={cn('text-xl font-bold m-0', s.variant === 'danger' && 'text-red-600')}>{s.value}</p>
                            </div>
                        ))}
                    </SummaryGrid>
                </SummaryBlock>
                <SummaryBlock title="Filtros" accent>
                    <div className="flex flex-col gap-3">
                        <Input
                            type="text"
                            icon={Search}
                            placeholder="Buscar por ID o fuente…"
                            value={filter}
                            onChange={(e) => setFilter(e.target.value)}
                        />
                        <Select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
                            <option value="">Todos los estados</option>
                            <option value="PENDING">Pending</option>
                            <option value="PENDING_PROCESS">Pending Process</option>
                            <option value="PROCESSING">Processing</option>
                            <option value="COMPLETED">Completed</option>
                            <option value="PARTIALLY_PROMOTED">Partially Promoted</option>
                            <option value="FAILED">Failed</option>
                            <option value="CANCELLED">Cancelled</option>
                            <option value="PROMOTED">Promoted</option>
                        </Select>
                    </div>
                    <div className="flex flex-wrap gap-4 mt-3 pt-3 border-t border-dashed border-[#e2e8f0] text-xs text-slate-500">
                        <span>{total} lote{total !== 1 ? 's' : ''} en total{total > 0 && ` · página ${page} de ${totalPages}`}</span>
                        {stats.records > 0 && <span>{formatNumber(stats.records)} registros en esta página</span>}
                    </div>
                </SummaryBlock>
            </div>

            {loading ? (
                <div className="batches-loading">
                    <LoadingSpinner message="Cargando batches…" />
                </div>
            ) : batches.length > 0 || total > 0 ? (
                <DataTableShell
                    title="Listado de lotes"
                    meta={`${sortedBatches.length} fila${sortedBatches.length !== 1 ? 's' : ''} · ${PAGE_SIZE} por página`}
                    maxHeight="min(520px, calc(100vh - 340px))"
                    headerActions={
                        <>
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
                        </>
                    }
                >
                        <DataTable>
                            <DataTableHead>
                                <tr>
                                    <DataTableTh className="w-10 text-center">
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
                                    </DataTableTh>
                                    <DataTableTh className="w-10 text-center">#</DataTableTh>
                                    {SORTABLE_COLUMNS.map((col) => (
                                        <SortableTh
                                            key={col.key}
                                            columnKey={col.key}
                                            label={col.label}
                                            sortKey={sortKey}
                                            sortDir={sortDir}
                                            onSort={handleSort}
                                            numeric={col.numeric}
                                        />
                                    ))}
                                    <DataTableTh className="whitespace-nowrap">Acciones</DataTableTh>
                                </tr>
                            </DataTableHead>
                            <DataTableBody>
                                {sortedBatches.map((batch, index) => {
                                    const canMonitor = MONITOR_STATUSES.includes(batch.status);
                                    const canResume = RESUMABLE_STATUSES.includes(batch.status);
                                    const canCancel = CANCELLABLE_STATUSES.includes(batch.status);
                                    const rowNum = (page - 1) * PAGE_SIZE + index + 1;

                                    return (
                                        <DataTableRow key={batch.batch_id} selected={selectedIds.has(batch.batch_id)}>
                                            <DataTableTd className="text-center">
                                                <input
                                                    type="checkbox"
                                                    className="accent-brand-600"
                                                    checked={selectedIds.has(batch.batch_id)}
                                                    onChange={() => toggleSelectOne(batch.batch_id)}
                                                    aria-label={`Seleccionar batch ${batch.batch_id}`}
                                                    disabled={deleting}
                                                />
                                            </DataTableTd>
                                            <DataTableRowNum>{rowNum}</DataTableRowNum>
                                            <DataTableTd mono className="whitespace-nowrap text-xs">
                                                {batch.batch_id}
                                            </DataTableTd>
                                            <DataTableTd className="max-w-[140px] truncate font-medium" title={batch.source_name}>
                                                {batch.source_name || EMPTY}
                                            </DataTableTd>
                                            <DataTableTd>
                                                <BatchStatusCell status={batch.status} errorMessage={batch.error_message} />
                                            </DataTableTd>
                                            <DataTableTd numeric>{formatNumber(batch.records_count ?? 0)}</DataTableTd>
                                            <DataTableTd className="whitespace-nowrap text-xs" title={getBatchDisplayDate(batch) || ''}>
                                                {formatDate(getBatchDisplayDate(batch))}
                                            </DataTableTd>
                                            <DataTableTd numeric className={batch.duration_in_progress ? 'text-brand-600 font-medium' : ''} title={getBatchDurationTitle(batch)}>
                                                {getBatchDurationLabel(batch)}
                                            </DataTableTd>
                                            <DataTableTd>
                                                <div className="flex items-center gap-1">
                                                    {canMonitor && (
                                                        <button type="button" className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-[#e2e8f0] hover:bg-blue-50 hover:text-brand-700 hover:border-blue-200" onClick={() => handleViewProgress(batch.batch_id)} title="Ver progreso" aria-label="Ver progreso">
                                                            <Eye size={16} />
                                                        </button>
                                                    )}
                                                    {canResume && (
                                                        <button type="button" className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-blue-200 text-brand-600 hover:bg-blue-50" onClick={() => handleResume(batch.batch_id)} title="Reanudar promoción" aria-label="Reanudar promoción">
                                                            <Play size={16} />
                                                        </button>
                                                    )}
                                                    {canCancel && (
                                                        <button type="button" className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-[#e2e8f0] hover:bg-red-50 hover:text-red-600 hover:border-red-200 disabled:opacity-50" onClick={(e) => handleCancel(batch.batch_id, e)} title="Cancelar batch" aria-label="Cancelar batch" disabled={cancellingId === batch.batch_id}>
                                                            {cancellingId === batch.batch_id ? <Loader2 size={16} className="animate-spin" /> : <XCircle size={16} />}
                                                        </button>
                                                    )}
                                                    {!canMonitor && !canResume && !canCancel && <span className="text-slate-400">—</span>}
                                                </div>
                                            </DataTableTd>
                                        </DataTableRow>
                                    );
                                })}
                            </DataTableBody>
                        </DataTable>
                    {totalPages > 1 && (
                        <DataTablePagination>
                            <Button variant="secondary" icon={ChevronLeft} onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page <= 1 || loading}>Anterior</Button>
                            <span className="text-sm text-slate-500 min-w-[8rem] text-center">Página {page} de {totalPages}</span>
                            <Button variant="secondary" icon={ChevronRight} onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={page >= totalPages || loading}>Siguiente</Button>
                        </DataTablePagination>
                    )}
                </DataTableShell>
            ) : (
                <DataTableShell empty emptyTitle="Sin lotes" emptyDescription="No se encontraron lotes con los filtros actuales." />
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
