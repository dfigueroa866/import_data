import React, { useState, useEffect } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import {
    LayoutDashboard,
    Upload,
    Database,
    Activity,
    Layers,
    Settings2,
    Sun,
    Moon,
    LogIn,
    LogOut
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import './Sidebar.css';

const Sidebar = () => {
    const navigate = useNavigate();
    const { user, isAuthenticated, logout } = useAuth();
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

    const handleLogout = () => {
        logout();
        navigate('/login', { replace: true, state: null });
    };

    const navItems = [
        { path: '/', icon: LayoutDashboard, label: 'Dashboard' },
        { path: '/upload', icon: Upload, label: 'Upload' },
        { path: '/catalogs', icon: Settings2, label: 'Catálogos' },
        { path: '/batches', icon: Layers, label: 'Batches' },
        { path: '/monitoring', icon: Activity, label: 'Monitoring' },
    ];

    return (
        <aside className="sidebar glass-card">
            <div className="sidebar-header">
                <NavLink
                    to="/"
                    className="sidebar-logo"
                    aria-label="Ir a la página principal"
                    title="Inicio"
                >
                    <Database size={32} className="logo-icon" />
                    <span className="sidebar-title gradient-text">M8 Connect</span>
                </NavLink>
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
                {isAuthenticated ? (
                    <>
                        <div className="sidebar-user">
                            <span className="sidebar-user-name">
                                {user?.display_name || user?.email}
                            </span>
                            {user?.display_name && (
                                <span className="sidebar-user-email">{user.email}</span>
                            )}
                        </div>
                        <button
                            type="button"
                            onClick={handleLogout}
                            className="sidebar-logout-btn"
                        >
                            <LogOut size={16} />
                            <span>Cerrar sesión</span>
                        </button>
                    </>
                ) : (
                    <NavLink to="/login" className="sidebar-login-link">
                        <LogIn size={16} />
                        <span>Iniciar sesión</span>
                    </NavLink>
                )}
                <div className="sidebar-footer-actions">
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
            </div>
        </aside>
    );
};

export default Sidebar;
