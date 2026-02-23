#!/usr/bin/env python3
"""
database_switcher.py - Herramienta para cambiar entre PostgreSQL y Supabase

Este script ayuda a:
1. Cambiar la configuración entre PostgreSQL y Supabase
2. Migrar datos entre diferentes bases de datos
3. Actualizar archivos de configuración automáticamente
4. Verificar compatibilidad antes del cambio
"""

import os
import sys
import logging
import shutil
from pathlib import Path
from typing import Dict, Any, Optional
import argparse
from datetime import datetime

# Agregar el directorio src al path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

try:
    from data_staging.config import settings, DatabaseType
    from data_staging.database import DatabaseManager, DatabaseConfig
except ImportError as e:
    logging.error(f"Error importando configuración: {e}")
    sys.exit(1)

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class DatabaseSwitcher:
    def __init__(self):
        self.project_root = Path(__file__).parent.parent.parent
        self.env_file = self.project_root / ".env"
        self.env_backup_dir = self.project_root / "config" / "backups"
        self.env_backup_dir.mkdir(parents=True, exist_ok=True)
    
    def backup_current_env(self) -> str:
        """Crea backup del archivo .env actual"""
        if not self.env_file.exists():
            logger.warning("⚠️  Archivo .env no existe")
            return None
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f".env_backup_{timestamp}"
        backup_path = self.env_backup_dir / backup_name
        
        try:
            shutil.copy2(self.env_file, backup_path)
            logger.info(f"✅ Backup creado: {backup_path}")
            return str(backup_path)
        except Exception as e:
            logger.error(f"❌ Error creando backup: {e}")
            return None
    
    def detect_current_database_type(self) -> DatabaseType:
        """Detecta el tipo de base de datos actual"""
        try:
            return settings.DATABASE_TYPE
        except:
            return DatabaseType.POSTGRESQL
    
    def update_env_file(self, target_type: DatabaseType, config: Dict[str, str]):
        """Actualiza el archivo .env con nueva configuración"""
        if not self.env_file.exists():
            logger.error("❌ Archivo .env no existe")
            return False
        
        try:
            # Leer archivo actual
            with open(self.env_file, 'r') as f:
                lines = f.readlines()
            
            # Actualizar líneas
            updated_lines = []
            keys_to_update = set(config.keys())
            keys_found = set()
            
            for line in lines:
                line = line.strip()
                if '=' in line and not line.startswith('#'):
                    key = line.split('=')[0]
                    if key in config:
                        updated_lines.append(f"{key}={config[key]}\n")
                        keys_found.add(key)
                    else:
                        updated_lines.append(line + '\n')
                else:
                    updated_lines.append(line + '\n')
            
            # Agregar keys que no existían
            keys_to_add = keys_to_update - keys_found
            if keys_to_add:
                updated_lines.append(f"\n# Configuración actualizada para {target_type}\n")
                for key in keys_to_add:
                    updated_lines.append(f"{key}={config[key]}\n")
            
            # Escribir archivo actualizado
            with open(self.env_file, 'w') as f:
                f.writelines(updated_lines)
            
            logger.info(f"✅ Archivo .env actualizado para {target_type}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error actualizando .env: {e}")
            return False
    
    def generate_postgresql_config(self) -> Dict[str, str]:
        """Genera configuración para PostgreSQL"""
        config = {
            "DATABASE_TYPE": "postgresql",
            "DATABASE_URL": "postgresql://staging_user:staging_pass@localhost:5432/staging_db",
            # Comentar configuraciones de Supabase
            "# SUPABASE_URL": "",
            "# SUPABASE_ANON_KEY": "",
            "# SUPABASE_SERVICE_ROLE_KEY": "",
        }
        
        logger.info("📝 Configuración PostgreSQL generada")
        logger.info("💡 Recuerda actualizar DATABASE_URL con tus credenciales")
        
        return config
    
    def generate_supabase_config(self) -> Dict[str, str]:
        """Genera configuración para Supabase"""
        config = {
            "DATABASE_TYPE": "supabase",
            "DATABASE_URL": "postgresql://postgres:[YOUR-PASSWORD]@db.[PROJECT-REF].supabase.co:5432/postgres",
            "SUPABASE_URL": "https://[PROJECT-REF].supabase.co",
            "SUPABASE_ANON_KEY": "your-anon-key-here",
            "SUPABASE_SERVICE_ROLE_KEY": "your-service-role-key-here",
            "SUPABASE_JWT_SECRET": "your-jwt-secret-here"
        }
        
        logger.info("📝 Configuración Supabase generada")
        logger.info("💡 Obtén los valores reales desde https://app.supabase.com")
        logger.info("   1. Ve a Settings > Database para DATABASE_URL")
        logger.info("   2. Ve a Settings > API para las keys")
        
        return config
    
    def test_database_connection(self, database_url: str, db_type: DatabaseType) -> bool:
        """Prueba conexión a la base de datos"""
        try:
            logger.info(f"🔌 Probando conexión a {db_type}...")
            
            db_config = DatabaseConfig(
                DATABASE_URL=database_url,
                DATABASE_TYPE=db_type
            )
            db_manager = DatabaseManager(db_config)
            
            connection_info = db_manager.test_connection()
            
            if connection_info["status"] == "connected":
                logger.info("✅ Conexión exitosa")
                logger.info(f"   Usuario: {connection_info.get('user', 'N/A')}")
                logger.info(f"   Base de datos: {connection_info.get('database', 'N/A')}")
                return True
            else:
                logger.error(f"❌ Error en conexión: {connection_info.get('error', 'Unknown')}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error probando conexión: {e}")
            return False
    
    def migrate_data(self, source_config: Dict, target_config: Dict) -> bool:
        """Migra datos entre bases de datos (implementación básica)"""
        logger.info("🔄 Iniciando migración de datos...")
        logger.warning("⚠️  Migración automática no implementada completamente")
        logger.info("💡 Para migrar datos:")
        logger.info("   1. Usa pg_dump para exportar desde la fuente")
        logger.info("   2. Usa pg_restore para importar al destino")
        logger.info("   3. O usa herramientas como DBeaver para copiar datos")
        
        # TODO: Implementar migración automática real
        return True
    
    def switch_to_postgresql(self, migrate_data: bool = False) -> bool:
        """Cambia configuración a PostgreSQL"""
        logger.info("🐘 Cambiando a PostgreSQL...")
        
        current_type = self.detect_current_database_type()
        if current_type == DatabaseType.POSTGRESQL:
            logger.info("✅ Ya estás usando PostgreSQL")
            return True
        
        # Backup del .env actual
        backup_path = self.backup_current_env()
        if not backup_path:
            logger.warning("⚠️  No se pudo crear backup")
        
        # Generar nueva configuración
        new_config = self.generate_postgresql_config()
        
        # Migrar datos si se solicita
        if migrate_data:
            # Aquí implementarías la migración real
            self.migrate_data({}, {})
        
        # Actualizar .env
        success = self.update_env_file(DatabaseType.POSTGRESQL, new_config)
        
        if success:
            logger.info("✅ Cambio a PostgreSQL completado")
            logger.info("📋 Próximos pasos:")
            logger.info("   1. Actualiza DATABASE_URL en .env con tus credenciales")
            logger.info("   2. Asegúrate de que PostgreSQL esté ejecutándose")
            logger.info("   3. Ejecuta: python scripts/setup/init_database.py")
            logger.info("   4. Ejecuta: make setup-schemas")
        
        return success
    
    def switch_to_supabase(self, migrate_data: bool = False) -> bool:
        """Cambia configuración a Supabase"""
        logger.info("🌐 Cambiando a Supabase...")
        
        current_type = self.detect_current_database_type()
        if current_type == DatabaseType.SUPABASE:
            logger.info("✅ Ya estás usando Supabase")
            return True
        
        # Backup del .env actual
        backup_path = self.backup_current_env()
        if not backup_path:
            logger.warning("⚠️  No se pudo crear backup")
        
        # Generar nueva configuración
        new_config = self.generate_supabase_config()
        
        # Migrar datos si se solicita
        if migrate_data:
            self.migrate_data({}, {})
        
        # Actualizar .env
        success = self.update_env_file(DatabaseType.SUPABASE, new_config)
        
        if success:
            logger.info("✅ Cambio a Supabase completado")
            logger.info("📋 Próximos pasos:")
            logger.info("   1. Crea un proyecto en https://app.supabase.com")
            logger.info("   2. Actualiza las variables en .env con valores reales")
            logger.info("   3. Ejecuta: python scripts/setup/supabase_setup_guide.py")
            logger.info("   4. Ejecuta: make setup-schemas")
        
        return success
    
    def show_current_status(self):
        """Muestra estado actual de la configuración"""
        logger.info("📊 Estado Actual de la Base de Datos")
        logger.info("=" * 40)
        
        try:
            current_type = self.detect_current_database_type()
            logger.info(f"🎯 Tipo actual: {current_type}")
            
            # Mostrar configuración relevante
            if current_type == DatabaseType.SUPABASE:
                logger.info(f"🌐 URL Supabase: {settings.SUPABASE_URL}")
                logger.info(f"🔑 Anon Key: {'✅ Configurada' if settings.SUPABASE_ANON_KEY else '❌ Faltante'}")
                logger.info(f"🔐 Service Key: {'✅ Configurada' if settings.SUPABASE_SERVICE_ROLE_KEY else '❌ Faltante'}")
            else:
                logger.info(f"🐘 Database URL: {settings.DATABASE_URL}")
            
            # Probar conexión
            try:
                db_config = DatabaseConfig()
                db_manager = DatabaseManager(db_config)
                connection_info = db_manager.test_connection()
                
                if connection_info["status"] == "connected":
                    logger.info("✅ Conexión: Exitosa")
                    logger.info(f"   Usuario: {connection_info.get('user', 'N/A')}")
                    logger.info(f"   Base de datos: {connection_info.get('database', 'N/A')}")
                else:
                    logger.error("❌ Conexión: Falló")
                    
            except Exception as e:
                logger.error(f"❌ Error probando conexión: {e}")
                
        except Exception as e:
            logger.error(f"❌ Error obteniendo estado: {e}")
    
    def list_backups(self):
        """Lista backups disponibles del archivo .env"""
        logger.info("📂 Backups Disponibles:")
        
        backups = list(self.env_backup_dir.glob(".env_backup_*"))
        
        if not backups:
            logger.info("   No hay backups disponibles")
            return
        
        backups.sort(reverse=True)  # Más recientes primero
        
        for i, backup in enumerate(backups[:10]):  # Mostrar últimos 10
            stat = backup.stat()
            size = stat.st_size
            mtime = datetime.fromtimestamp(stat.st_mtime)
            logger.info(f"   {i+1}. {backup.name} ({size} bytes, {mtime.strftime('%Y-%m-%d %H:%M')})")
    
    def restore_backup(self, backup_name: str) -> bool:
        """Restaura un backup del archivo .env"""
        backup_path = self.env_backup_dir / backup_name
        
        if not backup_path.exists():
            logger.error(f"❌ Backup no encontrado: {backup_name}")
            return False
        
        try:
            # Crear backup del .env actual antes de restaurar
            current_backup = self.backup_current_env()
            
            # Restaurar backup
            shutil.copy2(backup_path, self.env_file)
            logger.info(f"✅ Backup restaurado: {backup_name}")
            
            if current_backup:
                logger.info(f"💾 .env anterior guardado en: {current_backup}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error restaurando backup: {e}")
            return False

def main():
    """Función principal con argumentos de línea de comandos"""
    parser = argparse.ArgumentParser(
        description="Herramienta para cambiar entre PostgreSQL y Supabase"
    )
    parser.add_argument(
        "action",
        choices=["status", "to-postgresql", "to-supabase", "list-backups", "restore"],
        help="Acción a realizar"
    )
    parser.add_argument(
        "--migrate-data",
        action="store_true",
        help="Migrar datos al cambiar de base de datos"
    )
    parser.add_argument(
        "--backup-name",
        help="Nombre del backup a restaurar (para action=restore)"
    )
    
    args = parser.parse_args()
    
    switcher = DatabaseSwitcher()
    
    try:
        if args.action == "status":
            switcher.show_current_status()
            
        elif args.action == "to-postgresql":
            success = switcher.switch_to_postgresql(args.migrate_data)
            sys.exit(0 if success else 1)
            
        elif args.action == "to-supabase":
            success = switcher.switch_to_supabase(args.migrate_data)
            sys.exit(0 if success else 1)
            
        elif args.action == "list-backups":
            switcher.list_backups()
            
        elif args.action == "restore":
            if not args.backup_name:
                logger.error("❌ --backup-name es requerido para restore")
                sys.exit(1)
            success = switcher.restore_backup(args.backup_name)
            sys.exit(0 if success else 1)
            
    except KeyboardInterrupt:
        logger.info("\n⏹️  Operación cancelada")
        sys.exit(1)
    except Exception as e:
        logger.error(f"\n❌ Error inesperado: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()