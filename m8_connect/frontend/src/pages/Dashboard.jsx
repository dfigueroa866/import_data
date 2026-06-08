import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Activity, Upload as UploadIcon, Database, TrendingUp } from 'lucide-react';
import Card from '../components/Card';
import StatusBadge from '../components/StatusBadge';
import LoadingSpinner from '../components/LoadingSpinner';
import Button from '../components/Button';
import { monitoringService } from '../services/monitoringService';
import { uploadService } from '../services/uploadService';
import './Dashboard.css';

const Dashboard = () => {
    const [loading, setLoading] = useState(true);
    const [systemStatus, setSystemStatus] = useState(null);
    const [recentBatches, setRecentBatches] = useState([]);
    const [health, setHealth] = useState(null);

    useEffect(() => {
        loadDashboardData();
    }, []);

    const loadDashboardData = async () => {
        try {
            setLoading(true);
            const [statusData, batchesData, healthData] = await Promise.all([
                monitoringService.getSystemStatus(),
                uploadService.listBatches({ limit: 5 }),
                monitoringService.getHealth(),
            ]);

            setSystemStatus(statusData);
            setRecentBatches(batchesData.batches || []);
            setHealth(healthData);
        } catch (error) {
            console.error('Error loading dashboard:', error);
        } finally {
            setLoading(false);
        }
    };

    if (loading) {
        return (
            <div className="page-container">
                <LoadingSpinner size="lg" message="Loading dashboard..." />
            </div>
        );
    }

    const stats = systemStatus?.batch_statistics || {};

    return (
        <div className="page-container">
            <div className="page-header">
                <h1 className="page-title">Dashboard</h1>
                <p className="page-subtitle">System overview and recent activity</p>
            </div>

            {/* Stats Grid */}
            <div className="stats-grid">
                <Card className="stat-card hover-lift">
                    <div className="stat-icon stat-icon-primary">
                        <Database size={24} />
                    </div>
                    <div className="stat-content">
                        <p className="stat-label">Total Batches</p>
                        <p className="stat-value">{stats.total_batches || 0}</p>
                    </div>
                </Card>

                <Card className="stat-card hover-lift">
                    <div className="stat-icon stat-icon-success">
                        <TrendingUp size={24} />
                    </div>
                    <div className="stat-content">
                        <p className="stat-label">Completed</p>
                        <p className="stat-value">{stats.completed_batches || 0}</p>
                    </div>
                </Card>

                <Card className="stat-card hover-lift">
                    <div className="stat-icon stat-icon-danger">
                        <Activity size={24} />
                    </div>
                    <div className="stat-content">
                        <p className="stat-label">Failed</p>
                        <p className="stat-value">{stats.failed_batches || 0}</p>
                    </div>
                </Card>

                <Card className="stat-card hover-lift">
                    <div className="stat-icon stat-icon-info">
                        <UploadIcon size={24} />
                    </div>
                    <div className="stat-content">
                        <p className="stat-label">Success Rate</p>
                        <p className="stat-value">{stats.success_rate?.toFixed(1) || 0}%</p>
                    </div>
                </Card>
            </div>

            {/* System Health */}
            <Card title="System Health" className="mt-lg">
                <div className="health-status">
                    <StatusBadge status={health?.status || 'unknown'} />
                    <span className="health-label">
                        {health?.status === 'healthy' ? 'All systems operational' : 'System issues detected'}
                    </span>
                </div>
            </Card>

            {/* Recent Batches */}
            <Card title="Recent Batches" subtitle="Latest file uploads" className="mt-lg">
                {recentBatches.length > 0 ? (
                    <div className="batches-table-container">
                        <table className="batches-table">
                            <thead>
                                <tr>
                                    <th>Batch ID</th>
                                    <th>Source</th>
                                    <th>Status</th>
                                    <th>Records</th>
                                    <th>Created</th>
                                </tr>
                            </thead>
                            <tbody>
                                {recentBatches.map((batch) => (
                                    <tr key={batch.batch_id}>
                                        <td>
                                            <code>{batch.batch_id.substring(0, 8)}...</code>
                                        </td>
                                        <td>{batch.source_name || 'N/A'}</td>
                                        <td>
                                            <StatusBadge status={batch.status} />
                                        </td>
                                        <td>{batch.records_count || 0}</td>
                                        <td>{new Date(batch.created_at).toLocaleDateString()}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                ) : (
                    <p className="empty-state">No batches found</p>
                )}

                <div className="card-footer">
                    <Link to="/batches">
                        <Button variant="ghost">View All Batches →</Button>
                    </Link>
                </div>
            </Card>
        </div>
    );
};

export default Dashboard;
