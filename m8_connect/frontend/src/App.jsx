import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import ProtectedRoute from './components/ProtectedRoute';
import Sidebar from './components/layout/Sidebar';
import AppHeader from './components/layout/AppHeader';
import Dashboard from './pages/Dashboard';
import Login from './pages/Login';
import UploadLanding from './pages/UploadLanding';
import CatalogAdmin from './pages/CatalogAdmin';
import UploadWizard from './components/wizard/UploadWizard';
import CatalogUploadWizard from './components/wizard/CatalogUploadWizard';
import Batches from './pages/Batches';
import BatchProgress from './pages/BatchProgress';
import Monitoring from './pages/Monitoring';

function AppLayout() {
  return (
    <ProtectedRoute>
      <div className="flex h-screen overflow-hidden bg-[#f1f5f9] dark:bg-[#0f172a]">
        <Sidebar />
        <div className="flex min-w-0 flex-1 flex-col ml-52 max-md:ml-16">
          <AppHeader />
          <main className="flex flex-1 flex-col overflow-hidden">
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
