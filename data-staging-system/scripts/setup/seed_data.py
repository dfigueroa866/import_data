#!/usr/bin/env python3
"""
seed_data.py - Script para cargar datos de prueba y configuración inicial

Este script:
1. Carga configuraciones de fuentes de datos de ejemplo
2. Crea datos de prueba para testing
3. Configura usuarios y permisos iniciales
4. Inserta datos de referencia
"""

import os
import sys
import logging
import json
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
import uuid

# Agregar el directorio src al path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

try:
    from data_staging.config import settings
except ImportError as e:
    logging.error(f"Error importando configuración: {e}")
    sys.exit(1)

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class DataSeeder:
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.engine = create_engine(database_url)
    
    def seed_data_sources(self):
        """Carga configuraciones de fuentes de datos de ejemplo"""
        logger.info("📋 Cargando configuraciones de fuentes de datos...")
        
        sample_sources = [
            {
                "source_name": "ventas_excel",
                "source_type": "file",
                "connection_config": {
                    "file_path": "./data/sample/ventas_sample.xlsx",
                    "read_options": {
                        "sheet_name": "Ventas",
                        "header": 0,
                        "skiprows": 0
                    }
                },
                "validation_rules": {
                    "not_null_columns": ["fecha", "producto_id", "cliente_id", "cantidad", "precio"],
                    "unique_columns": ["venta_id"],
                    "column_types": {
                        "venta_id": "int64",
                        "fecha": "datetime64[ns]",
                        "producto_id": "int64",
                        "cliente_id": "int64",
                        "cantidad": "float64",
                        "precio": "float64"
                    },
                    "range_validations": {
                        "cantidad": {"min": 0, "max": 10000},
                        "precio": {"min": 0, "max": 1000000}
                    },
                    "custom_rules": {
                        "total_coherence": {
                            "rule_type": "calculated_field",
                            "expression": "cantidad * precio",
                            "target_column": "total",
                            "tolerance": 0.01
                        }
                    }
                },
                "target_table": "ventas"
            },
            {
                "source_name": "clientes_csv",
                "source_type": "file",
                "connection_config": {
                    "file_path": "./data/sample/clientes_sample.csv",
                    "read_options": {
                        "delimiter": ",",
                        "encoding": "utf-8",
                        "header": 0
                    }
                },
                "validation_rules": {
                    "not_null_columns": ["cliente_id", "nombre", "email"],
                    "unique_columns": ["cliente_id", "email"],
                    "column_types": {
                        "cliente_id": "int64",
                        "nombre": "string",
                        "email": "string",
                        "telefono": "string",
                        "fecha_registro": "datetime64[ns]"
                    },
                    "custom_rules": {
                        "email_format": {
                            "rule_type": "regex",
                            "column": "email",
                            "pattern": r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
                        }
                    }
                },
                "target_table": "clientes"
            },
            {
                "source_name": "productos_api",
                "source_type": "api",
                "connection_config": {
                    "url": "https://api.example.com/productos",
                    "method": "GET",
                    "headers": {
                        "Authorization": "Bearer YOUR_TOKEN_HERE",
                        "Content-Type": "application/json"
                    },
                    "params": {
                        "limit": 1000,
                        "format": "json"
                    },
                    "timeout": 30
                },
                "validation_rules": {
                    "not_null_columns": ["producto_id", "nombre", "categoria", "precio"],
                    "unique_columns": ["producto_id", "codigo_barras"],
                    "column_types": {
                        "producto_id": "int64",
                        "nombre": "string",
                        "categoria": "string",
                        "precio": "float64",
                        "stock": "int64"
                    },
                    "range_validations": {
                        "precio": {"min": 0.01, "max": 100000},
                        "stock": {"min": 0, "max": 999999}
                    }
                },
                "target_table": "productos"
            },
            {
                "source_name": "inventario_database",
                "source_type": "database",
                "connection_config": {
                    "connection_string": "postgresql://user:pass@localhost:5432/legacy_db",
                    "query": """
                        SELECT 
                            producto_id,
                            almacen_id,
                            cantidad_disponible,
                            cantidad_reservada,
                            fecha_actualizacion
                        FROM inventario 
                        WHERE fecha_actualizacion >= CURRENT_DATE - INTERVAL '1 day'
                    """,
                    "chunk_size": 10000
                },
                "validation_rules": {
                    "not_null_columns": ["producto_id", "almacen_id", "cantidad_disponible"],
                    "column_types": {
                        "producto_id": "int64",
                        "almacen_id": "int64",
                        "cantidad_disponible": "int64",
                        "cantidad_reservada": "int64"
                    },
                    "range_validations": {
                        "cantidad_disponible": {"min": 0},
                        "cantidad_reservada": {"min": 0}
                    }
                },
                "target_table": "inventario"
            }
        ]
        
        try:
            with self.engine.begin() as conn:
                for source in sample_sources:
                    # Verificar si ya existe
                    check_query = text("""
                        SELECT COUNT(*) FROM staging_meta.data_sources 
                        WHERE source_name = :source_name
                    """)
                    exists = conn.execute(check_query, {"source_name": source["source_name"]}).scalar()
                    
                    if exists > 0:
                        logger.info(f"⚠️  Fuente '{source['source_name']}' ya existe, actualizando...")
                        update_query = text("""
                            UPDATE staging_meta.data_sources 
                            SET source_type = :source_type,
                                connection_config = :connection_config,
                                validation_rules = :validation_rules,
                                target_table = :target_table
                            WHERE source_name = :source_name
                        """)
                        conn.execute(update_query, {
                            "source_name": source["source_name"],
                            "source_type": source["source_type"],
                            "connection_config": json.dumps(source["connection_config"]),
                            "validation_rules": json.dumps(source["validation_rules"]),
                            "target_table": source["target_table"]
                        })
                    else:
                        insert_query = text("""
                            INSERT INTO staging_meta.data_sources 
                            (source_name, source_type, connection_config, validation_rules, target_table)
                            VALUES (:source_name, :source_type, :connection_config, :validation_rules, :target_table)
                        """)
                        conn.execute(insert_query, {
                            "source_name": source["source_name"],
                            "source_type": source["source_type"],
                            "connection_config": json.dumps(source["connection_config"]),
                            "validation_rules": json.dumps(source["validation_rules"]),
                            "target_table": source["target_table"]
                        })
                    
                    logger.info(f"✅ Fuente '{source['source_name']}' configurada")
            
            return True
            
        except SQLAlchemyError as e:
            logger.error(f"❌ Error cargando fuentes de datos: {e}")
            return False
    
    def seed_source_summaries(self):
        """Carga datos iniciales en la tabla de resúmenes de fuentes"""
        logger.info("📊 Inicializando resúmenes de fuentes...")
        
        initial_summaries = [
            {
                "source_name": "ventas_excel",
                "load_frequency": "DAILY",
                "next_scheduled_load": datetime.now() + timedelta(days=1)
            },
            {
                "source_name": "clientes_csv", 
                "load_frequency": "WEEKLY",
                "next_scheduled_load": datetime.now() + timedelta(days=7)
            },
            {
                "source_name": "productos_api",
                "load_frequency": "DAILY",
                "next_scheduled_load": datetime.now() + timedelta(hours=6)
            },
            {
                "source_name": "inventario_database",
                "load_frequency": "DAILY", 
                "next_scheduled_load": datetime.now() + timedelta(hours=2)
            }
        ]
        
        try:
            with self.engine.begin() as conn:
                for summary in initial_summaries:
                    insert_query = text("""
                        INSERT INTO staging_meta.source_load_summary 
                        (source_name, load_frequency, next_scheduled_load, current_status)
                        VALUES (:source_name, :load_frequency, :next_scheduled_load, 'PENDING')
                        ON CONFLICT (source_name) DO UPDATE SET
                            load_frequency = EXCLUDED.load_frequency,
                            next_scheduled_load = EXCLUDED.next_scheduled_load,
                            updated_at = CURRENT_TIMESTAMP
                    """)
                    conn.execute(insert_query, summary)
                    logger.info(f"✅ Resumen para '{summary['source_name']}' inicializado")
            
            return True
            
        except SQLAlchemyError as e:
            logger.error(f"❌ Error inicializando resúmenes: {e}")
            return False
    
    def create_sample_staging_tables(self):
        """Crea tablas de staging de ejemplo"""
        logger.info("🏗️  Creando tablas de staging de ejemplo...")
        
        staging_tables = {
            "ventas_staging": """
                CREATE TABLE IF NOT EXISTS staging_data.ventas_staging (
                    staging_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    batch_id UUID REFERENCES staging_meta.batch_control(batch_id),
                    source_row_number INTEGER,
                    raw_data JSONB,
                    processed_data JSONB,
                    validation_status VARCHAR(20) DEFAULT 'PENDING',
                    error_details JSONB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    processed_at TIMESTAMP
                )
            """,
            "clientes_staging": """
                CREATE TABLE IF NOT EXISTS staging_data.clientes_staging (
                    staging_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    batch_id UUID REFERENCES staging_meta.batch_control(batch_id),
                    source_row_number INTEGER,
                    raw_data JSONB,
                    processed_data JSONB,
                    validation_status VARCHAR(20) DEFAULT 'PENDING',
                    error_details JSONB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    processed_at TIMESTAMP
                )
            """,
            "productos_staging": """
                CREATE TABLE IF NOT EXISTS staging_data.productos_staging (
                    staging_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    batch_id UUID REFERENCES staging_meta.batch_control(batch_id),
                    source_row_number INTEGER,
                    raw_data JSONB,
                    processed_data JSONB,
                    validation_status VARCHAR(20) DEFAULT 'PENDING',
                    error_details JSONB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    processed_at TIMESTAMP
                )
            """,
            "inventario_staging": """
                CREATE TABLE IF NOT EXISTS staging_data.inventario_staging (
                    staging_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    batch_id UUID REFERENCES staging_meta.batch_control(batch_id),
                    source_row_number INTEGER,
                    raw_data JSONB,
                    processed_data JSONB,
                    validation_status VARCHAR(20) DEFAULT 'PENDING',
                    error_details JSONB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    processed_at TIMESTAMP
                )
            """
        }
        
        try:
            with self.engine.begin() as conn:
                for table_name, create_sql in staging_tables.items():
                    conn.execute(text(create_sql))
                    logger.info(f"✅ Tabla '{table_name}' creada")
            
            return True
            
        except SQLAlchemyError as e:
            logger.error(f"❌ Error creando tablas de staging: {e}")
            return False
    
    def create_production_tables(self):
        """Crea tablas de producción de ejemplo"""
        logger.info("🎯 Creando tablas de producción de ejemplo...")
        
        production_tables = {
            "ventas": """
                CREATE TABLE IF NOT EXISTS m8_schema.ventas (
                    venta_id SERIAL PRIMARY KEY,
                    fecha DATE NOT NULL,
                    producto_id INTEGER NOT NULL,
                    cliente_id INTEGER NOT NULL,
                    cantidad DECIMAL(10,2) NOT NULL,
                    precio DECIMAL(10,2) NOT NULL,
                    total DECIMAL(10,2) GENERATED ALWAYS AS (cantidad * precio) STORED,
                    descuento DECIMAL(5,2) DEFAULT 0,
                    vendedor_id INTEGER,
                    sucursal_id INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """,
            "clientes": """
                CREATE TABLE IF NOT EXISTS m8_schema.clientes (
                    cliente_id SERIAL PRIMARY KEY,
                    nombre VARCHAR(200) NOT NULL,
                    email VARCHAR(150) UNIQUE NOT NULL,
                    telefono VARCHAR(20),
                    direccion TEXT,
                    ciudad VARCHAR(100),
                    pais VARCHAR(100),
                    fecha_registro DATE DEFAULT CURRENT_DATE,
                    fecha_nacimiento DATE,
                    activo BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """,
            "productos": """
                CREATE TABLE IF NOT EXISTS m8_schema.productos (
                    producto_id SERIAL PRIMARY KEY,
                    nombre VARCHAR(200) NOT NULL,
                    descripcion TEXT,
                    categoria VARCHAR(100) NOT NULL,
                    precio DECIMAL(10,2) NOT NULL,
                    costo DECIMAL(10,2),
                    codigo_barras VARCHAR(50) UNIQUE,
                    sku VARCHAR(50) UNIQUE,
                    stock INTEGER DEFAULT 0,
                    stock_minimo INTEGER DEFAULT 0,
                    activo BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """,
            "inventario": """
                CREATE TABLE IF NOT EXISTS m8_schema.inventario (
                    inventario_id SERIAL PRIMARY KEY,
                    producto_id INTEGER NOT NULL,
                    almacen_id INTEGER NOT NULL,
                    cantidad_disponible INTEGER NOT NULL DEFAULT 0,
                    cantidad_reservada INTEGER NOT NULL DEFAULT 0,
                    cantidad_total INTEGER GENERATED ALWAYS AS (cantidad_disponible + cantidad_reservada) STORED,
                    fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(producto_id, almacen_id)
                )
            """
        }
        
        try:
            with self.engine.begin() as conn:
                for table_name, create_sql in production_tables.items():
                    conn.execute(text(create_sql))
                    logger.info(f"✅ Tabla de producción '{table_name}' creada")
            
            return True
            
        except SQLAlchemyError as e:
            logger.error(f"❌ Error creando tablas de producción: {e}")
            return False
    
    def seed_sample_data(self):
        """Carga datos de ejemplo para testing"""
        logger.info("🎭 Cargando datos de ejemplo...")
        
        # Crear un lote de ejemplo
        batch_id = str(uuid.uuid4())
        
        try:
            with self.engine.begin() as conn:
                # Insertar lote de control
                conn.execute(text("""
                    INSERT INTO staging_meta.batch_control 
                    (batch_id, source_name, source_type, file_name, file_size, records_count, status, metadata)
                    VALUES (:batch_id, 'demo_data', 'manual', 'seed_data.py', 1024, 100, 'COMPLETED', 
                            '{"purpose": "demo", "created_by": "seed_script"}')
                """), {"batch_id": batch_id})
                
                # Insertar historial de carga de ejemplo
                load_id = str(uuid.uuid4())
                start_time = datetime.now() - timedelta(minutes=5)
                end_time = datetime.now()
                
                conn.execute(text("""
                    INSERT INTO staging_meta.load_history 
                    (load_id, batch_id, source_name, load_type, target_table, records_inserted,
                     data_quality_score, load_start_time, load_end_time, duration_seconds, status)
                    VALUES (:load_id, :batch_id, 'demo_data', 'FULL', 'demo_table', 100,
                            98.5, :start_time, :end_time, :duration, 'COMPLETED')
                """), {
                    "load_id": load_id,
                    "batch_id": batch_id,
                    "start_time": start_time,
                    "end_time": end_time,
                    "duration": int((end_time - start_time).total_seconds())
                })
                
                # Insertar logs de validación de ejemplo
                validation_log_id = str(uuid.uuid4())
                conn.execute(text("""
                    INSERT INTO staging_meta.validation_logs 
                    (log_id, batch_id, validation_type, validation_rule, status, error_count, message)
                    VALUES (:log_id, :batch_id, 'type_check', 'column_types', 'PASSED', 0, 
                            'All columns have correct data types')
                """), {
                    "log_id": validation_log_id,
                    "batch_id": batch_id
                })
                
                logger.info(f"✅ Datos de ejemplo creados con batch_id: {batch_id}")
            
            return True
            
        except SQLAlchemyError as e:
            logger.error(f"❌ Error cargando datos de ejemplo: {e}")
            return False
    
    def create_sample_files(self):
        """Crea archivos de ejemplo para testing"""
        logger.info("📁 Creando archivos de ejemplo...")
        
        # Crear directorio de datos de ejemplo
        sample_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'sample')
        os.makedirs(sample_dir, exist_ok=True)
        
        # Crear CSV de ejemplo
        csv_content = """cliente_id,nombre,email,telefono,fecha_registro
1,Juan Pérez,juan.perez@email.com,+34-123-456-789,2024-01-15
2,María García,maria.garcia@email.com,+34-987-654-321,2024-01-16
3,Carlos López,carlos.lopez@email.com,+34-555-123-456,2024-01-17
4,Ana Martínez,ana.martinez@email.com,+34-777-888-999,2024-01-18
5,Luis Rodríguez,luis.rodriguez@email.com,+34-111-222-333,2024-01-19"""
        
        csv_path = os.path.join(sample_dir, 'clientes_sample.csv')
        with open(csv_path, 'w', encoding='utf-8') as f:
            f.write(csv_content)
        
        # Crear JSON de ejemplo
        json_content = {
            "productos": [
                {
                    "producto_id": 1,
                    "nombre": "Laptop HP",
                    "categoria": "Electrónicos",
                    "precio": 799.99,
                    "stock": 25
                },
                {
                    "producto_id": 2,
                    "nombre": "Mouse Inalámbrico",
                    "categoria": "Accesorios",
                    "precio": 29.99,
                    "stock": 150
                },
                {
                    "producto_id": 3,
                    "nombre": "Teclado Mecánico",
                    "categoria": "Accesorios", 
                    "precio": 89.99,
                    "stock": 75
                }
            ]
        }
        
        json_path = os.path.join(sample_dir, 'productos_sample.json')
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(json_content, f, indent=2, ensure_ascii=False)
        
        logger.info(f"✅ Archivos de ejemplo creados en {sample_dir}")
        return True
    
    def setup_initial_config(self):
        """Configura parámetros iniciales del sistema"""
        logger.info("⚙️  Configurando parámetros iniciales...")
        
        # Aquí podrías agregar configuraciones adicionales como:
        # - Configuración de alertas
        # - Parámetros de calidad de datos
        # - Configuración de notificaciones
        # - etc.
        
        logger.info("✅ Configuración inicial completada")
        return True
    
    def seed_all(self):
        """Ejecuta todo el proceso de seeding"""
        logger.info("🌱 Iniciando carga de datos iniciales...")
        
        steps = [
            ("Fuentes de datos", self.seed_data_sources),
            ("Resúmenes de fuentes", self.seed_source_summaries),
            ("Tablas de staging", self.create_sample_staging_tables),
            ("Tablas de producción", self.create_production_tables),
            ("Datos de ejemplo", self.seed_sample_data),
            ("Archivos de ejemplo", self.create_sample_files),
            ("Configuración inicial", self.setup_initial_config)
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
    logger.info("CARGA DE DATOS INICIALES - DATA STAGING SYSTEM")
    logger.info("=" * 60)
    
    try:
        # Verificar configuración
        if not hasattr(settings, 'DATABASE_URL') or not settings.DATABASE_URL:
            logger.error("❌ DATABASE_URL no está configurada")
            return False
        
        # Cargar datos iniciales
        seeder = DataSeeder(settings.DATABASE_URL)
        success = seeder.seed_all()
        
        if success:
            logger.info("\n" + "=" * 60)
            logger.info("✅ CARGA DE DATOS INICIALES COMPLETADA EXITOSAMENTE")
            logger.info("=" * 60)
            logger.info("\nDatos cargados:")
            logger.info("• 4 fuentes de datos de ejemplo configuradas")
            logger.info("• Tablas de staging y producción creadas")
            logger.info("• Datos de ejemplo para testing")
            logger.info("• Archivos de muestra en data/sample/")
            logger.info("\nSistema listo para usar!")
            return True
        else:
            logger.error("\n" + "=" * 60)
            logger.error("❌ CARGA DE DATOS INICIALES FALLÓ")
            logger.error("=" * 60)
            return False
            
    except KeyboardInterrupt:
        logger.info("\n⏹️  Carga cancelada por el usuario")
        return False
    except Exception as e:
        logger.error(f"\n❌ Error inesperado: {e}")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)