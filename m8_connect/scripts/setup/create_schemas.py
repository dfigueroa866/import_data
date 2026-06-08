#!/usr/bin/env python3
"""
create_schemas.py - Script para crear esquemas y tablas de M8 Connect

Este script:
1. Crea los esquemas necesarios (staging_meta, staging_data, production)
2. Crea todas las tablas del sistema
3. Crea índices para optimización
4. Crea vistas para consultas frecuentes
5. Configura permisos básicos
"""

import os
import sys
import logging
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

# Agregar el directorio src al path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

try:
    from data_staging.config import settings
    from data_staging.models.base import Base
except ImportError as e:
    logging.error(f"Error importando configuración: {e}")
    logging.error("Asegúrate de que la estructura del proyecto esté correcta")
    sys.exit(1)

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class SchemaCreator:
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.engine = create_engine(database_url)
    
    def create_schemas(self):
        """Crea los esquemas necesarios"""
        schemas = ['staging_meta', 'staging_data', 'm8_schema']
        
        logger.info("📁 Creando esquemas...")
        
        try:
            with self.engine.begin() as conn:
                for schema in schemas:
                    conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS {schema}'))
                    logger.info(f"✅ Schema '{schema}' creado")
            
            return True
            
        except SQLAlchemyError as e:
            logger.error(f"❌ Error creando esquemas: {e}")
            return False
    
    def create_tables(self):
        """Crea todas las tablas usando SQLAlchemy models"""
        logger.info("🏗️  Creando tablas...")
        
        try:
            # Crear todas las tablas definidas en los modelos
            Base.metadata.create_all(self.engine)
            logger.info("✅ Todas las tablas creadas exitosamente")
            return True
            
        except SQLAlchemyError as e:
            logger.error(f"❌ Error creando tablas: {e}")
            return False
    
    def create_additional_tables(self):
        """Crea tablas adicionales que no están en los modelos"""
        logger.info("🔧 Creando tablas adicionales...")
        
        additional_sql = """
        -- Tabla de control de lotes
        CREATE TABLE IF NOT EXISTS staging_meta.batch_control (
            batch_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            source_name VARCHAR(100) NOT NULL,
            source_type VARCHAR(50) NOT NULL,
            file_name VARCHAR(255),
            file_size BIGINT,
            records_count INTEGER,
            status VARCHAR(20) DEFAULT 'PENDING',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            started_at TIMESTAMP,
            completed_at TIMESTAMP,
            error_message TEXT,
            metadata JSONB,
            organization_id TEXT
        );

        -- Tabla de configuración de fuentes
        CREATE TABLE IF NOT EXISTS staging_meta.data_sources (
            source_id SERIAL PRIMARY KEY,
            source_name VARCHAR(100) UNIQUE NOT NULL,
            source_type VARCHAR(50) NOT NULL,
            connection_config JSONB,
            validation_rules JSONB,
            target_table VARCHAR(100),
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- Tabla de logs de validación
        CREATE TABLE IF NOT EXISTS staging_meta.validation_logs (
            log_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            batch_id UUID REFERENCES staging_meta.batch_control(batch_id),
            validation_type VARCHAR(50),
            validation_rule VARCHAR(100),
            status VARCHAR(20),
            error_count INTEGER DEFAULT 0,
            message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- Tabla de historial de cargas
        CREATE TABLE IF NOT EXISTS staging_meta.load_history (
            load_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            batch_id UUID REFERENCES staging_meta.batch_control(batch_id),
            source_name VARCHAR(100) NOT NULL,
            load_type VARCHAR(50) NOT NULL,
            target_table VARCHAR(100),
            records_inserted INTEGER DEFAULT 0,
            records_updated INTEGER DEFAULT 0,
            records_deleted INTEGER DEFAULT 0,
            records_rejected INTEGER DEFAULT 0,
            data_quality_score DECIMAL(5,2),
            load_start_time TIMESTAMP NOT NULL,
            load_end_time TIMESTAMP,
            duration_seconds INTEGER,
            status VARCHAR(20) DEFAULT 'IN_PROGRESS',
            error_details TEXT,
            metadata JSONB,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- Tabla resumen de fuentes
        CREATE TABLE IF NOT EXISTS staging_meta.source_load_summary (
            source_name VARCHAR(100) PRIMARY KEY,
            last_successful_load TIMESTAMP,
            last_attempted_load TIMESTAMP,
            total_successful_loads INTEGER DEFAULT 0,
            total_failed_loads INTEGER DEFAULT 0,
            average_load_duration_seconds INTEGER,
            last_record_count INTEGER DEFAULT 0,
            last_data_quality_score DECIMAL(5,2),
            current_status VARCHAR(20),
            next_scheduled_load TIMESTAMP,
            load_frequency VARCHAR(50),
            is_active BOOLEAN DEFAULT TRUE,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- Template para tablas de staging
        CREATE TABLE IF NOT EXISTS staging_data.template_staging (
            staging_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            batch_id UUID REFERENCES staging_meta.batch_control(batch_id),
            source_row_number INTEGER,
            raw_data JSONB,
            processed_data JSONB,
            validation_status VARCHAR(20) DEFAULT 'PENDING',
            error_details JSONB,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            processed_at TIMESTAMP
        );
        """
        
        try:
            with self.engine.begin() as conn:
                # Ejecutar cada statement por separado
                for statement in additional_sql.split(';'):
                    statement = statement.strip()
                    if statement:
                        conn.execute(text(statement))
            
            logger.info("✅ Tablas adicionales creadas")
            return True
            
        except SQLAlchemyError as e:
            logger.error(f"❌ Error creando tablas adicionales: {e}")
            return False
    
    def create_indexes(self):
        """Crea índices para optimización"""
        logger.info("🔍 Creando índices...")
        
        indexes_sql = """
        -- Índices para load_history
        CREATE INDEX IF NOT EXISTS idx_load_history_source_time 
        ON staging_meta.load_history(source_name, load_start_time DESC);
        
        CREATE INDEX IF NOT EXISTS idx_load_history_batch_id 
        ON staging_meta.load_history(batch_id);
        
        CREATE INDEX IF NOT EXISTS idx_load_history_status 
        ON staging_meta.load_history(status);
        
        CREATE INDEX IF NOT EXISTS idx_load_history_start_time 
        ON staging_meta.load_history(load_start_time DESC);
        
        -- Índices para batch_control
        CREATE INDEX IF NOT EXISTS idx_batch_control_source_created 
        ON staging_meta.batch_control(source_name, created_at DESC);
        
        CREATE INDEX IF NOT EXISTS idx_batch_control_status 
        ON staging_meta.batch_control(status);
        
        CREATE INDEX IF NOT EXISTS idx_batch_control_created 
        ON staging_meta.batch_control(created_at DESC);
        
        -- Índices para validation_logs
        CREATE INDEX IF NOT EXISTS idx_validation_logs_batch_id 
        ON staging_meta.validation_logs(batch_id);
        
        CREATE INDEX IF NOT EXISTS idx_validation_logs_created 
        ON staging_meta.validation_logs(created_at DESC);
        
        -- Índices para template_staging
        CREATE INDEX IF NOT EXISTS idx_template_staging_batch_id 
        ON staging_data.template_staging(batch_id);
        
        CREATE INDEX IF NOT EXISTS idx_template_staging_validation_status 
        ON staging_data.template_staging(validation_status);
        
        CREATE INDEX IF NOT EXISTS idx_template_staging_created 
        ON staging_data.template_staging(created_at DESC);
        """
        
        try:
            with self.engine.begin() as conn:
                for statement in indexes_sql.split(';'):
                    statement = statement.strip()
                    if statement:
                        conn.execute(text(statement))
            
            logger.info("✅ Índices creados")
            return True
            
        except SQLAlchemyError as e:
            logger.error(f"❌ Error creando índices: {e}")
            return False
    
    def create_views(self):
        """Crea vistas para consultas frecuentes"""
        logger.info("👁️  Creando vistas...")
        
        views_sql = """
        -- Vista para consultas rápidas de última carga
        CREATE OR REPLACE VIEW staging_meta.v_latest_loads AS
        SELECT 
            s.source_name,
            s.last_successful_load,
            s.last_attempted_load,
            s.current_status,
            s.last_record_count,
            s.last_data_quality_score,
            s.total_successful_loads,
            s.total_failed_loads,
            ROUND(
                s.total_successful_loads::DECIMAL / 
                NULLIF(s.total_successful_loads + s.total_failed_loads, 0) * 100, 
                2
            ) as success_rate,
            s.average_load_duration_seconds,
            s.load_frequency,
            CASE 
                WHEN s.last_successful_load IS NULL THEN 'Never loaded'
                WHEN s.last_successful_load < CURRENT_TIMESTAMP - INTERVAL '1 day' 
                     AND s.load_frequency = 'DAILY' THEN 'Overdue'
                WHEN s.last_successful_load < CURRENT_TIMESTAMP - INTERVAL '7 days' 
                     AND s.load_frequency = 'WEEKLY' THEN 'Overdue'
                WHEN s.last_successful_load < CURRENT_TIMESTAMP - INTERVAL '30 days' 
                     AND s.load_frequency = 'MONTHLY' THEN 'Overdue'
                ELSE 'On Schedule'
            END as schedule_status
        FROM staging_meta.source_load_summary s
        WHERE s.is_active = TRUE;

        -- Vista de estadísticas de carga por día
        CREATE OR REPLACE VIEW staging_meta.v_daily_load_stats AS
        SELECT 
            DATE_TRUNC('day', load_start_time) as load_date,
            source_name,
            COUNT(*) as total_loads,
            SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END) as successful_loads,
            SUM(CASE WHEN status = 'FAILED' THEN 1 ELSE 0 END) as failed_loads,
            AVG(duration_seconds) as avg_duration_seconds,
            SUM(records_inserted + records_updated) as total_records_processed,
            AVG(data_quality_score) as avg_quality_score
        FROM staging_meta.load_history
        WHERE load_start_time >= CURRENT_DATE - INTERVAL '90 days'
        GROUP BY DATE_TRUNC('day', load_start_time), source_name
        ORDER BY load_date DESC, source_name;

        -- Vista de errores recientes
        CREATE OR REPLACE VIEW staging_meta.v_recent_errors AS
        SELECT 
            lh.source_name,
            lh.load_start_time,
            lh.error_details,
            lh.duration_seconds,
            bc.file_name,
            bc.file_size,
            EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - lh.load_start_time))/3600 as hours_ago
        FROM staging_meta.load_history lh
        JOIN staging_meta.batch_control bc ON lh.batch_id = bc.batch_id
        WHERE lh.status = 'FAILED'
          AND lh.load_start_time >= CURRENT_TIMESTAMP - INTERVAL '7 days'
        ORDER BY lh.load_start_time DESC;
        """
        
        try:
            with self.engine.begin() as conn:
                for statement in views_sql.split(';'):
                    statement = statement.strip()
                    if statement and not statement.startswith('--'):
                        conn.execute(text(statement))
            
            logger.info("✅ Vistas creadas")
            return True
            
        except SQLAlchemyError as e:
            logger.error(f"❌ Error creando vistas: {e}")
            return False
    
    def create_functions(self):
        """Crea funciones útiles de PostgreSQL"""
        logger.info("⚙️  Creando funciones...")
        
        functions_sql = """
        -- Función para limpiar datos antiguos
        CREATE OR REPLACE FUNCTION staging_meta.cleanup_old_data(days_to_keep INTEGER DEFAULT 30)
        RETURNS INTEGER
        LANGUAGE plpgsql
        AS $$
        DECLARE
            deleted_count INTEGER := 0;
            temp_count INTEGER;
        BEGIN
            -- Limpiar load_history
            DELETE FROM staging_meta.load_history 
            WHERE load_start_time < CURRENT_TIMESTAMP - (days_to_keep || ' days')::INTERVAL;
            GET DIAGNOSTICS temp_count = ROW_COUNT;
            deleted_count := deleted_count + temp_count;
            
            -- Limpiar validation_logs
            DELETE FROM staging_meta.validation_logs 
            WHERE created_at < CURRENT_TIMESTAMP - (days_to_keep || ' days')::INTERVAL;
            GET DIAGNOSTICS temp_count = ROW_COUNT;
            deleted_count := deleted_count + temp_count;
            
            RETURN deleted_count;
        END;
        $$;

        -- Función para obtener estadísticas de una fuente
        CREATE OR REPLACE FUNCTION staging_meta.get_source_stats(source_name_param VARCHAR(100))
        RETURNS TABLE(
            total_loads INTEGER,
            successful_loads INTEGER,
            failed_loads INTEGER,
            avg_duration_seconds NUMERIC,
            last_load_time TIMESTAMP,
            avg_quality_score NUMERIC
        )
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RETURN QUERY
            SELECT 
                COUNT(*)::INTEGER as total_loads,
                SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END)::INTEGER as successful_loads,
                SUM(CASE WHEN status = 'FAILED' THEN 1 ELSE 0 END)::INTEGER as failed_loads,
                AVG(duration_seconds) as avg_duration_seconds,
                MAX(load_start_time) as last_load_time,
                AVG(data_quality_score) as avg_quality_score
            FROM staging_meta.load_history
            WHERE source_name = source_name_param
              AND load_start_time >= CURRENT_TIMESTAMP - INTERVAL '30 days';
        END;
        $$;
        """
        
        try:
            with self.engine.begin() as conn:
                for statement in functions_sql.split('$$;'):
                    statement = statement.strip()
                    if statement and not statement.startswith('--'):
                        statement += '$$;' if not statement.endswith('$$;') else ''
                        if len(statement) > 10:  # Evitar statements vacíos
                            conn.execute(text(statement))
            
            logger.info("✅ Funciones creadas")
            return True
            
        except SQLAlchemyError as e:
            logger.error(f"❌ Error creando funciones: {e}")
            return False
    
    def verify_setup(self):
        """Verifica que todo se haya creado correctamente"""
        logger.info("🔍 Verificando configuración...")
        
        try:
            with self.engine.begin() as conn:
                # Verificar esquemas
                result = conn.execute(text("""
                    SELECT schema_name 
                    FROM information_schema.schemata 
                    WHERE schema_name IN ('staging_meta', 'staging_data', 'public')
                """))
                schemas = [row[0] for row in result]
                logger.info(f"✅ Esquemas encontrados: {schemas}")
                
                # Verificar tablas principales
                result = conn.execute(text("""
                    SELECT table_schema, table_name 
                    FROM information_schema.tables 
                    WHERE table_schema IN ('staging_meta', 'staging_data')
                    ORDER BY table_schema, table_name
                """))
                tables = [(row[0], row[1]) for row in result]
                logger.info(f"✅ Tablas creadas: {len(tables)}")
                for schema, table in tables:
                    logger.info(f"   {schema}.{table}")
                
                # Verificar vistas
                result = conn.execute(text("""
                    SELECT table_schema, table_name 
                    FROM information_schema.views 
                    WHERE table_schema = 'staging_meta'
                """))
                views = [(row[0], row[1]) for row in result]
                logger.info(f"✅ Vistas creadas: {len(views)}")
                for schema, view in views:
                    logger.info(f"   {schema}.{view}")
            
            return True
            
        except SQLAlchemyError as e:
            logger.error(f"❌ Error en verificación: {e}")
            return False
    
    def create_all(self):
        """Ejecuta todo el proceso de creación"""
        logger.info("🚀 Iniciando creación de esquemas y tablas...")
        
        steps = [
            ("Esquemas", self.create_schemas),
            ("Tablas base", self.create_tables),
            ("Tablas adicionales", self.create_additional_tables),
            ("Índices", self.create_indexes),
            ("Vistas", self.create_views),
            ("Funciones", self.create_functions),
            ("Verificación", self.verify_setup)
        ]
        
        for step_name, step_func in steps:
            logger.info(f"\n--- {step_name} ---")
            if not step_func():
                logger.error(f"❌ Falló en paso: {step_name}")
                return False
        
        return True

def main():
    """Función principal"""
    logger.info("=" * 60)
    logger.info("CREADOR DE ESQUEMAS - M8 CONNECT")
    logger.info("=" * 60)
    
    try:
        # Verificar configuración
        if not hasattr(settings, 'DATABASE_URL') or not settings.DATABASE_URL:
            logger.error("❌ DATABASE_URL no está configurada")
            return False
        
        # Crear esquemas y tablas
        creator = SchemaCreator(settings.DATABASE_URL)
        success = creator.create_all()
        
        if success:
            logger.info("\n" + "=" * 60)
            logger.info("✅ CREACIÓN DE ESQUEMAS COMPLETADA EXITOSAMENTE")
            logger.info("=" * 60)
            logger.info("\nPróximos pasos:")
            logger.info("1. Ejecutar: alembic upgrade head")
            logger.info("2. Ejecutar: python scripts/setup/seed_data.py")
            return True
        else:
            logger.error("\n" + "=" * 60)
            logger.error("❌ CREACIÓN DE ESQUEMAS FALLÓ")
            logger.error("=" * 60)
            return False
            
    except KeyboardInterrupt:
        logger.info("\n⏹️  Creación cancelada por el usuario")
        return False
    except Exception as e:
        logger.error(f"\n❌ Error inesperado: {e}")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)