#!/usr/bin/env python3
"""
Database status check script
"""
import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'src'))

def check_database_status():
    """Check database connection and status"""
    try:
        # Try to import database module
        try:
            from data_staging.database import get_database_manager
            from sqlalchemy import text
        except ImportError as e:
            print(f'⚠️  Database module not fully configured: {e}')
            return False
        
        # Test database connection
        try:
            db_manager = get_database_manager()
            print('✅ Database manager initialized')
            
            with db_manager.get_session() as session:
                # Test basic connection
                result = session.execute(text('SELECT 1 as test'))
                test_result = result.scalar()
                if test_result == 1:
                    print('✅ Database connection successful')
                
                # Get database version
                try:
                    result = session.execute(text('SELECT version()'))
                    version = result.scalar()
                    if version:
                        db_name = version.split()[0]
                        db_version = version.split()[1] if len(version.split()) > 1 else 'Unknown'
                        print(f'📋 Database: {db_name} {db_version}')
                except Exception:
                    print('📋 Database: Connected (version info not available)')
                
                # Check for schemas
                try:
                    result = session.execute(text("""
                        SELECT schema_name 
                        FROM information_schema.schemata 
                        WHERE schema_name IN ('staging_meta', 'staging_data', 'production')
                        ORDER BY schema_name
                    """))
                    schemas = [row[0] for row in result.fetchall()]
                    if schemas:
                        print(f'📁 Schemas: {", ".join(schemas)}')
                    else:
                        print('📁 Schemas: None configured yet')
                        
                    # Check table counts
                    result = session.execute(text("""
                        SELECT table_schema, COUNT(*) as table_count
                        FROM information_schema.tables 
                        WHERE table_schema IN ('staging_meta', 'staging_data', 'production')
                        GROUP BY table_schema
                    """))
                    table_counts = dict(result.fetchall())
                    
                    for schema in ['staging_meta', 'staging_data', 'production']:
                        count = table_counts.get(schema, 0)
                        print(f'📊 Tables in {schema}: {count}')
                        
                except Exception as e:
                    print(f'⚠️  Could not check schemas/tables: {e}')
                
            return True
            
        except Exception as e:
            print(f'❌ Database connection failed: {e}')
            print('💡 Check your .env file and database configuration')
            return False
            
    except Exception as e:
        print(f'❌ Database check failed: {e}')
        return False

if __name__ == '__main__':
    success = check_database_status()
    sys.exit(0 if success else 1)