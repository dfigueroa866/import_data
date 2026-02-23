import React, { useState, useEffect } from 'react';
import { Search, RefreshCw } from 'lucide-react';
import Card from '../components/Card';
import StatusBadge from '../components/StatusBadge';
import LoadingSpinner from '../components/LoadingSpinner';
import Button from '../components/Button';
import { uploadService } from '../services/uploadService';
import './Batches.css';

const Batches = () => {
    const [batches, setBatches] = useState([]);
    const [loading, setLoading] = useState(true);
    const [filter, setFilter] = useState('');
    const [statusFilter, setStatusFilter] = useState('');

    useEffect(() => {
        loadBatches();
    }, [statusFilter]);

    const loadBatches = async () => {
        try {
            setLoading(true);
            const params = statusFilter ? { status: statusFilter } : {};
            const data = await uploadService.listBatches(params);
            setBatches(data.batches || []);
        } catch (error) {
            console.error('Error loading batches:', error);
        } finally {
            setLoading(false);
        }
    };

    const filteredBatches = batches.filter((batch) => {
        const searchTerm = filter.toLowerCase();
        return (
            batch.batch_id?.toLowerCase().includes(searchTerm) ||
            batch.source_name?.toLowerCase().includes(searchTerm)
        );
    });

    return (
        <div className="page-container">
            <div className="page-header">
                <div>
                    <h1 className="page-title">Batches</h1>
                    <p className="page-subtitle">Manage and monitor all file upload batches</p>
                </div>
                <Button icon={RefreshCw} onClick={loadBatches}>
                    Refresh
                </Button>
            </div>

            <Card>
                {/* Filters */}
                <div className="filters-container">
                    <div className="search-box">
                        <Search size={20} className="search-icon" />
                        <input
                            type="text"
                            className="search-input"
                            placeholder="Search batches..."
                            value={filter}
                            onChange={(e) => setFilter(e.target.value)}
                        />
                    </div>

                    <select
                        className="filter-select"
                        value={statusFilter}
                        onChange={(e) => setStatusFilter(e.target.value)}
                    >
                        <option value="">All Status</option>
                        <option value="PENDING">Pending</option>
                        <option value="PROCESSING">Processing</option>
                        <option value="COMPLETED">Completed</option>
                        <option value="FAILED">Failed</option>
                    </select>
                </div>

                {/* Batches Table */}
                {loading ? (
                    <LoadingSpinner message="Loading batches..." />
                ) : filteredBatches.length > 0 ? (
                    <div className="table-container">
                        <table className="data-table">
                            <thead>
                                <tr>
                                    <th>Batch ID</th>
                                    <th>Source Name</th>
                                    <th>Status</th>
                                    <th>Records</th>
                                    <th>File Size</th>
                                    <th>Created</th>
                                    <th>Completed</th>
                                </tr>
                            </thead>
                            <tbody>
                                {filteredBatches.map((batch) => (
                                    <tr key={batch.batch_id}>
                                        <td>
                                            <code className="batch-id">{batch.batch_id.substring(0, 8)}...</code>
                                        </td>
                                        <td className="source-name">{batch.source_name || 'N/A'}</td>
                                        <td>
                                            <StatusBadge status={batch.status} />
                                        </td>
                                        <td>{batch.records_count?.toLocaleString() || 0}</td>
                                        <td>{batch.file_size ? `${(batch.file_size / 1024).toFixed(2)} KB` : 'N/A'}</td>
                                        <td>{new Date(batch.created_at).toLocaleString()}</td>
                                        <td>
                                            {batch.completed_at
                                                ? new Date(batch.completed_at).toLocaleString()
                                                : '-'}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                ) : (
                    <div className="empty-state">
                        <p>No batches found</p>
                    </div>
                )}
            </Card>
        </div>
    );
};

export default Batches;
