import React from 'react';
import { Navigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { hasPermission, isConnectAdmin } from '../utils/permissions';

const PermissionRoute = ({ children, permission, adminOnly = false, fallback = '/' }) => {
  const { user, isInitializing } = useAuth();

  if (isInitializing) {
    return null;
  }

  if (adminOnly && !isConnectAdmin(user)) {
    return <Navigate to={fallback} replace />;
  }

  if (permission && !isConnectAdmin(user) && !hasPermission(user?.permissions, permission)) {
    return <Navigate to={fallback} replace />;
  }

  return children;
};

export default PermissionRoute;
