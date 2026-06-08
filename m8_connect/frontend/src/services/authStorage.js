const TOKEN_KEY = 'm8_access_token';
const REFRESH_KEY = 'm8_refresh_token';
const USER_KEY = 'm8_user';
const REMEMBER_KEY = 'm8_remember';

export const isTokenExpired = (token) => {
    if (!token) return true;
    try {
        const payload = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')));
        if (!payload.exp) return false;
        return Date.now() >= payload.exp * 1000;
    } catch {
        return true;
    }
};

export const isTokenExpiringSoon = (token, withinMs = 2 * 60 * 1000) => {
    if (!token) return true;
    try {
        const payload = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')));
        if (!payload.exp) return false;
        return payload.exp * 1000 - Date.now() <= withinMs;
    } catch {
        return true;
    }
};

export const getToken = () => {
    return localStorage.getItem(TOKEN_KEY) || sessionStorage.getItem(TOKEN_KEY);
};

export const getRefreshToken = () => {
    return localStorage.getItem(REFRESH_KEY) || sessionStorage.getItem(REFRESH_KEY);
};

export const getStoredUser = () => {
    const raw = localStorage.getItem(USER_KEY) || sessionStorage.getItem(USER_KEY);
    if (!raw) return null;
    try {
        return JSON.parse(raw);
    } catch {
        return null;
    }
};

export const isRemembered = () => {
    return Boolean(localStorage.getItem(REMEMBER_KEY) || localStorage.getItem(TOKEN_KEY));
};

export const setAuthSession = (accessToken, refreshToken, user, remember = true) => {
    clearAuthSession();
    const storage = remember ? localStorage : sessionStorage;
    storage.setItem(TOKEN_KEY, accessToken);
    if (refreshToken) {
        storage.setItem(REFRESH_KEY, refreshToken);
    }
    storage.setItem(USER_KEY, JSON.stringify(user));
    storage.setItem(REMEMBER_KEY, remember ? '1' : '0');
};

export const updateAccessToken = (accessToken) => {
    const storage = isRemembered() ? localStorage : sessionStorage;
    storage.setItem(TOKEN_KEY, accessToken);
};

export const clearAuthSession = () => {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(REFRESH_KEY);
    localStorage.removeItem(USER_KEY);
    localStorage.removeItem(REMEMBER_KEY);
    sessionStorage.removeItem(TOKEN_KEY);
    sessionStorage.removeItem(REFRESH_KEY);
    sessionStorage.removeItem(USER_KEY);
    sessionStorage.removeItem(REMEMBER_KEY);
};
