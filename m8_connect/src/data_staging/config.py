# src/data_staging/config.py
"""
Configuración centralizada del sistema con soporte para PostgreSQL y Supabase
"""

import os
from typing import List, Dict, Any, Optional
from pydantic_settings import BaseSettings
from pydantic import Field, validator, AnyHttpUrl
from enum import Enum

class Environment(str, Enum):
    """Entornos de ejecución"""
    DEVELOPMENT = "development"
    TESTING = "testing"
    STAGING = "staging"
    PRODUCTION = "m8_schema"

class DatabaseType(str, Enum):
    """Tipos de base de datos soportados"""
    POSTGRESQL = "postgresql"

class Settings(BaseSettings):
    """Configuración principal del sistema"""
    
    # === CONFIGURACIÓN DE ENTORNO ===
    ENVIRONMENT: Environment = Field(Environment.DEVELOPMENT, description="Entorno de ejecución")
    DEBUG: bool = Field(False, description="Modo debug")
    LOG_LEVEL: str = Field("INFO", description="Nivel de logging")
    
    # === CONFIGURACIÓN DE BASE DE DATOS ===
    DATABASE_URL: str = Field(..., description="URL de conexión a la base de datos")
    DATABASE_TYPE: Optional[DatabaseType] = Field(None, description="Tipo de base de datos")
    DATABASE_URL_TEST: Optional[str] = Field(None, description="URL de base de datos para testing")
    
    # Configuración de pool de conexiones
    DB_POOL_SIZE: int = Field(10, description="Tamaño del pool de conexiones")
    DB_MAX_OVERFLOW: int = Field(20, description="Máximo overflow del pool")
    DB_POOL_TIMEOUT: int = Field(30, description="Timeout del pool")
    DB_POOL_RECYCLE: int = Field(3600, description="Tiempo de reciclaje de conexiones")
    

    
    # === CONFIGURACIÓN DE API ===
    API_HOST: str = Field("0.0.0.0", description="Host de la API")
    API_PORT: int = Field(8000, description="Puerto de la API")
    API_PREFIX: str = Field("/api/v1", description="Prefijo de la API")
    API_TITLE: str = Field("M8 Connect", description="Título de la API")
    API_VERSION: str = Field("1.0.0", description="Versión de la API")
    
    # === CONFIGURACIÓN DE ARCHIVOS ===
    UPLOAD_PATH: str = Field("./data/uploads", description="Directorio de archivos subidos")
    TEMP_PATH: str = Field("./data/temp", description="Directorio temporal")
    BACKUP_PATH: str = Field("./backups", description="Directorio de backups")
    MAX_FILE_SIZE: int = Field(2 * 1024 * 1024 * 1024, description="Tamaño máximo de archivo (bytes)")
    ALLOWED_FILE_EXTENSIONS: List[str] = Field(
        [".csv", ".xlsx", ".xls", ".json", ".parquet"], 
        description="Extensiones de archivo permitidas"
    )
    
    # === CONFIGURACIÓN DE VALIDACIÓN ===
    MAX_ERROR_RATE: float = Field(0.05, description="Tasa máxima de errores permitida")
    MIN_QUALITY_SCORE: int = Field(95, description="Score mínimo de calidad de datos")
    VALIDATION_TIMEOUT: int = Field(300, description="Timeout de validación en segundos")
    PROCESS_CHUNK_SIZE: int = Field(250_000, description="Filas por chunk en PROCESS_FILE")
    AGGREGATION_CHUNK_SIZE: int = Field(500_000, description="Filas por chunk en agregación")
    AGG_SPILL_THRESHOLD_ROWS: int = Field(
        5_000_000,
        description="A partir de este volumen, agregación usa spill-to-disk en lugar de reduce solo en RAM",
    )
    AGG_IN_MEMORY_MAX_ROWS: int = Field(
        10_000_000,
        description="Máximo de filas de entrada para intentar reduce incremental solo en RAM",
    )
    AGG_ACC_MAX_ROWS: int = Field(
        3_000_000,
        description="Si el acumulador supera este tamaño durante reduce, cambiar a spill",
    )
    PREVIEW_JOB_TIMEOUT: int = Field(
        0,
        description="Timeout del job PREVIEW_BATCH en segundos (0 = sin límite)",
    )
    PARQUET_COMPRESSION: str = Field("snappy", description="Compresión Parquet (snappy/gzip)")
    PROGRESS_COMMIT_EVERY_CHUNKS: int = Field(2, description="Actualizar progreso cada N chunks")
    PROGRESS_ROW_INTERVAL: int = Field(50000, description="Filas entre updates de progreso intra-chunk")
    PROGRESS_UPDATE_INTERVAL_SEC: float = Field(
        15.0, description="Mínimo segundos entre escrituras de progreso a BD (worker)"
    )
    PROMOTION_PROGRESS_EVERY_CHUNKS: int = Field(
        3, description="Reportar progreso de promoción cada N chunks UPSERT"
    )
    API_DB_POOL_SIZE: int = Field(25, description="Pool SQLAlchemy del API (run_app)")
    API_DB_MAX_OVERFLOW: int = Field(45, description="Overflow del pool SQLAlchemy del API")
    USE_VECTORIZED_VALIDATION: bool = Field(
        True,
        description="Validación vectorizada Polars (paridad con legacy vía tests)",
    )
    PROMOTION_BATCH_SIZE: int = Field(
        250_000, description="Filas por chunk en PROMOTE_BATCH"
    )
    PROMOTION_METADATA_EVERY_CHUNKS: int = Field(
        3, description="Persistir metadata promoted_rows cada N chunks UPSERT"
    )
    PROMOTION_WORK_MEM: str = Field(
        "512MB", description="work_mem de sesión durante promoción masiva"
    )
    PROMOTION_SYNCHRONOUS_COMMIT: bool = Field(
        False,
        description="Si False, SET synchronous_commit=off en worker de promoción",
    )
    USE_VALIDATION_MULTIPROCESSING: bool = Field(
        False,
        description="Validación en paralelo (solo sin claves compuestas; ver parallel_validation)",
    )
    VALIDATION_WORKER_PROCESSES: int = Field(
        2, description="Procesos para validación paralela opcional"
    )
    PARALLEL_VALIDATION_MIN_ROWS: int = Field(
        500_000,
        description="Mínimo de filas para activar validación multiproceso",
    )
    ARROW_COPY_MIN_ROWS: int = Field(
        10_000,
        description="Usar COPY PyArrow solo desde este número de filas por chunk",
    )
    VECTORIZED_ID_MIN_ROWS: int = Field(
        10_000,
        description="Generación vectorizada de id solo en chunks >= este tamaño",
    )
    
    # === CONFIGURACIÓN DE ETL ===
    ETL_BATCH_SIZE: int = Field(10000, description="Tamaño de lote para procesamiento ETL")
    ETL_MAX_RETRIES: int = Field(3, description="Máximo número de reintentos")
    ETL_RETRY_DELAY: int = Field(60, description="Delay entre reintentos en segundos")
    
    # === CONFIGURACIÓN DE MONITOREO ===
    ENABLE_MONITORING: bool = Field(True, description="Habilitar monitoreo")
    MONITORING_INTERVAL: int = Field(300, description="Intervalo de monitoreo en segundos")
    ALERT_EMAIL_ENABLED: bool = Field(False, description="Habilitar alertas por email")
    ALERT_SLACK_ENABLED: bool = Field(False, description="Habilitar alertas por Slack")
    
    # === CONFIGURACIÓN DE EMAIL ===
    SMTP_SERVER: Optional[str] = Field(None, description="Servidor SMTP")
    SMTP_PORT: int = Field(587, description="Puerto SMTP")
    SMTP_USERNAME: Optional[str] = Field(None, description="Usuario SMTP")
    SMTP_PASSWORD: Optional[str] = Field(None, description="Contraseña SMTP")
    SMTP_USE_TLS: bool = Field(True, description="Usar TLS para SMTP")
    EMAIL_FROM: Optional[str] = Field(None, description="Email remitente")
    EMAIL_USERNAME: Optional[str] = Field(None, description="Usuario de email")
    EMAIL_PASSWORD: Optional[str] = Field(None, description="Contraseña de email")
    
    # === CONFIGURACIÓN DE SLACK ===
    SLACK_WEBHOOK_URL: Optional[AnyHttpUrl] = Field(None, description="Webhook URL de Slack")
    SLACK_CHANNEL: str = Field("#data-alerts", description="Canal de Slack para alertas")
    
    # === CONFIGURACIÓN DE AWS ===
    AWS_ACCESS_KEY_ID: Optional[str] = Field(None, description="AWS Access Key ID")
    AWS_SECRET_ACCESS_KEY: Optional[str] = Field(None, description="AWS Secret Access Key")
    AWS_REGION: str = Field("us-east-1", description="Región de AWS")
    AWS_S3_BUCKET: Optional[str] = Field(None, description="Bucket S3 para backups")
    BACKUP_S3_BUCKET: Optional[str] = Field(None, description="Bucket S3 para backups")
    
    # === CONFIGURACIÓN DE PREFECT ===
    PREFECT_API_URL: Optional[AnyHttpUrl] = Field(None, description="URL de la API de Prefect")
    PREFECT_WORKSPACE: Optional[str] = Field(None, description="Workspace de Prefect")
    
    # === CONFIGURACIÓN DE SEGURIDAD ===
    SECRET_KEY: str = Field("development-secret-key-must-be-at-least-32-characters-long", description="Clave secreta para tokens")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(15, description="Minutos de expiración del access token")
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(7, description="Días de validez del refresh token")
    SESSION_INACTIVITY_MINUTES: int = Field(
        15, description="Minutos de inactividad antes de cerrar sesión (referencia frontend)"
    )
    ALGORITHM: str = Field("HS256", description="Algoritmo de encriptación")
    
    # === CONFIGURACIÓN DE LOGGING ===
    LOG_FORMAT: str = Field("detailed", description="Formato de logging")
    
    # === CONFIGURACIÓN DE CACHE ===
    REDIS_URL: Optional[str] = Field(None, description="URL de Redis para cache")
    CACHE_TTL: int = Field(300, description="TTL del cache en segundos")
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        

    
    @validator('UPLOAD_PATH', 'TEMP_PATH', 'BACKUP_PATH')
    def create_directories(cls, v):
        """Crea directorios si no existen"""
        import os
        os.makedirs(v, exist_ok=True)
        return v
    
    @validator('SECRET_KEY')
    def validate_secret_key(cls, v):
        """Valida que la clave secreta tenga longitud mínima"""
        if len(v) < 32:
            raise ValueError('SECRET_KEY debe tener al menos 32 caracteres')
        return v
    
    @property
    def is_development(self) -> bool:
        """Verifica si estamos en entorno de desarrollo"""
        return self.ENVIRONMENT == Environment.DEVELOPMENT
    
    @property
    def is_production(self) -> bool:
        """Verifica si estamos en entorno de producción"""
        return self.ENVIRONMENT == Environment.PRODUCTION
    
    @property
    def is_testing(self) -> bool:
        """Verifica si estamos en entorno de testing"""
        return self.ENVIRONMENT == Environment.TESTING
    
    @property
    def is_postgresql(self) -> bool:
        """Verifica si estamos usando PostgreSQL tradicional"""
        return self.DATABASE_TYPE == DatabaseType.POSTGRESQL
    
    @property
    def database_config(self) -> Dict[str, Any]:
        """Retorna configuración específica de la base de datos"""
        return {
            "database_url": self.DATABASE_URL,
            "database_type": self.DATABASE_TYPE,
            "pool_size": self.DB_POOL_SIZE,
            "max_overflow": self.DB_MAX_OVERFLOW,
            "pool_timeout": self.DB_POOL_TIMEOUT,
            "pool_recycle": self.DB_POOL_RECYCLE,
        }
    
    def get_database_url_for_env(self, environment: str = None) -> str:
        """Obtiene la URL de base de datos para un entorno específico"""
        if environment == "test" and self.DATABASE_URL_TEST:
            return self.DATABASE_URL_TEST
        return self.DATABASE_URL

# Configuraciones específicas por entorno
class DevelopmentSettings(Settings):
    """Configuración para entorno de desarrollo"""
    ENVIRONMENT: Environment = Environment.DEVELOPMENT
    DEBUG: bool = True
    LOG_LEVEL: str = "DEBUG"
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10

class TestingSettings(Settings):
    """Configuración para entorno de testing"""
    ENVIRONMENT: Environment = Environment.TESTING
    DEBUG: bool = True
    LOG_LEVEL: str = "DEBUG"
    DB_POOL_SIZE: int = 2
    DB_MAX_OVERFLOW: int = 5
    
    @validator('DATABASE_URL', pre=True, always=True)
    def use_test_database(cls, v, values):
        """Usa la base de datos de testing si está configurada"""
        test_url = values.get('DATABASE_URL_TEST')
        if test_url:
            return test_url
        return v

class ProductionSettings(Settings):
    """Configuración para entorno de producción"""
    ENVIRONMENT: Environment = Environment.PRODUCTION
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    ENABLE_MONITORING: bool = True
    ALERT_EMAIL_ENABLED: bool = True

def get_settings() -> Settings:
    """Factory para obtener la configuración según el entorno"""
    env = os.getenv("ENVIRONMENT", "development").lower()
    
    if env == "public":
        return ProductionSettings()
    elif env == "testing":
        return TestingSettings()
    elif env == "development":
        return DevelopmentSettings()
    else:
        return Settings()

# Instancia global de configuración
settings = get_settings()

# Información de la aplicación
APP_INFO = {
    "title": settings.API_TITLE,
    "version": settings.API_VERSION,
    "description": """
    M8 Connect — plataforma de ingesta con soporte para PostgreSQL.
    
    Características:
    - Soporte para PostgreSQL
    - Validaciones automáticas de calidad de datos
    - API REST completa para gestión de cargas
    - Dashboard de monitoreo en tiempo real
    - Integración con flujos ETL automatizados
    """,
    "contact": {
        "name": "Data Team",
        "email": "data-team@company.com",
    },
    "license_info": {
        "name": "MIT License",
        "url": "https://opensource.org/licenses/MIT",
    },
}