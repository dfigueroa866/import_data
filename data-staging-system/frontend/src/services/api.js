import axios from 'axios';
import { getToken, getRefreshToken } from './authStorage';
import { refreshAccessToken } from './authService';
import { notifyApiActivity } from './sessionActivity';

// Dev: empty baseURL → requests go to Vite (localhost:5173) and proxy /api to 127.0.0.1:8000.
// Prod/build: set VITE_API_URL or defaults to 127.0.0.1 (avoid localhost on Windows IPv6).
const envUrl = import.meta.env.VITE_API_URL;
const API_URL =
    envUrl !== undefined && envUrl !== ''
        ? envUrl
        : import.meta.env.DEV
          ? ''
          : 'http://127.0.0.1:8000';

let unauthorizedHandler = null;
let refreshPromise = null;

export const setUnauthorizedHandler = (handler) => {
    unauthorizedHandler = handler;
};

const api = axios.create({
    baseURL: API_URL,
    headers: {
        'Content-Type': 'application/json',
    },
    timeout: 120000,
});

const shouldAttemptRefresh = (error) => {
    const status = error.response?.status;
    const requestUrl = error.config?.url || '';
    const isAuthRoute =
        requestUrl.includes('/auth/login')
        || requestUrl.includes('/auth/refresh');

    return status === 401 && !error.config?.skipAuthRefresh && !isAuthRoute;
};

// Request interceptor
api.interceptors.request.use(
    (config) => {
        const token = getToken();
        if (token) {
            config.headers.Authorization = `Bearer ${token}`;
        }
        return config;
    },
    (error) => Promise.reject(error)
);

// Response interceptor
api.interceptors.response.use(
    (response) => {
        notifyApiActivity();
        return response;
    },
    async (error) => {
        const originalRequest = error.config;

        if (shouldAttemptRefresh(error) && originalRequest && !originalRequest._retry) {
            originalRequest._retry = true;

            if (!getRefreshToken()) {
                unauthorizedHandler?.();
                return Promise.reject(error);
            }

            try {
                if (!refreshPromise) {
                    refreshPromise = refreshAccessToken().finally(() => {
                        refreshPromise = null;
                    });
                }
                await refreshPromise;
                originalRequest.headers.Authorization = `Bearer ${getToken()}`;
                return api(originalRequest);
            } catch (refreshError) {
                unauthorizedHandler?.();
                return Promise.reject(refreshError);
            }
        }

        if (error.response?.status === 401) {
            const requestUrl = originalRequest?.url || '';
            if (
                !requestUrl.includes('/auth/login')
                && !requestUrl.includes('/auth/refresh')
            ) {
                unauthorizedHandler?.();
            }
        }

        if (error.response) {
            console.error('API Error:', error.response.data);
        } else if (error.request) {
            console.error('Network Error:', error.request);
        } else {
            console.error('Error:', error.message);
        }
        return Promise.reject(error);
    }
);

export default api;
