import logging
import os
from pathlib import Path
from sqlalchemy import text
from data_staging.database import get_database_manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def apply_migration():
    try:
        # Get database manager
        db_manager = get_database_manager()
        
        # Read migration file
        migration_path = Path("migrations/create_job_queue.sql")
        if not migration_path.exists():
            logger.error(f"Migration file not found: {migration_path}")
            return
            
        logger.info(f"Reading migration from {migration_path}")
        with open(migration_path, "r", encoding="utf-8") as f:
            sql_content = f.read()
            
        # Execute migration
        logger.info("Connecting to database...")
        with db_manager.get_session() as session:
            logger.info("Executing migration...")
            # Split by statement if needed, or execute as one block if supported
            # sqlalchemy text() might handle multiple statements if backend supports it
            # But better to just execute.
            session.execute(text(sql_content))
            session.commit()
            logger.info("Migration applied successfully!")
            
    except Exception as e:
        logger.error(f"Error applying migration: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    apply_migration()
