/** Persistencia y aplicación del tema claro/oscuro (DESIGN_STYLE.md §11). */

export const THEME_STORAGE_KEY = 'm8_connect_theme';

export const THEMES = {
  LIGHT: 'light',
  DARK: 'dark',
};

export function getStoredTheme() {
  try {
    const stored = localStorage.getItem(THEME_STORAGE_KEY);
    if (stored === THEMES.LIGHT || stored === THEMES.DARK) {
      return stored;
    }
  } catch {
    /* ignore */
  }
  return null;
}

export function resolveInitialTheme() {
  const stored = getStoredTheme();
  if (stored) {
    return stored;
  }
  if (typeof window !== 'undefined' && window.matchMedia('(prefers-color-scheme: dark)').matches) {
    return THEMES.DARK;
  }
  return THEMES.LIGHT;
}

export function applyTheme(theme) {
  const root = document.documentElement;
  const isDark = theme === THEMES.DARK;
  root.classList.toggle('dark', isDark);
  root.setAttribute('data-theme', isDark ? THEMES.DARK : THEMES.LIGHT);
  root.style.colorScheme = isDark ? 'dark' : 'light';
}

export function persistTheme(theme) {
  try {
    localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    /* ignore */
  }
}
