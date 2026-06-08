import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import ProtectedRoute from './components/ProtectedRoute';
import Sidebar from './components/Sidebar';
import Dashboard from './pages/Dashboard';
import Login from './pages/Login';
import UploadLanding from './pages/UploadLanding';
import CatalogAdmin from './pages/CatalogAdmin';
import UploadWizard from './components/wizard/UploadWizard';
import CatalogUploadWizard from './components/wizard/CatalogUploadWizard';
import Batches from './pages/Batches';
import BatchProgress from './pages/BatchProgress';
import Monitoring from './pages/Monitoring';
import './App.css';

function AppLayout() {
  return (
    <ProtectedRoute>
      <div className="app-container">
        <Sidebar />
        <main className="main-content">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/upload" element={<UploadLanding />} />
            <Route path="/upload/history" element={<UploadWizard />} />
            <Route path="/upload/catalog" element={<CatalogUploadWizard />} />
            <Route path="/catalogs" element={<CatalogAdmin />} />
            <Route path="/batches" element={<Batches />} />
            <Route path="/batches/:batchId" element={<BatchProgress />} />
            <Route path="/monitoring" element={<Monitoring />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
    </ProtectedRoute>
  );
}

function App() {
  return (
    <AuthProvider>
      <Router>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/*" element={<AppLayout />} />
        </Routes>
      </Router>
    </AuthProvider>
  );
}

export default App;
