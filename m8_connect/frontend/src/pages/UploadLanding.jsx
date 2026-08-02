import React, { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { History, BookOpen, Upload, Download } from 'lucide-react';
import { PageHeader, Button, Alert } from '../components/ui';
import { useAuth } from '../context/AuthContext';
import { canUploadType, canViewConfig } from '../utils/permissions';
import { getHistoryCatalogReadiness, downloadUploadLayouts } from '../services/wizardService';
import { formatMissingCatalogs } from '../lib/statusLabels';

const UploadLanding = () => {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [historyReadiness, setHistoryReadiness] = useState(null);
  const [downloadingLayouts, setDownloadingLayouts] = useState(false);
  const [layoutError, setLayoutError] = useState('');

  useEffect(() => {
    let cancelled = false;
    if (!canUploadType(user, 'history')) {
      return undefined;
    }
    (async () => {
      try {
        const readiness = await getHistoryCatalogReadiness();
        if (!cancelled) {
          setHistoryReadiness(readiness);
        }
      } catch {
        if (!cancelled) {
          setHistoryReadiness(null);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [user]);

  const historyBlocked = historyReadiness != null && historyReadiness.ready === false;
  const missingCatalogsLabel = formatMissingCatalogs(historyReadiness?.missing);

  const cards = useMemo(() => {
    const all = [
      {
        key: 'history',
        icon: History,
        iconClass: 'text-brand-500',
        title: 'Historia',
        description: 'Carga histórica de ventas con agregación semanal o mensual, validación de cantidades y promoción a producción.',
        onClick: () => navigate('/upload/history'),
        link: canViewConfig(user, 'history') || user?.m8_connect_role === 'admin_m8_connect'
          ? { to: '/config/history', label: 'Configurar historia →' }
          : null,
        allowed: canUploadType(user, 'history'),
        blocked: historyBlocked,
        blockedMessage: historyReadiness?.message,
        missingCatalogsLabel,
      },
      {
        key: 'catalogs',
        icon: BookOpen,
        iconClass: 'text-emerald-500',
        title: 'Catálogos',
        description: 'Carga maestros de productos (SKUs) y ubicaciones aplicando las reglas de validación específicas de cada tabla.',
        onClick: () => navigate('/upload/catalog'),
        link: canViewConfig(user, 'catalogs') || user?.m8_connect_role === 'admin_m8_connect'
          ? { to: '/config/catalogs', label: 'Configurar catálogos →' }
          : null,
        allowed: canUploadType(user, 'catalogs'),
        blocked: false,
      },
    ];
    return all.filter((card) => card.allowed);
  }, [navigate, user, historyBlocked, historyReadiness?.message, missingCatalogsLabel]);

  const handleCardClick = (card) => {
    if (card.blocked) return;
    card.onClick();
  };

  const handleDownloadLayouts = async () => {
    if (downloadingLayouts) return;
    setLayoutError('');
    setDownloadingLayouts(true);
    try {
      await downloadUploadLayouts();
    } catch (err) {
      const detail = err.response?.data?.detail;
      setLayoutError(
        typeof detail === 'string'
          ? detail
          : err.message || 'No se pudieron descargar los layouts'
      );
    } finally {
      setDownloadingLayouts(false);
    }
  };

  return (
    <div className="flex flex-1 flex-col gap-5 overflow-y-auto p-8 max-w-4xl mx-auto w-full scrollbar-thin">
      <PageHeader
        icon={Upload}
        title="Cargar datos"
        subtitle="Selecciona el tipo de carga que deseas realizar"
        actions={(
          <Button
            variant="secondary"
            icon={Download}
            onClick={handleDownloadLayouts}
            disabled={downloadingLayouts}
            loading={downloadingLayouts}
            loadingLabel="Generando…"
          >
            Descargar layouts CSV
          </Button>
        )}
      />

      {layoutError && <Alert variant="error">{layoutError}</Alert>}

      {cards.length === 0 ? (
        <p className="text-sm text-slate-500">No tienes permisos para realizar cargas.</p>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {cards.map((card) => {
            const CardTag = card.blocked ? 'div' : 'button';
            return (
              <CardTag
                key={card.title}
                type={card.blocked ? undefined : 'button'}
                onClick={() => handleCardClick(card)}
                aria-disabled={card.blocked || undefined}
                className={[
                  'text-left rounded-md border bg-white p-8 shadow-sm transition-all dark:bg-slate-800 w-full',
                  card.blocked
                    ? 'border-amber-300 opacity-95 dark:border-amber-700 cursor-not-allowed'
                    : 'border-[#e2e8f0] hover:border-brand-500 hover:shadow-md dark:border-[#334155]',
                ].join(' ')}
              >
                <card.icon size={32} className={`mb-4 ${card.iconClass}`} />
                <h2 className="font-display text-lg font-semibold text-slate-900 dark:text-slate-100 mb-2">{card.title}</h2>
                <p className="text-sm text-slate-500 mb-4 leading-relaxed">{card.description}</p>
                {card.blocked && card.blockedMessage && (
                  <p className="text-sm text-amber-800 dark:text-amber-200 mb-2 leading-relaxed">
                    {card.blockedMessage}
                  </p>
                )}
                {card.blocked && card.missingCatalogsLabel && (
                  <p className="text-sm text-amber-700 dark:text-amber-300 mb-3 leading-relaxed">
                    Faltan: {card.missingCatalogsLabel}
                  </p>
                )}
                {!card.blocked && (
                  <span className="font-semibold text-brand-600 text-sm">Continuar →</span>
                )}
                {card.blocked && (
                  <span className="block mt-2 text-sm">
                    <Link to="/upload/catalog" className="text-brand-600 hover:underline font-semibold">
                      Ir a catálogos →
                    </Link>
                  </span>
                )}
                {card.link && (
                  <span className="block mt-2 text-sm" onClick={(e) => e.stopPropagation()}>
                    <Link to={card.link.to} className="text-brand-600 hover:underline">{card.link.label}</Link>
                  </span>
                )}
              </CardTag>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default UploadLanding;
