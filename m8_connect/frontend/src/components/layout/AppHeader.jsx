import React from 'react';
import { useAuth } from '../../context/AuthContext';

const AppHeader = () => {
  const { user } = useAuth();

  return (
    <header className="flex h-12 flex-shrink-0 items-center justify-between border-b border-white/10 bg-[#0f172a] px-6">
      <span className="font-display text-sm font-medium text-slate-300">
        Centro de operaciones
      </span>
      {user && (
        <span className="max-w-[220px] truncate text-sm text-slate-200">
          {user.display_name || user.email}
        </span>
      )}
    </header>
  );
};

export default AppHeader;
