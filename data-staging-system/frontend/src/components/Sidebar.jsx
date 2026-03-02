import React, { useState, useEffect } from 'react';
import { NavLink } from 'react-router-dom';
import {
    LayoutDashboard,
    Upload,
    Database,
    Activity,
    Layers,
    Sun,
    Moon
} from 'lucide-react';
import './Sidebar.css';

const Sidebar = () => {
    // Theme state
    const [theme, setTheme] = useState(() => {
        return localStorage.getItem('theme') || 'dark';
    });

    // Apply theme effect
    useEffect(() => {
        document.documentElement.setAttribute('data-theme', theme);
        localStorage.setItem('theme', theme);
    }, [theme]);

    const toggleTheme = () => {
        setTheme(prev => prev === 'dark' ? 'light' : 'dark');
    };

    const navItems = [
        { path: '/', icon: LayoutDashboard, label: 'Dashboard' },
        { path: '/upload', icon: Upload, label: 'Upload' },
        { path: '/batches', icon: Layers, label: 'Batches' },
        { path: '/staging', icon: Database, label: 'Staging' },
        { path: '/monitoring', icon: Activity, label: 'Monitoring' },
    ];

    return (
        <aside className="sidebar glass-card">
            <div className="sidebar-header">
                <div className="sidebar-logo">
                    <Database size={32} className="logo-icon" />
                    <h1 className="sidebar-title gradient-text">Data Staging</h1>
                </div>
            </div>

            <nav className="sidebar-nav">
                {navItems.map((item) => (
                    <NavLink
                        key={item.path}
                        to={item.path}
                        onClick={(e) => {
                            if (item.path === '/upload' && window.location.pathname === '/upload') {
                                window.location.reload();
                            }
                        }}
                        className={({ isActive }) =>
                            `sidebar-link ${isActive ? 'sidebar-link-active' : ''}`
                        }
                    >
                        <item.icon size={20} className="sidebar-icon" />
                        <span className="sidebar-label">{item.label}</span>
                    </NavLink>
                ))}
            </nav>

            <div className="sidebar-footer">
                <button
                    onClick={toggleTheme}
                    className="theme-toggle-btn"
                    aria-label="Toggle Theme"
                    title={`Switch to ${theme === 'dark' ? 'Light' : 'Dark'} Mode`}
                >
                    {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
                </button>
                <div className="sidebar-version">v2.0.0</div>
            </div>
        </aside>
    );
};

export default Sidebar;
