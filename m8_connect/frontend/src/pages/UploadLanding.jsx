import React from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { History, BookOpen, Upload } from 'lucide-react';
import { PageHeader } from '../components/ui';

const UploadLanding = () => {
  const navigate = useNavigate();

  const cards = [
    {
      icon: History,
      iconClass: 'text-brand-500',
      title: 'Historia',
      description: 'Carga histórica de ventas con agregación semanal o mensual, validación de cantidades y promoción a producción.',
      onClick: () => navigate('/upload/history'),
    },
    {
      icon: BookOpen,
      iconClass: 'text-emerald-500',
      title: 'Catálogos',
      description: 'Carga maestros de productos (SKUs) y ubicaciones aplicando las reglas de validación específicas de cada tabla.',
      onClick: () => navigate('/upload/catalog'),
      link: { to: '/catalogs', label: 'Configurar catálogos →' },
    },
  ];

  return (
    <div className="flex flex-1 flex-col gap-5 overflow-y-auto p-8 max-w-4xl mx-auto w-full scrollbar-thin">
      <PageHeader icon={Upload} title="Cargar datos" subtitle="Selecciona el tipo de carga que deseas realizar" />

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {cards.map((card) => (
          <button
            key={card.title}
            type="button"
            onClick={card.onClick}
            className="text-left rounded-md border border-[#e2e8f0] bg-white p-8 shadow-sm hover:border-brand-500 hover:shadow-md transition-all dark:border-[#334155] dark:bg-slate-800 w-full"
          >
            <card.icon size={32} className={`mb-4 ${card.iconClass}`} />
            <h2 className="font-display text-lg font-semibold text-slate-900 dark:text-slate-100 mb-2">{card.title}</h2>
            <p className="text-sm text-slate-500 mb-4 leading-relaxed">{card.description}</p>
            <span className="font-semibold text-brand-600 text-sm">Continuar →</span>
            {card.link && (
              <span className="block mt-2 text-sm" onClick={(e) => e.stopPropagation()}>
                <Link to={card.link.to} className="text-brand-600 hover:underline">{card.link.label}</Link>
              </span>
            )}
          </button>
        ))}
      </div>
    </div>
  );
};

export default UploadLanding;
