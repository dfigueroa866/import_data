import React, { createContext, useCallback, useContext, useMemo, useState } from 'react';
import {
  THEMES,
  applyTheme,
  persistTheme,
  resolveInitialTheme,
} from '../lib/theme';

const ThemeContext = createContext(null);

export function ThemeProvider({ children }) {
  const [theme, setThemeState] = useState(() => resolveInitialTheme());

  const setTheme = useCallback((next) => {
    const resolved = next === THEMES.DARK ? THEMES.DARK : THEMES.LIGHT;
    setThemeState(resolved);
    applyTheme(resolved);
    persistTheme(resolved);
  }, []);

  const toggleTheme = useCallback(() => {
    setTheme(theme === THEMES.DARK ? THEMES.LIGHT : THEMES.DARK);
  }, [setTheme, theme]);

  const value = useMemo(
    () => ({
      theme,
      isDark: theme === THEMES.DARK,
      setTheme,
      toggleTheme,
    }),
    [theme, setTheme, toggleTheme]
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) {
    throw new Error('useTheme debe usarse dentro de ThemeProvider');
  }
  return ctx;
}
