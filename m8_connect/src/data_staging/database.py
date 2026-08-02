# src/data_staging/database.py
"""
Configuración de base de datos para PostgreSQL y Supabase

Este módulo maneja automáticamente la configuración para:
- PostgreSQL tradicional (local o remoto)
- Supabase (cloud PostgreSQL con características específicas)
"""

import os
import logging
from pathlib import Path
from enum import Enum
from typing import Optional, Dict, Any
from urllib.parse import urlparse, parse_qs
from sqlalchemy import create_engine, text, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import NullPool, QueuePool
from pydantic import Field, validator
from pydantic_settings import BaseSettings
import httpx

logger = logging.getLogger(__name__)

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    # Load .env from project root
    env_path = Path(__file__).parent.parent.parent / '.env'
    if env_path.exists():
        load_dotenv(env_path)
        logger.debug(f"Loaded .env from {env_path}")
    else:
        logger.warning(f".env file not found at {env_path}")
except ImportError:
    logger.warning("python-dotenv not available, trying manual loading")
    # If python-dotenv not available, try manual loading
    env_path = Path(__file__).parent.parent.parent / '.env'
    if env_path.exists():
        with open(env_path, 'r') as f:
            for line in f:
                if '=' in line and not line.strip().startswith('#'):
                    key, value = line.strip().split('=', 1)
                    os.environ[key] = value



class DatabaseType(str, Enum):
    """Tipos de base de datos soportados"""
    POSTGRESQL = "postgresql"

class DatabaseConfig(BaseSettings):
    """Configuración de base de datos con soporte para PostgreSQL y Supabase"""
    
    # Configuración general
    DATABASE_URL: str = Field(..., description="URL de conexión a la base de datos")
    DATABASE_TYPE: DatabaseType = DatabaseType.POSTGRESQL
    
    # Configuración de SSL
    SSL_REQUIRE: bool = Field(True, description="Requerir SSL")
    SSL_MODE: str = Field("prefer", description="Modo SSL")
    
    # Configuración de timeouts
    CONNECT_TIMEOUT: int = Field(10, description="Timeout de conexión")
    COMMAND_TIMEOUT: int = Field(60, description="Timeout de comandos")
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"
    
    # Configuración de pool de conexiones (API / SQLAlchemy)
    POOL_SIZE: int = Field(25, description="Tamaño del pool de conexiones")
    MAX_OVERFLOW: int = Field(45, description="Máximo overflow del pool")
    POOL_TIMEOUT: int = Field(30, description="Timeout del pool en segundos")
    POOL_RECYCLE: int = Field(3600, description="Tiempo de reciclaje de conexiones en segundos")

def _is_local_database_url(database_url: str) -> bool:
    """True cuando la URL apunta a localhost (túnel SSH o Postgres local)."""
    hostname = (urlparse(database_url).hostname or "").lower()
    return hostname in {"localhost", "127.0.0.1", "::1"}


def _build_database_config() -> DatabaseConfig:
    """Construye DatabaseConfig desde settings (fuente única de verdad)."""
    from data_staging.config import settings

    database_url = str(settings.DATABASE_URL)
    return DatabaseConfig(
        DATABASE_URL=database_url,
        POOL_SIZE=settings.API_DB_POOL_SIZE,
        MAX_OVERFLOW=settings.API_DB_MAX_OVERFLOW,
        SSL_REQUIRE=not _is_local_database_url(database_url),
    )


class DatabaseManager:
    """Gestor de base de datos que maneja PostgreSQL y Supabase"""
    
    def __init__(self, config: DatabaseConfig):
        self.config = config
        self.database_type = DatabaseType.POSTGRESQL
        self._engine: Optional[Engine] = None
        self._session_factory: Optional[sessionmaker] = None
        
        logger.info("Inicializando DatabaseManager para PostgreSQL")
    
    def _create_postgresql_engine(self) -> Engine:
        """Crea engine para PostgreSQL tradicional"""
        logger.info("Configurando engine para PostgreSQL")
        
        connect_args = {
            "connect_timeout": self.config.CONNECT_TIMEOUT,
            "options": f"-c statement_timeout={self.config.COMMAND_TIMEOUT * 1000}",  # milliseconds
            "application_name": "m8_connect"
        }
        
        # Configurar SSL si es necesario
        if self.config.SSL_REQUIRE:
            connect_args["sslmode"] = self.config.SSL_MODE
        
        engine = create_engine(
            self.config.DATABASE_URL,
            poolclass=QueuePool,
            pool_size=self.config.POOL_SIZE,
            max_overflow=self.config.MAX_OVERFLOW,
            pool_timeout=self.config.POOL_TIMEOUT,
            pool_recycle=self.config.POOL_RECYCLE,
            pool_pre_ping=True,  # Detecta conexiones muertas ANTES de usarlas
            connect_args=connect_args,
            echo=False  # Cambiar a True para debug SQL
        )
        logger.info(
            "PostgreSQL pool: size=%s overflow=%s timeout=%ss",
            self.config.POOL_SIZE,
            self.config.MAX_OVERFLOW,
            self.config.POOL_TIMEOUT,
        )
        
        # Configurar eventos del engine
        self._setup_engine_events(engine)
        
        return engine
    

    
    def _setup_engine_events(self, engine: Engine):
        """Configura eventos comunes del engine"""
        
        @event.listens_for(engine, "connect")
        def set_postgresql_settings(dbapi_connection, connection_record):
            """Configura settings específicos de PostgreSQL"""
            with dbapi_connection.cursor() as cursor:
                # Configurar timezone
                cursor.execute("SET timezone TO 'UTC'")
                
                # Configurar formato de fechas
                cursor.execute("SET datestyle TO 'ISO, MDY'")
                
                # Configurar búsqueda de esquemas
                cursor.execute("SET search_path TO staging_meta, staging_data, m8_schema, public")
                
                logger.debug("Configuraciones PostgreSQL aplicadas")
    

    
    @property
    def engine(self) -> Engine:
        """Obtiene o crea el engine de base de datos"""
        if self._engine is None:
            self._engine = self._create_postgresql_engine()
        return self._engine
    
    @property
    def session_factory(self) -> sessionmaker:
        """Obtiene o crea el factory de sesiones"""
        if self._session_factory is None:
            self._session_factory = sessionmaker(
                bind=self.engine,
                autocommit=False,
                autoflush=False,
                expire_on_commit=False
            )
        
        return self._session_factory
    
    def get_session(self) -> Session:
        """Crea una nueva sesión de base de datos"""
        return self.session_factory()
    
    def test_connection(self) -> Dict[str, Any]:
        """Prueba la conexión y retorna información del servidor"""
        try:
            with self.engine.begin() as conn:
                # Información básica del servidor (PostgreSQL)
                result = conn.execute(text("SELECT version()"))
                version = result.scalar()
                
                # Información de la base de datos actual
                result = conn.execute(text("SELECT current_database(), current_user, inet_server_addr(), inet_server_port()"))
                db_info = result.fetchone()
                
                # Verificar extensiones disponibles
                result = conn.execute(text("""
                    SELECT extname FROM pg_extension 
                    WHERE extname IN ('uuid-ossp', 'pg_stat_statements', 'pg_trgm')
                """))
                extensions = [row[0] for row in result]
                
                info = {
                    "status": "connected",
                    "database_type": self.database_type,
                    "version": version,
                    "database": db_info[0],
                    "user": db_info[1],
                    "server_addr": db_info[2],
                    "server_port": db_info[3],
                    "extensions": extensions,
                    "pool_size": self.engine.pool.size(),
                    "checked_out": self.engine.pool.checkedout(),
                }
                
                logger.info(f"Conexión exitosa a {self.database_type}")
                return info
                
        except Exception as e:
            logger.error(f"Error probando conexión: {e}")
            return {
                "status": "error",
                "database_type": self.database_type,
                "error": str(e)
            }
    
    def get_database_info(self) -> Dict[str, Any]:
        """Obtiene información completa de la base de datos"""
        return self.test_connection()
    
    def close(self):
        """Cierra todas las conexiones"""
        if self._engine:
            self._engine.dispose()
            self._engine = None
            logger.info("Engine de base de datos cerrado")

# Instancia global del gestor de base de datos
_database_manager: Optional[DatabaseManager] = None

def get_database_manager() -> DatabaseManager:
    """Obtiene la instancia global del gestor de base de datos"""
    global _database_manager
    
    if _database_manager is None:
        _database_manager = DatabaseManager(_build_database_config())
    
    return _database_manager

def get_database_session() -> Session:
    """Obtiene una nueva sesión de base de datos"""
    return get_database_manager().get_session()

def get_database_engine() -> Engine:
    """Obtiene el engine de base de datos"""
    return get_database_manager().engine

# Dependency para FastAPI
async def get_db_session():
    """Dependency de FastAPI para obtener sesión de base de datos"""
    session = get_database_session()
    try:
        yield session
    finally:
        session.close()

# Funciones de utilidad
def is_postgresql() -> bool:
    """Verifica si estamos usando PostgreSQL tradicional"""
    return True

def get_database_type() -> DatabaseType:
    """Obtiene el tipo de base de datos en uso"""
    return DatabaseType.POSTGRESQL