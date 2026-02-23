import React, { useState, useEffect } from 'react';
import { Database, ArrowRight } from 'lucide-react';
import Card from '../components/Card';
import Button from '../components/Button';
import LoadingSpinner from '../components/LoadingSpinner';
import Modal from '../components/Modal';
import { stagingService } from '../services/stagingService';
import './Staging.css';

const Staging = () => {
    const [tables, setTables] = useState([]);
    const [loading, setLoading] = useState(true);
    const [showModal, setShowModal] = useState(false);
    const [selectedTable, setSelectedTable] = useState(null);
    const [promotionConfig, setPromotionConfig] = useState({
        batchId: '',
        stagingTable: '',
        productionTable: '',
        productionSchema: 'm8_schema',
        dedupColumns: '',
    });

    useEffect(() => {
        loadTables();
    }, []);

    const loadTables = async () => {
        try {
            setLoading(true);
            const data = await stagingService.listTables();
            setTables(data.tables || []);
        } catch (error) {
            console.error('Error loading tables:', error);
        } finally {
            setLoading(false);
        }
    };

    const handlePromote = async () => {
        try {
            await stagingService.processToProduction(promotionConfig);
            alert('Staging-to-production started successfully!');
            setShowModal(false);
        } catch (error) {
            alert('Error: ' + (error.response?.data?.detail || 'Promotion failed'));
        }
    };

    return (
        <div className="page-container">
            <div className="page-header">
                <div>
                    <h1 className="page-title">Staging Operations</h1>
                    <p className="page-subtitle">Manage staging tables and promote to production</p>
                </div>
                <Button icon={ArrowRight} onClick={() => setShowModal(true)}>
                    Promote to Production
                </Button>
            </div>

            {loading ? (
                <LoadingSpinner message="Loading staging tables..." />
            ) : (
                <div className="tables-grid">
                    {tables.map((table) => (
                        <Card
                            key={table.table_name}
                            className="table-card hover-lift"
                            hoverable
                        >
                            <div className="table-info">
                                <Database size={32} className="table-icon" />
                                <div>
                                    <h3 className="table-name">{table.table_name}</h3>
                                    <div className="table-stats">
                                        <span>{table.column_count || 0} columns</span>
                                        <span>•</span>
                                        <span>{table.record_count?.toLocaleString() || 0} records</span>
                                    </div>
                                </div>
                            </div>
                        </Card>
                    ))}

                    {tables.length === 0 && (
                        <div className="empty-state">
                            <Database size={64} className="empty-icon" />
                            <p>No staging tables found</p>
                        </div>
                    )}
                </div>
            )}

            {/* Promote Modal */}
            <Modal
                isOpen={showModal}
                onClose={() => setShowModal(false)}
                title="Promote to Production"
                footer={
                    <>
                        <Button variant="secondary" onClick={() => setShowModal(false)}>
                            Cancel
                        </Button>
                        <Button variant="primary" onClick={handlePromote}>
                            Start Promotion
                        </Button>
                    </>
                }
            >
                <div className="modal-form">
                    <div className="form-group">
                        <label className="form-label">Batch ID</label>
                        <input
                            type="text"
                            className="form-input"
                            value={promotionConfig.batchId}
                            onChange={(e) =>
                                setPromotionConfig({ ...promotionConfig, batchId: e.target.value })
                            }
                            placeholder="Enter batch ID"
                        />
                    </div>

                    <div className="form-group">
                        <label className="form-label">Staging Table</label>
                        <input
                            type="text"
                            className="form-input"
                            value={promotionConfig.stagingTable}
                            onChange={(e) =>
                                setPromotionConfig({ ...promotionConfig, stagingTable: e.target.value })
                            }
                            placeholder="e.g., stage_products"
                        />
                    </div>

                    <div className="form-group">
                        <label className="form-label">Production Table</label>
                        <input
                            type="text"
                            className="form-input"
                            value={promotionConfig.productionTable}
                            onChange={(e) =>
                                setPromotionConfig({ ...promotionConfig, productionTable: e.target.value })
                            }
                            placeholder="e.g., products"
                        />
                    </div>

                    <div className="form-group">
                        <label className="form-label">Production Schema</label>
                        <input
                            type="text"
                            className="form-input"
                            value={promotionConfig.productionSchema}
                            onChange={(e) =>
                                setPromotionConfig({ ...promotionConfig, productionSchema: e.target.value })
                            }
                            placeholder="e.g., m8_schema"
                        />
                    </div>

                    <div className="form-group">
                        <label className="form-label">Dedup Columns (comma-separated)</label>
                        <input
                            type="text"
                            className="form-input"
                            value={promotionConfig.dedupColumns}
                            onChange={(e) =>
                                setPromotionConfig({ ...promotionConfig, dedupColumns: e.target.value })
                            }
                            placeholder="e.g., product_id"
                        />
                    </div>
                </div>
            </Modal>
        </div>
    );
};

export default Staging;
