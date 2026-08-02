import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import ProtectedRoute from './components/ProtectedRoute';
import PermissionRoute from './components/PermissionRoute';
import Sidebar from './components/layout/Sidebar';
import AppHeader from './components/layout/AppHeader';
import Dashboard from './pages/Dashboard';
import Login from './pages/Login';
import UploadLanding from './pages/UploadLanding';
import CatalogAdmin from './pages/CatalogAdmin';
import HistoryAdmin from './pages/HistoryAdmin';
import RolesAdmin from './pages/RolesAdmin';
import UploadWizard from './components/wizard/UploadWizard';
import CatalogUploadWizard from './components/wizard/CatalogUploadWizard';
import Batches from './pages/Batches';
import BatchProgress from './pages/BatchProgress';
import Monitoring from './pages/Monitoring';
import IncrementalDashboard from './pages/IncrementalDashboard';
import IncrementalSchedule from './pages/IncrementalSchedule';
import IncrementalOrganizations from './pages/IncrementalOrganizations';
import IncrementalRuns from './pages/IncrementalRuns';
import IncrementalRunDetail from './pages/IncrementalRunDetail';
import ThemeToggle from './components/ui/ThemeToggle';

function AppLayout() {
  return (
    <ProtectedRoute>
      <div className="flex h-screen overflow-hidden bg-[#f1f5f9] dark:bg-[#0f172a]">
        <Sidebar />
        <div className="flex min-w-0 flex-1 flex-col ml-52 max-md:ml-16">
          <AppHeader />
          <main className="flex flex-1 flex-col overflow-hidden">
            <Routes>
              <Route
                path="/"
                element={(
                  <PermissionRoute permission="menus.panel">
                    <Dashboard />
                  </PermissionRoute>
                )}
              />
              <Route
                path="/upload"
                element={(
                  <PermissionRoute permission="menus.upload">
                    <UploadLanding />
                  </PermissionRoute>
                )}
              />
              <Route
                path="/upload/history"
                element={(
                  <PermissionRoute permission="upload.history">
                    <UploadWizard />
                  </PermissionRoute>
                )}
              />
              <Route
                path="/upload/catalog"
                element={(
                  <PermissionRoute permission="upload.catalogs">
                    <CatalogUploadWizard />
                  </PermissionRoute>
                )}
              />
              <Route
                path="/config/catalogs"
                element={(
                  <PermissionRoute permission="config.catalogs_view" adminOnly={false}>
                    <CatalogAdmin />
                  </PermissionRoute>
                )}
              />
              <Route
                path="/config/history"
                element={(
                  <PermissionRoute permission="config.history_view" adminOnly={false}>
                    <HistoryAdmin />
                  </PermissionRoute>
                )}
              />
              <Route
                path="/config/roles"
                element={(
                  <PermissionRoute adminOnly>
                    <RolesAdmin />
                  </PermissionRoute>
                )}
              />
              <Route path="/catalogs" element={<Navigate to="/config/catalogs" replace />} />
              <Route
                path="/batches"
                element={(
                  <PermissionRoute permission="menus.batches">
                    <Batches />
                  </PermissionRoute>
                )}
              />
              <Route
                path="/batches/:batchId"
                element={(
                  <PermissionRoute permission="menus.batches">
                    <BatchProgress />
                  </PermissionRoute>
                )}
              />
              <Route
                path="/incremental"
                element={(
                  <PermissionRoute permission="menus.incremental">
                    <IncrementalDashboard />
                  </PermissionRoute>
                )}
              />
              <Route
                path="/incremental/schedule"
                element={(
                  <PermissionRoute permission="config.incremental_view" adminOnly={false}>
                    <IncrementalSchedule />
                  </PermissionRoute>
                )}
              />
              <Route
                path="/incremental/organizations"
                element={(
                  <PermissionRoute permission="config.incremental_view" adminOnly={false}>
                    <IncrementalOrganizations />
                  </PermissionRoute>
                )}
              />
              <Route
                path="/incremental/runs"
                element={(
                  <PermissionRoute permission="menus.incremental">
                    <IncrementalRuns />
                  </PermissionRoute>
                )}
              />
              <Route
                path="/incremental/runs/:runId"
                element={(
                  <PermissionRoute permission="menus.incremental">
                    <IncrementalRunDetail />
                  </PermissionRoute>
                )}
              />
              <Route
                path="/monitoring"
                element={(
                  <PermissionRoute permission="menus.monitoring">
                    <Monitoring />
                  </PermissionRoute>
                )}
              />
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
        <ThemeToggle />
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/*" element={<AppLayout />} />
        </Routes>
      </Router>
    </AuthProvider>
  );
}

export default App;
