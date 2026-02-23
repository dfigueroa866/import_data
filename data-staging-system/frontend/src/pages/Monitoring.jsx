import React, { useState, useEffect } from 'react';
import { Activity, TrendingUp, Clock } from 'lucide-react';
import Card from '../components/Card';
import StatusBadge from '../components/StatusBadge';
import LoadingSpinner from '../components/LoadingSpinner';
import { monitoringService } from '../services/monitoringService';
import './Monitoring.css';

const Monitoring = () => {
    const [loading, setLoading] = useState(true);
    const [systemStatus, setSystemStatus] = useState(null);
    const [health, setHealth] = useState(null);

    useEffect(() => {
        loadMonitoringData();
        // Refresh every 30 seconds
        const interval = setInterval(loadMonitoringData, 30000);
        return () => clearInterval(interval);
    }, []);

    const loadMonitoringData = async () => {
        try {
            setLoading(true);
            const [statusData, healthData] = await Promise.all([
                monitoringService.getSystemStatus(),
                monitoringService.getHealth(),
            ]);

            setSystemStatus(statusData);
            setHealth(healthData);
        } catch (error) {
            console.error('Error loading monitoring data:', error);
        } finally {
            setLoading(false);
        }
    };

    if (loading) {
        return (
            <div className="page-container">
                <LoadingSpinner size="lg" message="Loading monitoring data..." />
            </div>
        );
    }

    const stats = systemStatus?.batch_statistics || {};

    return (
        <div className="page-container">
            <div className="page-header">
                <h1 className="page-title">Monitoring</h1>
                <p className="page-subtitle">System health and performance metrics</p>
            </div>

            {/* System Health */}
            <Card title="System Health" className="mb-lg">
                <div className="health-grid">
                    <div className="health-item">
                        <div className="health-item-header">
                            <Activity size={20} />
                            <span>Status</span>
                        </div>
                        <StatusBadge status={health?.status || 'unknown'} />
                    </div>

                    <div className="health-item">
                        <div className="health-item-header">
                            <Clock size={20} />
                            <span>Last Check</span>
                        </div>
                        <span className="health-value">
                            {health?.timestamp
                                ? new Date(health.timestamp).toLocaleTimeString()
                                : 'N/A'}
                        </span>
                    </div>

                    <div className="health-item">
                        <div className="health-item-header">
                            <TrendingUp size={20} />
                            <span>Environment</span>
                        </div>
                        <span className="health-value">{health?.environment || 'N/A'}</span>
                    </div>
                </div>
            </Card>

            {/* Batch Statistics */}
            <div className="monitoring-grid">
                <Card title="Batch Statistics">
                    <div className="stats-list">
                        <div className="stat-row">
                            <span className="stat-row-label">Total Batches</span>
                            <span className="stat-row-value">{stats.total_batches || 0}</span>
                        </div>
                        <div className="stat-row">
                            <span className="stat-row-label">Completed</span>
                            <span className="stat-row-value stat-row-value-success">
                                {stats.completed_batches || 0}
                            </span>
                        </div>
                        <div className="stat-row">
                            <span className="stat-row-label">Failed</span>
                            <span className="stat-row-value stat-row-value-error">
                                {stats.failed_batches || 0}
                            </span>
                        </div>
                        <div className="stat-row stat-row-highlight">
                            <span className="stat-row-label">Success Rate</span>
                            <span className="stat-row-value">
                                {stats.success_rate?.toFixed(1) || 0}%
                            </span>
                        </div>
                    </div>
                </Card>

                <Card title="Database">
                    <div className="stats-list">
                        <div className="stat-row">
                            <span className="stat-row-label">Status</span>
                            <StatusBadge
                                status={health?.database_connected ? 'connected' : 'disconnected'}
                            />
                        </div>
                        <div className="stat-row">
                            <span className="stat-row-label">Type</span>
                            <span className="stat-row-value">{health?.database?.type || 'Unknown'}</span>
                        </div>
                    </div>
                </Card>
            </div>
        </div>
    );
};

export default Monitoring;
