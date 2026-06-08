import React from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { History, BookOpen } from 'lucide-react';
import './UploadLanding.css';

const UploadLanding = () => {
    const navigate = useNavigate();

    return (
        <div className="upload-landing">
            <div className="upload-landing-header">
                <h1>Cargar datos</h1>
                <p>Selecciona el tipo de carga que deseas realizar</p>
            </div>

            <div className="upload-type-grid">
                <button
                    type="button"
                    className="upload-type-card glass-card"
                    onClick={() => navigate('/upload/history')}
                >
                    <div className="upload-type-icon history">
                        <History size={40} />
                    </div>
                    <h2>Historia</h2>
                    <p>
                        Carga histórica de ventas con agregación semanal o mensual,
                        validación de cantidades y promoción a producción.
                    </p>
                    <span className="upload-type-cta">Continuar →</span>
                </button>

                <button
                    type="button"
                    className="upload-type-card glass-card"
                    onClick={() => navigate('/upload/catalog')}
                >
                    <div className="upload-type-icon catalog">
                        <BookOpen size={40} />
                    </div>
                    <h2>Catálogos</h2>
                    <p>
                        Carga maestros de productos (SKUs) y ubicaciones aplicando
                        las reglas de validación específicas de cada tabla.
                    </p>
                    <span className="upload-type-cta">Continuar →</span>
                    <span className="upload-type-link" style={{ display: 'block', marginTop: '0.5rem', fontSize: '0.85rem' }}>
                        <Link to="/catalogs">Configurar catálogos →</Link>
                    </span>
                </button>
            </div>
        </div>
    );
};

export default UploadLanding;
