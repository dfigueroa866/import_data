import React, { useState } from 'react';
import { useLocation, Navigate } from 'react-router-dom';
import { LogIn, Lock, Mail, Eye, EyeOff } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import LoadingSpinner from '../components/LoadingSpinner';
import './Login.css';

const Login = () => {
    const location = useLocation();
    const { login, isAuthenticated, isInitializing } = useAuth();
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [remember, setRemember] = useState(false);
    const [showPassword, setShowPassword] = useState(false);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');

    const redirectTo =
        location.state?.from && location.state.from !== '/login'
            ? location.state.from
            : '/';

    if (isInitializing) {
        return (
            <div className="login-page login-page--loading">
                <LoadingSpinner />
                <p>Verificando sesión...</p>
            </div>
        );
    }

    if (isAuthenticated) {
        return <Navigate to={redirectTo} replace />;
    }

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError('');

        if (!email.trim() || !password) {
            setError('Introduce tu correo y contraseña.');
            return;
        }

        try {
            setLoading(true);
            await login(email.trim(), password, remember);
        } catch (err) {
            const detail = err.response?.data?.detail;
            if (typeof detail === 'string') {
                setError(detail);
            } else if (err.response?.status === 404) {
                setError('Servicio de login no disponible. Reinicia el backend (python run_app.py).');
            } else {
                setError('No se pudo iniciar sesión. Inténtalo de nuevo.');
            }
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="login-page">
            <div className="login-card">
                <header className="login-header">
                    <h1 className="login-title">Bienvenido de nuevo</h1>
                    <p className="login-subtitle">
                        Inicia sesión para acceder a tu centro de comando de cadena de suministro.
                    </p>
                </header>

                <form className="login-form" onSubmit={handleSubmit}>
                    <div className="login-field">
                        <label htmlFor="email" className="login-label">
                            Correo electrónico
                        </label>
                        <div className="login-input-wrapper">
                            <Mail size={18} className="login-input-icon" />
                            <input
                                id="email"
                                type="email"
                                className="login-input"
                                placeholder="nombre@empresa.com"
                                value={email}
                                onChange={(e) => setEmail(e.target.value)}
                                autoComplete="email"
                                disabled={loading}
                            />
                        </div>
                    </div>

                    <div className="login-field">
                        <label htmlFor="password" className="login-label">
                            Contraseña
                        </label>
                        <div className="login-input-wrapper login-input-wrapper--password">
                            <Lock size={18} className="login-input-icon" />
                            <input
                                id="password"
                                type={showPassword ? 'text' : 'password'}
                                className="login-input login-input--with-toggle"
                                placeholder="••••••••"
                                value={password}
                                onChange={(e) => setPassword(e.target.value)}
                                autoComplete="current-password"
                                disabled={loading}
                            />
                            <button
                                type="button"
                                className="login-password-toggle"
                                onClick={() => setShowPassword((prev) => !prev)}
                                disabled={loading}
                                aria-label={showPassword ? 'Ocultar contraseña' : 'Mostrar contraseña'}
                                title={showPassword ? 'Ocultar contraseña' : 'Mostrar contraseña'}
                            >
                                {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                            </button>
                        </div>
                    </div>

                    <div className="login-options">
                        <label className="login-remember">
                            <input
                                type="checkbox"
                                checked={remember}
                                onChange={(e) => setRemember(e.target.checked)}
                                disabled={loading}
                            />
                            <span>Recordarme</span>
                        </label>
                        <button type="button" className="login-forgot" disabled={loading}>
                            ¿Olvidaste tu contraseña?
                        </button>
                    </div>

                    {error && <div className="login-error">{error}</div>}

                    <button type="submit" className="login-submit" disabled={loading}>
                        <LogIn size={20} />
                        <span>{loading ? 'Iniciando sesión...' : 'Iniciar sesión'}</span>
                    </button>
                </form>
            </div>
        </div>
    );
};

export default Login;
