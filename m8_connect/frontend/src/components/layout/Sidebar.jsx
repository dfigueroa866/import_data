import React, { useEffect, useState } from 'react';
import { NavLink, useLocation, useNavigate } from 'react-router-dom';
import {
  LayoutDashboard,
  Upload,
  Database,
  Activity,
  Layers,
  Settings2,
  LogIn,
  LogOut,
  BookOpen,
  History,
  ChevronDown,
} from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { cn } from '../../lib/utils';

const navItems = [
  { path: '/', icon: LayoutDashboard, label: 'Panel' },
  { path: '/upload', icon: Upload, label: 'Cargas' },
  { path: '/batches', icon: Layers, label: 'Lotes' },
  { path: '/monitoring', icon: Activity, label: 'Monitoreo' },
];

const configNav = {
  label: 'Configuración',
  icon: Settings2,
  children: [
    { path: '/config/catalogs', icon: BookOpen, label: 'Catálogos' },
    { path: '/config/history', icon: History, label: 'Historia' },
  ],
};

const isConfigPath = (pathname) =>
  pathname === '/catalogs'
  || pathname.startsWith('/config/catalogs')
  || pathname.startsWith('/config/history');

const Sidebar = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, isAuthenticated, logout } = useAuth();
  const [configOpen, setConfigOpen] = useState(() => isConfigPath(location.pathname));

  useEffect(() => {
    if (isConfigPath(location.pathname)) {
      setConfigOpen(true);
    }
  }, [location.pathname]);

  const handleLogout = () => {
    logout();
    navigate('/login', { replace: true, state: null });
  };

  const configActive = isConfigPath(location.pathname);

  return (
    <aside className="fixed left-0 top-0 z-10 flex h-screen w-52 flex-col border-r border-[#e2e8f0] bg-white shadow-sm dark:border-[#334155] dark:bg-slate-800">
      <div className="p-3 pb-2">
        <NavLink to="/" className="flex items-center gap-2 rounded-lg p-1 hover:opacity-90" title="Inicio">
          <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary text-white flex-shrink-0">
            <Database size={20} />
          </span>
          <span className="font-display text-sm font-bold tracking-tight text-slate-900 dark:text-slate-100 hidden md:inline">
            M8 Connect
          </span>
        </NavLink>
      </div>

      <nav className="flex-1 overflow-y-auto px-2 py-1 scrollbar-thin">
        <span className="px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-slate-400 hidden md:block">
          Navegación
        </span>
        {navItems.slice(0, 2).map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            onClick={() => {
              if (item.path === '/upload' && window.location.pathname === '/upload') {
                window.location.reload();
              }
            }}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors mb-0.5',
                isActive
                  ? 'bg-blue-50 text-brand-500 dark:bg-blue-950/40 dark:text-blue-400'
                  : 'text-slate-600 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-700 dark:hover:text-slate-100'
              )
            }
          >
            <item.icon size={16} className="flex-shrink-0" />
            <span className="hidden md:inline">{item.label}</span>
          </NavLink>
        ))}

        <div className="mb-0.5">
          <button
            type="button"
            onClick={() => setConfigOpen((open) => !open)}
            className={cn(
              'flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
              configActive
                ? 'bg-blue-50 text-brand-500 dark:bg-blue-950/40 dark:text-blue-400'
                : 'text-slate-600 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-700 dark:hover:text-slate-100'
            )}
            aria-expanded={configOpen}
          >
            <configNav.icon size={16} className="flex-shrink-0" />
            <span className="hidden md:inline flex-1 text-left">{configNav.label}</span>
            <ChevronDown
              size={14}
              className={cn(
                'hidden md:block flex-shrink-0 transition-transform text-slate-400',
                configOpen && 'rotate-180'
              )}
            />
          </button>
          {configOpen && (
            <div className="mt-0.5 space-y-0.5 pl-2 md:pl-4">
              {configNav.children.map((item) => (
                <NavLink
                  key={item.path}
                  to={item.path}
                  className={({ isActive }) =>
                    cn(
                      'flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
                      isActive
                        ? 'bg-blue-50 text-brand-500 dark:bg-blue-950/40 dark:text-blue-400'
                        : 'text-slate-600 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-700 dark:hover:text-slate-100'
                    )
                  }
                >
                  <item.icon size={15} className="flex-shrink-0 opacity-80" />
                  <span className="hidden md:inline">{item.label}</span>
                </NavLink>
              ))}
            </div>
          )}
        </div>

        {navItems.slice(2).map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors mb-0.5',
                isActive
                  ? 'bg-blue-50 text-brand-500 dark:bg-blue-950/40 dark:text-blue-400'
                  : 'text-slate-600 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-700 dark:hover:text-slate-100'
              )
            }
          >
            <item.icon size={16} className="flex-shrink-0" />
            <span className="hidden md:inline">{item.label}</span>
          </NavLink>
        ))}
      </nav>

      <div className="border-t border-[#e2e8f0] dark:border-[#334155] p-3 flex flex-col gap-2">
        {isAuthenticated ? (
          <>
            <div className="px-1 hidden md:block">
              <p className="text-sm font-medium text-slate-900 dark:text-slate-100 truncate m-0">
                {user?.display_name || user?.email}
              </p>
              {user?.display_name && (
                <p className="text-xs text-slate-500 truncate m-0">{user.email}</p>
              )}
            </div>
            <button
              type="button"
              onClick={handleLogout}
              className="flex items-center gap-2 w-full rounded-lg border border-[#e2e8f0] dark:border-[#334155] px-3 py-2 text-sm text-slate-600 hover:text-red-600 hover:border-red-200 hover:bg-red-50 dark:text-slate-400 dark:hover:bg-red-950/30 transition-colors"
            >
              <LogOut size={16} />
              <span className="hidden md:inline">Cerrar sesión</span>
            </button>
          </>
        ) : (
          <NavLink
            to="/login"
            className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-slate-600 hover:bg-blue-50 hover:text-brand-600"
          >
            <LogIn size={16} />
            <span className="hidden md:inline">Iniciar sesión</span>
          </NavLink>
        )}
        <p className="text-center text-[10px] font-mono text-slate-400 hidden md:block m-0">v2.0.0</p>
      </div>
    </aside>
  );
};

export default Sidebar;
