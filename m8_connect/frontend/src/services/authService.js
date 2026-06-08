import axios from 'axios';
import api from './api';
import {
    setAuthSession,
    clearAuthSession,
    getToken,
    getRefreshToken,
    getStoredUser,
    isRemembered,
    updateAccessToken,
} from './authStorage';

const envUrl = import.meta.env.VITE_API_URL;
const API_URL =
    envUrl !== undefined && envUrl !== ''
        ? envUrl
        : import.meta.env.DEV
          ? ''
          : 'http://127.0.0.1:8000';

export {
    getToken,
    getRefreshToken,
    getStoredUser,
    setAuthSession,
    clearAuthSession,
    isRemembered,
    updateAccessToken,
};

export const login = async (email, password) => {
    const response = await api.post('/api/v1/auth/login', { email, password });
    return response.data;
};

export const getCurrentUser = async () => {
    const response = await api.get('/api/v1/auth/me');
    return response.data;
};

export const refreshAccessToken = async () => {
    const refreshToken = getRefreshToken();
    if (!refreshToken) {
        throw new Error('No hay refresh token');
    }

    const response = await axios.post(
        `${API_URL}/api/v1/auth/refresh`,
        { refresh_token: refreshToken },
        {
            headers: { 'Content-Type': 'application/json' },
            timeout: 30000,
        }
    );

    const { access_token: accessToken } = response.data;
    updateAccessToken(accessToken);
    return response.data;
};
