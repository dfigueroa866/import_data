import React, {
    createContext,
    useContext,
    useMemo,
    useState,
    useCallback,
    useEffect,
    useRef,
} from 'react';
import {
    clearAuthSession,
    getStoredUser,
    getToken,
    getRefreshToken,
    isTokenExpired,
    isTokenExpiringSoon,
    isRemembered,
    setAuthSession,
} from '../services/authStorage';
import {
    login as loginRequest,
    getCurrentUser,
    refreshAccessToken,
} from '../services/authService';
import { setUnauthorizedHandler } from '../services/api';
import { registerTouchActivity } from '../services/sessionActivity';
import {
    SESSION_INACTIVITY_MS,
    SESSION_CHECK_INTERVAL_MS,
    SESSION_ACTIVITY_THROTTLE_MS,
} from '../constants/sessionConfig';

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
    const [token, setToken] = useState(() => getToken());
    const [user, setUser] = useState(() => getStoredUser());
    const [authStatus, setAuthStatus] = useState(() => (getToken() || getRefreshToken() ? 'checking' : 'guest'));

    const lastActivityRef = useRef(Date.now());
    const loadProcessCountRef = useRef(0);

    const touchActivity = useCallback(() => {
        lastActivityRef.current = Date.now();
    }, []);

    const registerLoadProcess = useCallback(() => {
        loadProcessCountRef.current += 1;
        return () => {
            loadProcessCountRef.current = Math.max(0, loadProcessCountRef.current - 1);
        };
    }, []);

    const logout = useCallback(() => {
        clearAuthSession();
        setToken(null);
        setUser(null);
        setAuthStatus('guest');
    }, []);

    const applySession = useCallback((accessToken, refreshToken, profile, remember) => {
        setAuthSession(accessToken, refreshToken, profile, remember);
        setToken(accessToken);
        setUser(profile);
        setAuthStatus('authenticated');
        touchActivity();
    }, [touchActivity]);

    const login = useCallback(async (email, password, remember = true) => {
        const data = await loginRequest(email, password);
        applySession(data.access_token, data.refresh_token, data.user, remember);
        return data;
    }, [applySession]);

    const tryRefreshSession = useCallback(async () => {
        const refreshToken = getRefreshToken();
        if (!refreshToken) {
            throw new Error('Sin refresh token');
        }
        const data = await refreshAccessToken();
        const profile = await getCurrentUser();
        const remember = isRemembered();
        setAuthSession(data.access_token, refreshToken, profile, remember);
        setToken(data.access_token);
        setUser(profile);
        touchActivity();
        return data.access_token;
    }, [touchActivity]);

    useEffect(() => {
        registerTouchActivity(touchActivity);
        return () => registerTouchActivity(null);
    }, [touchActivity]);

    useEffect(() => {
        const storedToken = getToken();
        const refreshToken = getRefreshToken();

        if (!storedToken && !refreshToken) {
            setAuthStatus('guest');
            return undefined;
        }

        let cancelled = false;

        const bootstrap = async () => {
            try {
                let activeToken = storedToken;

                if (!activeToken || isTokenExpired(activeToken)) {
                    activeToken = await tryRefreshSession();
                }

                const profile = await getCurrentUser();
                if (cancelled) return;

                const remember = isRemembered();
                setAuthSession(activeToken, refreshToken, profile, remember);
                setToken(activeToken);
                setUser(profile);
                setAuthStatus('authenticated');
                touchActivity();
            } catch {
                if (cancelled) return;
                clearAuthSession();
                setToken(null);
                setUser(null);
                setAuthStatus('guest');
            }
        };

        bootstrap();

        return () => {
            cancelled = true;
        };
    }, [touchActivity, tryRefreshSession]);

    useEffect(() => {
        setUnauthorizedHandler(logout);
        return () => setUnauthorizedHandler(null);
    }, [logout]);

    useEffect(() => {
        if (authStatus !== 'authenticated') return undefined;

        touchActivity();

        let lastThrottledTouch = 0;
        const onUserActivity = () => {
            const now = Date.now();
            if (now - lastThrottledTouch >= SESSION_ACTIVITY_THROTTLE_MS) {
                lastThrottledTouch = now;
                touchActivity();
            }
        };

        const events = ['mousemove', 'mousedown', 'keydown', 'touchstart', 'scroll', 'click'];
        events.forEach((eventName) => {
            window.addEventListener(eventName, onUserActivity, { passive: true });
        });

        const intervalId = window.setInterval(async () => {
            const idleFor = Date.now() - lastActivityRef.current;
            const loadActive = loadProcessCountRef.current > 0;

            if (idleFor >= SESSION_INACTIVITY_MS && !loadActive) {
                logout();
                return;
            }

            const currentToken = getToken();
            const userActive = idleFor < SESSION_INACTIVITY_MS;
            const shouldRefresh =
                loadActive
                || !currentToken
                || isTokenExpired(currentToken)
                || (userActive && isTokenExpiringSoon(currentToken));

            if (!shouldRefresh) return;

            try {
                await tryRefreshSession();
            } catch {
                if (idleFor >= SESSION_INACTIVITY_MS && !loadActive) {
                    logout();
                }
            }
        }, SESSION_CHECK_INTERVAL_MS);

        return () => {
            events.forEach((eventName) => {
                window.removeEventListener(eventName, onUserActivity);
            });
            window.clearInterval(intervalId);
        };
    }, [authStatus, logout, touchActivity, tryRefreshSession]);

    const value = useMemo(
        () => ({
            token,
            user,
            isAuthenticated: authStatus === 'authenticated',
            isInitializing: authStatus === 'checking',
            login,
            logout,
            touchActivity,
            registerLoadProcess,
        }),
        [token, user, authStatus, login, logout, touchActivity, registerLoadProcess]
    );

    return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export const useAuth = () => {
    const context = useContext(AuthContext);
    if (!context) {
        throw new Error('useAuth must be used within AuthProvider');
    }
    return context;
};

export default AuthContext;
