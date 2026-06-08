import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import LoadingSpinner from './LoadingSpinner';
import './ProtectedRoute.css';

const ProtectedRoute = ({ children }) => {
    const { isAuthenticated, isInitializing } = useAuth();
    const location = useLocation();

    if (isInitializing) {
        return (
            <div className="auth-route-loading">
                <LoadingSpinner />
                <p>Verificando sesión...</p>
            </div>
        );
    }

    if (!isAuthenticated) {
        return <Navigate to="/login" replace state={{ from: location.pathname }} />;
    }

    return children;
};

export default ProtectedRoute;
