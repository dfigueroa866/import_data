#!/usr/bin/env python3
"""
init_database.py - Script para inicializar la base de datos de M8 Connect

Este script:
1. Verifica la conexión a PostgreSQL
2. Crea la base de datos si no existe
3. Instala extensiones necesarias
4. Configura permisos básicos
"""

import os
import sys
import logging
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from urllib.parse import urlparse
import time

# Agregar el directorio src al path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

try:
    from data_staging.config import settings
except ImportError:
    # Fallback si no se puede importar la configuración
    class Settings:
        DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://staging_user:staging_pass@localhost:5432/staging_db')
    settings = Settings()

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class DatabaseInitializer:
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.parsed_url = urlparse(database_url)
        
        # Extraer componentes de la URL
        self.host = self.parsed_url.hostname
        self.port = self.parsed_url.port or 5432
        self.username = self.parsed_url.username
        self.password = self.parsed_url.password
        self.database = self.parsed_url.path[1:]  # Remover '/' inicial
        
        logger.info(f"Configuración de base de datos:")
        logger.info(f"  Host: {self.host}")
        logger.info(f"  Puerto: {self.port}")
        logger.info(f"  Usuario: {self.username}")
        logger.info(f"  Base de datos: {self.database}")
    
    def wait_for_postgres(self, max_retries: int = 30, delay: int = 2):
        """Espera a que PostgreSQL esté disponible"""
        logger.info("Esperando a que PostgreSQL esté disponible...")
        
        for attempt in range(max_retries):
            try:
                # Intentar conectar al servidor (no a la DB específica)
                conn = psycopg2.connect(
                    host=self.host,
                    port=self.port,
                    user=self.username,
                    password=self.password,
                    database='postgres'  # Usar la DB por defecto
                )
                conn.close()
                logger.info("✅ PostgreSQL está disponible")
                return True
                
            except psycopg2.OperationalError as e:
                logger.warning(f"Intento {attempt + 1}/{max_retries} - PostgreSQL no disponible: {e}")
                if attempt < max_retries - 1:
                    time.sleep(delay)
                else:
                    logger.error("❌ No se pudo conectar a PostgreSQL después de todos los intentos")
                    return False
        
        return False
    
    def database_exists(self) -> bool:
        """Verifica si la base de datos existe"""
        try:
            conn = psycopg2.connect(
                host=self.host,
                port=self.port,
                user=self.username,
                password=self.password,
                database='postgres'
            )
            conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
            
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM pg_catalog.pg_database WHERE datname = %s",
                (self.database,)
            )
            exists = cursor.fetchone() is not None
            
            cursor.close()
            conn.close()
            
            return exists
            
        except Exception as e:
            logger.error(f"Error verificando si la base de datos existe: {e}")
            return False
    
    def create_database(self):
        """Crea la base de datos si no existe"""
        if self.database_exists():
            logger.info(f"✅ La base de datos '{self.database}' ya existe")
            return True
        
        try:
            logger.info(f"📝 Creando base de datos '{self.database}'...")
            
            # Conectar a postgres para crear la nueva DB
            conn = psycopg2.connect(
                host=self.host,
                port=self.port,
                user=self.username,
                password=self.password,
                database='postgres'
            )
            conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
            
            cursor = conn.cursor()
            
            # Crear la base de datos
            cursor.execute(f'CREATE DATABASE "{self.database}"')
            
            cursor.close()
            conn.close()
            
            logger.info(f"✅ Base de datos '{self.database}' creada exitosamente")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error creando la base de datos: {e}")
            return False
    
    def install_extensions(self):
        """Instala extensiones necesarias de PostgreSQL"""
        extensions = [
            'uuid-ossp',     # Para generar UUIDs
            'pg_stat_statements',  # Para estadísticas de consultas
            'pg_trgm'        # Para búsquedas de texto similares
        ]
        
        try:
            logger.info("📦 Instalando extensiones de PostgreSQL...")
            
            conn = psycopg2.connect(
                host=self.host,
                port=self.port,
                user=self.username,
                password=self.password,
                database=self.database
            )
            conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
            
            cursor = conn.cursor()
            
            for extension in extensions:
                try:
                    cursor.execute(f'CREATE EXTENSION IF NOT EXISTS "{extension}"')
                    logger.info(f"✅ Extensión '{extension}' instalada")
                except Exception as e:
                    logger.warning(f"⚠️  No se pudo instalar la extensión '{extension}': {e}")
            
            cursor.close()
            conn.close()
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error instalando extensiones: {e}")
            return False
    
    def test_connection(self) -> bool:
        """Prueba la conexión final a la base de datos"""
        try:
            logger.info("🔍 Probando conexión final...")
            
            conn = psycopg2.connect(
                host=self.host,
                port=self.port,
                user=self.username,
                password=self.password,
                database=self.database
            )
            
            cursor = conn.cursor()
            cursor.execute('SELECT version()')
            version = cursor.fetchone()[0]
            
            cursor.close()
            conn.close()
            
            logger.info(f"✅ Conexión exitosa. PostgreSQL version: {version}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error en la conexión final: {e}")
            return False
    
    def initialize(self) -> bool:
        """Ejecuta el proceso completo de inicialización"""
        logger.info("🚀 Iniciando inicialización de la base de datos...")
        
        # 1. Esperar a que PostgreSQL esté disponible
        if not self.wait_for_postgres():
            return False
        
        # 2. Crear la base de datos
        if not self.create_database():
            return False
        
        # 3. Instalar extensiones
        if not self.install_extensions():
            return False
        
        # 4. Probar conexión final
        if not self.test_connection():
            return False
        
        logger.info("🎉 Inicialización de base de datos completada exitosamente")
        return True

def main():
    """Función principal"""
    logger.info("=" * 60)
    logger.info("INICIALIZADOR DE BASE DE DATOS - M8 CONNECT")
    logger.info("=" * 60)
    
    try:
        # Verificar que la URL de la base de datos esté configurada
        if not hasattr(settings, 'DATABASE_URL') or not settings.DATABASE_URL:
            logger.error("❌ DATABASE_URL no está configurada")
            logger.info("💡 Asegúrate de tener un archivo .env con DATABASE_URL configurado")
            return False
        
        # Inicializar la base de datos
        initializer = DatabaseInitializer(settings.DATABASE_URL)
        success = initializer.initialize()
        
        if success:
            logger.info("\n" + "=" * 60)
            logger.info("✅ INICIALIZACIÓN COMPLETADA EXITOSAMENTE")
            logger.info("=" * 60)
            logger.info("\nPróximos pasos:")
            logger.info("1. Ejecutar: python scripts/setup/create_schemas.py")
            logger.info("2. Ejecutar: alembic upgrade head")
            logger.info("3. Ejecutar: python scripts/setup/seed_data.py")
            return True
        else:
            logger.error("\n" + "=" * 60)
            logger.error("❌ INICIALIZACIÓN FALLÓ")
            logger.error("=" * 60)
            return False
            
    except KeyboardInterrupt:
        logger.info("\n⏹️  Inicialización cancelada por el usuario")
        return False
    except Exception as e:
        logger.error(f"\n❌ Error inesperado: {e}")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)