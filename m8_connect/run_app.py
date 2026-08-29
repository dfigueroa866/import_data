#!/usr/bin/env python3
"""
Main application runner for M8 Connect
"""

import sys
import os
import io

# Force UTF-8 encoding for stdout/stderr to handle emojis on Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

import logging
from pathlib import Path
from datetime import datetime

# Add src to path to ensure we use the correct data_staging package
sys.path.insert(0, str(Path(__file__).parent / "src"))

from logging.handlers import RotatingFileHandler

class SafeStreamHandler(logging.StreamHandler):
    """A stream handler that safely encodes special characters."""
    def emit(self, record):
        try:
            msg = self.format(record)
            stream = self.stream
            # Write with replacement for encoding errors
            stream.write(msg.encode('utf-8', 'replace').decode(sys.stdout.encoding or 'utf-8', 'replace') + self.terminator)
            self.flush()
        except Exception:
            self.handleError(record)

def setup_logging():
    """Setup logging configuration with robust file handling and separation of concerns."""
    # 1. Define and Create Log Directory
    log_dir = Path(os.getcwd()) / "logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        print(f"📂 Log directory verified at: {log_dir}")
    except Exception as e:
        print(f"❌ Failed to create log directory {log_dir}: {e}")
        return # Fallback to console only if filesystem fails

    # 2. Define Log Files
    app_log = log_dir / "application.log"
    sql_log = log_dir / "sql.log"
    error_log = log_dir / "errors.log"

    # 3. Create Formatters
    standard_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # 4. Create Handlers with Rotation (5MB limit, 3 backups)
    # Application Handler (INFO+)
    app_handler = RotatingFileHandler(app_log, maxBytes=5_000_000, backupCount=3, encoding='utf-8')
    app_handler.setLevel(logging.INFO)
    app_handler.setFormatter(standard_formatter)

    # SQL Handler (INFO+)
    sql_handler = RotatingFileHandler(sql_log, maxBytes=5_000_000, backupCount=3, encoding='utf-8')
    sql_handler.setLevel(logging.INFO) 
    sql_handler.setFormatter(standard_formatter)

    # Error Handler (ERROR+)
    error_handler = RotatingFileHandler(error_log, maxBytes=5_000_000, backupCount=3, encoding='utf-8')
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(standard_formatter)

    # Console Handler (Safe)
    console_handler = SafeStreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(standard_formatter)

    # 5. Configure Root Logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers = [] # Clear existing
    root_logger.addHandler(app_handler)
    root_logger.addHandler(error_handler)
    root_logger.addHandler(console_handler)

    # 6. Configure Specialized Loggers
    
    # SQLAlchemy - Send to sql.log AND console (optional, maybe too noisy for console)
    # Reducing console noise: SQL logs only to file
    sql_logger = logging.getLogger("sqlalchemy.engine")
    sql_logger.setLevel(logging.INFO) 
    sql_logger.handlers = [sql_handler] # Only to file to keep console clean
    sql_logger.propagate = False # Do not bubble up to root (avoids duplication in app.log)

    # Uvicorn - Ensure it uses our handlers
    uvicorn_logger = logging.getLogger("uvicorn")
    uvicorn_logger.handlers = [app_handler, error_handler, console_handler]
    uvicorn_logger.propagate = False
    
    uvicorn_error = logging.getLogger("uvicorn.error")
    uvicorn_error.handlers = [app_handler, error_handler, console_handler]
    uvicorn_error.propagate = False
    
    uvicorn_access = logging.getLogger("uvicorn.access")
    uvicorn_access.handlers = [app_handler, console_handler]
    uvicorn_access.propagate = False
    
    # Silence watchfiles logger
    logging.getLogger("watchfiles").setLevel(logging.ERROR)
    logging.getLogger("watchfiles.main").setLevel(logging.ERROR)
    logging.getLogger("watchfiles.watcher").setLevel(logging.ERROR)

    # Test write immediately
    try:
        logging.info("📝 Logging system initialized. Logs separated into logs/ directory.")
    except Exception:
        pass

def check_dependencies():
    """Verify optional packages required by auth and upload routers."""
    import sys

    missing = []
    checks = [
        ("bcrypt", "bcrypt"),
        ("jose", "python-jose[cryptography]"),
        ("dateutil", "python-dateutil"),
    ]
    for module, package in checks:
        try:
            __import__(module)
        except ImportError:
            missing.append(package)

    if missing:
        print("❌ Faltan dependencias del backend:")
        for pkg in missing:
            print(f"   - {pkg}")
        print(f"\n   Python en uso: {sys.executable}")
        print("\n💡 Instala con el MISMO Python (no uses solo 'pip' si apunta a otro venv):")
        print(f'   python -m pip install {" ".join(missing)}')
        print("   # o: python -m pip install -r requirements.txt")
        return False

    print("✅ Dependencias de auth y upload verificadas")
    return True


def check_port_available(port: int = 8000) -> bool:
    """Return True if the API port can be bound."""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("0.0.0.0", port))
            return True
        except OSError:
            print(f"❌ El puerto {port} ya está en uso")
            print("💡 Cierra el proceso anterior o usa otro puerto:")
            print(f"   netstat -ano | findstr :{port}")
            print("   taskkill /PID <pid> /F")
            return False


def check_environment():
    """Check if environment is properly configured."""
    env_file = Path(".env")
    if not env_file.exists():
        print("❌ .env file not found")
        print("💡 Copy .env.example to .env and configure your database")
        return False
    
    # Check if DATABASE_URL is configured
    try:
        from data_staging.config import settings
        if not settings.DATABASE_URL or "your-password" in str(settings.DATABASE_URL).lower():
            print("❌ DATABASE_URL not properly configured in .env")
            print("💡 Please update DATABASE_URL with your actual database credentials")
            return False
        
        print("✅ Environment configuration looks good")
        print(f"   Database type: {settings.DATABASE_TYPE or 'auto-detected'}")
        print(f"   Upload path: {settings.UPLOAD_PATH}")
        return True
        
    except Exception as e:
        print(f"❌ Configuration error: {e}")
        import traceback
        traceback.print_exc()
        print("💡 Check your .env file format and values")
        return False

def test_database():
    """Test database connection."""
    try:
        from data_staging.database import get_database_manager
        
        print("🔍 Testing database connection...")
        db_manager = get_database_manager()
        connection_info = db_manager.test_connection()
        
        if connection_info["status"] == "connected":
            print(f"✅ Database connected: {connection_info['database']}")
            print(f"   Type: {connection_info['database_type']}")
            if 'schemas' in connection_info:
                print(f"   Schemas: {connection_info['schemas']}")
            return True

        err = connection_info.get("error") or connection_info.get("message") or "Unknown error"
        print(f"❌ Database connection failed: {err}")

        err_lower = str(err).lower()
        if "connection refused" in err_lower or "10061" in err_lower:
            from data_staging.config import settings
            db_url = str(settings.DATABASE_URL or "")
            host_port = db_url.split("@")[-1] if "@" in db_url else db_url
            print("\n💡 PostgreSQL no está accesible en", host_port)
            print("   1. Mantén abierto el túnel SSH:")
            print("      ssh -i m8-steiner-key.pem -L 5432:172.18.0.3:5432 ubuntu@100.59.255.31")
            print("   2. O levanta Postgres local:")
            print("      docker compose -f docker/docker-compose.local.yml up -d")
            print("   3. Prueba: python scripts/test_postgres_connection.py")
            print("   4. Vuelve a ejecutar: python run_app.py")
        elif "password authentication failed" in err_lower:
            from data_staging.config import settings
            db_url = str(settings.DATABASE_URL or "")
            host_port = db_url.split("@")[-1] if "@" in db_url else db_url
            print("\n💡 Autenticación fallida en", host_port)
            print("   1. Verifica usuario y contraseña en DATABASE_URL (.env)")
            print("   2. Confirma que el túnel apunta al Postgres correcto (no a otra instancia local)")
            print("   3. Prueba: python scripts/test_postgres_connection.py")
        return False
            
    except Exception as e:
        print(f"❌ Database test failed: {e}")
        return False

def verify_critical_tables_exist():
    """Verify that critical database tables exist with expected schema."""
    try:
        from data_staging.database import get_database_manager
        from sqlalchemy import text
        
        print("🔍 Verifying database schema...")
        db_manager = get_database_manager()
        
        with db_manager.get_session() as session:
            # Check if staging_meta.data_sources table exists
            result = session.execute(text("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables 
                    WHERE table_schema = 'staging_meta' 
                    AND table_name = 'data_sources'
                )
            """))
            
            table_exists = result.scalar()
            
            if not table_exists:
                print("❌ Critical table 'staging_meta.data_sources' does not exist")
                print("💡 Run database migrations: alembic upgrade head")
                return False
            
            # Check if required columns exist
            result = session.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_schema = 'staging_meta' 
                AND table_name = 'data_sources'
                AND column_name IN ('created_at', 'updated_at')
            """))
            
            existing_columns = [row[0] for row in result]
            required_columns = ['created_at', 'updated_at']
            missing_columns = [col for col in required_columns if col not in existing_columns]
            
            if missing_columns:
                print(f"❌ Missing required columns in data_sources table: {missing_columns}")
                print("💡 Run database migrations: alembic upgrade head")
                return False
            
            print("✅ Database schema verification passed")
            
            # Silence SQLAlchemy logs to prevent console flooding
            logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
            
            return True
            
    except Exception as e:
        print(f"❌ Schema verification failed: {e}")
        print("💡 This usually means:")
        print("   1. Database connection issues")
        print("   2. Missing database tables")
        print("   3. Schema mismatch")
        print("💡 Try running: alembic upgrade head")
        return False

def main():
    """Main application entry point."""
    setup_logging()
    
    print("🚀 Starting M8 Connect")
    print("=" * 50)
    
    # Check environment
    if not check_environment():
        return 1

    if not check_dependencies():
        return 1
    
    # Test database
    if not test_database():
        print("\n💡 Database connection tips:")
        print("   1. Make sure your database is running")
        print("   2. Check DATABASE_URL in .env file")
        print("   3. For Supabase, get credentials from https://app.supabase.com")
        print("   4. Run: python3 check_supabase_connection.py")
        print("   5. Try restarting the application")
        return 1
    
    # Verify database schema
    if not verify_critical_tables_exist():
        print("\n❌ Database schema verification failed")
        print("💡 To fix this, run the following commands:")
        print("   1. alembic upgrade head")
        print("   2. python3 run_app.py")
        return 1
    
    # Start the API server
    try:
        if not check_port_available(8000):
            return 1

        print("\n🌐 Starting API server...")
        print("📍 API will be available at: http://localhost:8000")
        print("📚 API docs at: http://localhost:8000/docs")
        print("🖥️  UI (login): http://localhost:5173/login  —  cd frontend && npm run dev")
        print("   (Rutas /login en :8000 redirigen a Vite si no hay frontend/dist)")
        print("\nPress CTRL+C to stop\n")
        
        # Run with import string to support reload
        import uvicorn
        
        uvicorn.run(
            "data_staging.api.main:app",
            host="0.0.0.0",
            port=8000,
            reload=False,  # Set to False for production/workers
            reload_excludes=["logs", "data", "*.log", "*.tmp"],
            log_level="info",
            log_config=None
        )
        
    except KeyboardInterrupt:
        print("\n👋 Shutting down gracefully...")
    except Exception as e:
        print(f"❌ Error starting server: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())