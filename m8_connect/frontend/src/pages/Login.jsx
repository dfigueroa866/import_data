import React, { useState, useEffect } from 'react';
import { useLocation, Navigate } from 'react-router-dom';
import { LogIn, Lock, Mail, Eye, EyeOff, Database } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { Button, FormField, Input, Alert, LoadingSpinner } from '../components/ui';

const HERO_SLIDES = [
  { title: 'Visibilidad de extremo a extremo', text: 'Centraliza cargas, catálogos y lotes en un solo centro de operaciones.' },
  { title: 'Datos listos para producción', text: 'Pipelines ETL confiables con seguimiento en tiempo real.' },
  { title: 'Cadena de suministro conectada', text: 'Integra fuentes heterogéneas y mantén la calidad de tus datos.' },
];

const Login = () => {
  const location = useLocation();
  const { login, isAuthenticated, isInitializing } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [remember, setRemember] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [slideIndex, setSlideIndex] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => setSlideIndex((p) => (p + 1) % HERO_SLIDES.length), 6000);
    return () => clearInterval(timer);
  }, []);

  const redirectTo = location.state?.from && location.state.from !== '/login' ? location.state.from : '/';

  if (isInitializing) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-[#f3f4f6] dark:bg-[#111827]">
        <LoadingSpinner message="Verificando sesión…" />
      </div>
    );
  }

  if (isAuthenticated) return <Navigate to={redirectTo} replace />;

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
      if (typeof detail === 'string') setError(detail);
      else if (err.response?.status === 404) setError('Servicio de login no disponible. Reinicia el backend (python run_app.py).');
      else setError('No se pudo iniciar sesión. Inténtalo de nuevo.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen bg-[#f3f4f6] dark:bg-[#111827] transition-colors duration-300">
      <div className="flex flex-1 items-center justify-center p-8">
        <div className="w-full max-w-md rounded-2xl border border-[#e2e8f0] bg-white p-8 shadow-xl dark:border-[#334155] dark:bg-[#1f2937] lg:p-12">
          <div className="mb-8">
            <div className="mb-6 flex items-center gap-2">
              <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary text-white">
                <Database size={22} />
              </span>
              <span className="font-display text-lg font-bold tracking-tight text-slate-900 dark:text-slate-100">M8 Connect</span>
            </div>
            <h1 className="font-display text-3xl font-bold tracking-tight text-slate-900 dark:text-slate-100 mb-2">Bienvenido de nuevo</h1>
            <p className="text-sm text-slate-500 m-0">Inicia sesión para acceder a tu centro de operaciones de cadena de suministro.</p>
          </div>

          <form className="flex flex-col gap-5" onSubmit={handleSubmit}>
            <FormField label="Correo electrónico" htmlFor="email">
              <Input id="email" type="email" icon={Mail} placeholder="nombre@empresa.com" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" disabled={loading} className="py-2.5 focus:ring-primary" />
            </FormField>

            <FormField label="Contraseña" htmlFor="password">
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400 pointer-events-none" />
                <input
                  id="password"
                  type={showPassword ? 'text' : 'password'}
                  className="w-full py-2.5 pl-10 pr-10 border border-gray-300 rounded-lg text-sm bg-white dark:bg-gray-800 dark:border-gray-600 focus:outline-none focus:ring-2 focus:ring-primary"
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="current-password"
                  disabled={loading}
                />
                <button type="button" className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-slate-400 hover:text-slate-700 rounded" onClick={() => setShowPassword((p) => !p)} disabled={loading} aria-label={showPassword ? 'Ocultar' : 'Mostrar'}>
                  {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </FormField>

            <div className="flex items-center justify-between gap-4 -mt-2">
              <label className="flex items-center gap-2 text-sm text-slate-600 cursor-pointer">
                <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} disabled={loading} className="accent-primary" />
                Recordarme
              </label>
              <button type="button" className="text-sm text-brand-500 hover:underline" disabled={loading}>¿Olvidaste tu contraseña?</button>
            </div>

            {error && <Alert variant="error">{error}</Alert>}

            <Button type="submit" className="w-full py-2.5 bg-primary hover:bg-primary-hover shadow-lg hover:shadow-xl" icon={LogIn} loading={loading} disabled={loading}>
              Iniciar sesión
            </Button>
          </form>
        </div>
      </div>

      <div className="hidden lg:flex flex-1 relative items-end bg-gradient-to-br from-blue-900 via-primary to-[#0a3d61] overflow-hidden">
        <div className="absolute inset-0 bg-primary/35 bg-gradient-to-br from-primary/80 to-primary/35" />
        <div className="relative z-10 w-full p-12 min-h-48">
          {HERO_SLIDES.map((slide, i) => (
            <div key={slide.title} className={`transition-opacity duration-700 ${i === slideIndex ? 'opacity-100' : 'opacity-0 absolute inset-x-12 bottom-24 pointer-events-none'}`}>
              <h2 className="font-display text-2xl font-bold text-white mb-2 tracking-tight">{slide.title}</h2>
              <p className="text-lg text-white/85 m-0 max-w-md leading-relaxed">{slide.text}</p>
            </div>
          ))}
          <div className="absolute bottom-8 left-12 flex gap-2">
            {HERO_SLIDES.map((_, i) => (
              <button key={i} type="button" onClick={() => setSlideIndex(i)} className={`h-2 rounded-full transition-all ${i === slideIndex ? 'w-6 bg-white' : 'w-2 bg-white/35'}`} aria-label={`Diapositiva ${i + 1}`} />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

export default Login;
