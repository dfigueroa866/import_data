import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import Sidebar from './components/Sidebar';
import Dashboard from './pages/Dashboard';
import UploadWizard from './components/wizard/UploadWizard';
import Batches from './pages/Batches';
import Staging from './pages/Staging';
import Monitoring from './pages/Monitoring';
import './App.css';

function App() {
  return (
    <Router>
      <div className="app-container">
        <Sidebar />
        <main className="main-content">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/upload" element={<UploadWizard />} />
            <Route path="/batches" element={<Batches />} />
            <Route path="/staging" element={<Staging />} />
            <Route path="/monitoring" element={<Monitoring />} />
          </Routes>
        </main>
      </div>
    </Router>
  );
}

export default App;
