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
    SUPABASE = "supabase"
    CLICKHOUSE = "clickhouse"

class DatabaseConfig(BaseSettings):
    """Configuración de base de datos con soporte para PostgreSQL y Supabase"""
    
    # Configuración general
    DATABASE_URL: str = Field(..., description="URL de conexión a la base de datos")
    DATABASE_TYPE: Optional[DatabaseType] = Field(None, description="Tipo de base de datos (auto-detectado si no se especifica)")
    
    # Configuración de pool de conexiones
    POOL_SIZE: int = Field(10, description="Tamaño del pool de conexiones")
    MAX_OVERFLOW: int = Field(20, description="Máximo overflow del pool")
    POOL_TIMEOUT: int = Field(30, description="Timeout del pool en segundos")
    POOL_RECYCLE: int = Field(3600, description="Tiempo de reciclaje de conexiones en segundos")
    
    # Configuración específica de Supabase
    SUPABASE_URL: Optional[str] = Field(None, description="URL base de Supabase")
    SUPABASE_ANON_KEY: Optional[str] = Field(None, description="Clave anónima de Supabase")
    SUPABASE_SERVICE_ROLE_KEY: Optional[str] = Field(None, description="Clave de service role de Supabase")
    
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
    
    @validator('DATABASE_TYPE', pre=True, always=True)
    def auto_detect_database_type(cls, v, values):
        """Auto-detecta el tipo de base de datos basado en la URL"""
        if v is not None:
            return v
        
        database_url = values.get('DATABASE_URL', '')
        if not database_url:
            return DatabaseType.POSTGRESQL
        
        # Detectar Supabase por la URL
        if 'supabase.co' in database_url or 'supabase.com' in database_url:
            return DatabaseType.SUPABASE
        elif database_url.startswith('clickhouse'):
            return DatabaseType.CLICKHOUSE
        else:
            return DatabaseType.POSTGRESQL
    
    @validator('SUPABASE_URL', pre=True, always=True) 
    def extract_supabase_url(cls, v, values):
        """Extrae la URL de Supabase desde DATABASE_URL si no está especificada"""
        if v is not None:
            return v
        
        database_url = values.get('DATABASE_URL', '')
        database_type = values.get('DATABASE_TYPE')
        
        if database_type == DatabaseType.SUPABASE and 'supabase.co' in database_url:
            parsed = urlparse(database_url)
            # Extraer el proyecto ID del hostname (ej: xxxxx.supabase.co)
            project_id = parsed.hostname.split('.')[0]
            return f"https://{project_id}.supabase.co"
        
        return v

class DatabaseManager:
    """Gestor de base de datos que maneja PostgreSQL y Supabase"""
    
    def __init__(self, config: DatabaseConfig):
        self.config = config
        self.database_type = config.DATABASE_TYPE
        self._engine: Optional[Engine] = None
        self._session_factory: Optional[sessionmaker] = None
        
        logger.info(f"Inicializando DatabaseManager para {self.database_type}")
    
    def _create_postgresql_engine(self) -> Engine:
        """Crea engine para PostgreSQL tradicional"""
        logger.info("Configurando engine para PostgreSQL")
        
        connect_args = {
            "connect_timeout": self.config.CONNECT_TIMEOUT,
            "options": f"-c statement_timeout={self.config.COMMAND_TIMEOUT * 1000}"  # milliseconds
        }
        
        # Configurar SSL si es necesario
        if self.config.SSL_REQUIRE:
            connect_args["sslmode"] = self.config.SSL_MODE
        
        engine = create_engine(
            self.config.DATABASE_URL,
            poolclass=QueuePool,
            pool_size=15,  # Aumentado de 10 a 15
            max_overflow=30,  # Aumentado de 20 a 30
            pool_timeout=self.config.POOL_TIMEOUT,
            pool_recycle=self.config.POOL_RECYCLE,
            pool_pre_ping=True,  # Detecta conexiones muertas ANTES de usarlas
            connect_args=connect_args,
            echo=False  # Cambiar a True para debug SQL
        )
        
        # Configurar eventos del engine
        self._setup_engine_events(engine)
        
        return engine
    
    def _create_clickhouse_engine(self) -> Engine:
        """Crea engine para ClickHouse"""
        logger.info("Configurando engine para ClickHouse")
        
        # El connect_args para clickhouse-connect (via clickhouse-sqlalchemy)
        connect_args = {
            "connect_timeout": self.config.CONNECT_TIMEOUT,
            "send_receive_timeout": self.config.COMMAND_TIMEOUT,
        }
        
        engine = create_engine(
            self.config.DATABASE_URL,
            poolclass=QueuePool,
            pool_size=15,
            max_overflow=30,
            pool_timeout=self.config.POOL_TIMEOUT,
            pool_recycle=self.config.POOL_RECYCLE,
            pool_pre_ping=True,
            connect_args=connect_args,
            echo=False
        )
        
        return engine
    
    def _create_supabase_engine(self) -> Engine:
        """Crea engine para Supabase con configuraciones específicas"""
        logger.info("Configurando engine para Supabase")
        
        # Supabase requiere SSL y tiene configuraciones específicas
        connect_args = {
            "connect_timeout": self.config.CONNECT_TIMEOUT,
            "sslmode": "require",  # Supabase siempre requiere SSL
            "options": f"-c statement_timeout={self.config.COMMAND_TIMEOUT * 1000}",
            "application_name": "data_staging_system",
            "keepalives": 1,
            "keepalives_idle": 30,
            "keepalives_interval": 10,
            "keepalives_count": 5
        }
        
        # Pool configuration optimizada para Supabase
        engine = create_engine(
            self.config.DATABASE_URL,
            poolclass=QueuePool,
            pool_size=8,  # Aumentado de 3 a 8 para soportar más uploads concurrentes
            max_overflow=12,  # Aumentado de 2 a 12 para picos de carga
            pool_timeout=45,  # Aumentado de 30 a 45 segundos
            pool_recycle=1800,  # Reducido de 3600 a 1800 (30 min) para conexiones más frescas
            pool_pre_ping=True,  # Ya estaba configurado - mantener
            connect_args=connect_args,
            echo=False
        )
        
        # Configurar eventos específicos para Supabase
        self._setup_supabase_events(engine)
        
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
    
    def _setup_supabase_events(self, engine: Engine):
        """Configura eventos específicos para Supabase"""
        
        @event.listens_for(engine, "connect")
        def set_supabase_settings(dbapi_connection, connection_record):
            """Configura settings específicos de Supabase"""
            with dbapi_connection.cursor() as cursor:
                # Configuraciones básicas
                cursor.execute("SET timezone TO 'UTC'")
                cursor.execute("SET datestyle TO 'ISO, MDY'")
                cursor.execute("SET search_path TO staging_meta, staging_data, m8_schema, public")
                
                # Configuraciones específicas de Supabase
                cursor.execute("SET statement_timeout TO '60s'")
                cursor.execute("SET lock_timeout TO '30s'")
                
                logger.debug("Configuraciones Supabase aplicadas")
        
        @event.listens_for(engine, "checkout")
        def check_connection(dbapi_connection, connection_record, connection_proxy):
            """Verifica la conexión antes de usar (importante en Supabase)"""
            try:
                with dbapi_connection.cursor() as cursor:
                    cursor.execute("SELECT 1")
            except Exception as e:
                logger.warning(f"Conexión inválida detectada: {e}")
                # Forzar reconexión
                connection_record.invalidate()
                raise
    
    @property
    def engine(self) -> Engine:
        """Obtiene o crea el engine de base de datos"""
        if self._engine is None:
            if self.database_type == DatabaseType.SUPABASE:
                self._engine = self._create_supabase_engine()
            elif self.database_type == DatabaseType.CLICKHOUSE:
                self._engine = self._create_clickhouse_engine()
            else:
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
                if self.database_type == DatabaseType.CLICKHOUSE:
                    result = conn.execute(text("SELECT version()"))
                    version = result.scalar()
                    
                    result = conn.execute(text("SELECT currentDatabase(), currentUser()"))
                    db_info = result.fetchone()
                    
                    info = {
                        "status": "connected",
                        "database_type": self.database_type,
                        "version": version,
                        "database": db_info[0] if db_info else None,
                        "user": db_info[1] if db_info else None,
                        "pool_size": self.engine.pool.size(),
                        "checked_out": self.engine.pool.checkedout(),
                    }
                else:
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
    
    def check_supabase_api_access(self) -> Dict[str, Any]:
        """Verifica acceso a la API de Supabase (solo para tipo Supabase)"""
        if self.database_type != DatabaseType.SUPABASE:
            return {"status": "not_applicable", "message": "No es una instancia de Supabase"}
        
        if not self.config.SUPABASE_URL or not self.config.SUPABASE_ANON_KEY:
            return {"status": "missing_config", "message": "Faltan configuraciones de Supabase API"}
        
        try:
            headers = {
                "apikey": self.config.SUPABASE_ANON_KEY,
                "Authorization": f"Bearer {self.config.SUPABASE_ANON_KEY}"
            }
            
            # Probar endpoint de salud de Supabase
            response = httpx.get(
                f"{self.config.SUPABASE_URL}/rest/v1/",
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 200:
                return {
                    "status": "api_accessible",
                    "supabase_url": self.config.SUPABASE_URL,
                    "api_version": response.headers.get("x-supabase-api-version", "unknown")
                }
            else:
                return {
                    "status": "api_error",
                    "status_code": response.status_code,
                    "message": "API no accesible"
                }
                
        except Exception as e:
            return {
                "status": "api_error",
                "error": str(e)
            }
    
    def get_database_info(self) -> Dict[str, Any]:
        """Obtiene información completa de la base de datos"""
        info = self.test_connection()
        
        if self.database_type == DatabaseType.SUPABASE:
            supabase_info = self.check_supabase_api_access()
            info["supabase_api"] = supabase_info
        
        return info
    
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
        config = DatabaseConfig()
        _database_manager = DatabaseManager(config)
    
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
def is_supabase() -> bool:
    """Verifica si estamos usando Supabase"""
    return get_database_manager().database_type == DatabaseType.SUPABASE

def is_postgresql() -> bool:
    """Verifica si estamos usando PostgreSQL tradicional"""
    return get_database_manager().database_type == DatabaseType.POSTGRESQL

def get_database_type() -> DatabaseType:
    """Obtiene el tipo de base de datos en uso"""
    return get_database_manager().database_type