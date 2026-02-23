import React from 'react';
import './StatusBadge.css';

const StatusBadge = ({ status, className = '' }) => {
    const getStatusInfo = (status) => {
        const statusLower = status?.toLowerCase() || '';

        switch (statusLower) {
            case 'completed':
            case 'success':
            case 'passed':
                return { variant: 'success', label: status };
            case 'failed':
            case 'error':
            case 'rejected':
                return { variant: 'error', label: status };
            case 'pending':
            case 'queued':
            case 'waiting':
                return { variant: 'pending', label: status };
            case 'processing':
            case 'in_progress':
            case 'running':
                return { variant: 'processing', label: status };
            default:
                return { variant: 'default', label: status };
        }
    };

    const { variant, label } = getStatusInfo(status);

    return (
        <span className={`status-badge status-badge-${variant} ${className}`}>
            <span className="status-badge-dot"></span>
            {label}
        </span>
    );
};

export default StatusBadge;
