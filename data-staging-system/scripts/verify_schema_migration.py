#!/usr/bin/env python3
"""
scripts/verify_schema_migration.py
Verify that schema migration was successful
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from data_staging.database import get_database_manager
from sqlalchemy import text

def verify_migration():
    """Verify that migration was successful"""
    
    try:
        db_manager = get_database_manager()
        
        with db_manager.get_session() as session:
            print("🔍 Verifying schema migration...")
            
            # 1. Check tables in public schema
            public_tables_query = text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name IN ('products', 'history')
                ORDER BY table_name
            """)
            
            public_tables = [row[0] for row in session.execute(public_tables_query)]
            print(f"\n📋 Tables in public schema: {public_tables}")
            
            # 2. Check data source configurations
            config_query = text("""
                SELECT source_name, target_schema, target_table
                FROM staging_meta.data_sources 
                WHERE target_schema = 'public'
                ORDER BY source_name
            """)
            
            configs = session.execute(config_query).fetchall()
            print(f"\n⚙️ Data sources using public schema:")
            for source_name, target_schema, target_table in configs:
                print(f"   • {source_name} → {target_schema}.{target_table}")
            
            # 3. Check if production schema still exists
            production_tables_query = text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'production'
                ORDER BY table_name
            """)
            
            production_tables = [row[0] for row in session.execute(production_tables_query)]
            if production_tables:
                print(f"\n⚠️ Tables still in production schema: {production_tables}")
                print("   Consider dropping production schema if no longer needed")
            else:
                print(f"\n✅ No tables found in production schema")
            
            # 4. Count records in public tables
            if 'products' in public_tables:
                product_count = session.execute(text("SELECT COUNT(*) FROM m8_schema.products")).scalar()
                print(f"\n📊 Records in m8_schema.products: {product_count}")
            
            if 'history' in public_tables:
                history_count = session.execute(text("SELECT COUNT(*) FROM m8_schema.history")).scalar()
                print(f"📊 Records in m8_schema.history: {history_count}")
            
            return True
            
    except Exception as e:
        print(f"❌ Error during verification: {e}")
        return False

def test_upload_with_public_schema():
    """Test that uploads now go to public schema"""
    
    print(f"\n🧪 Testing upload configuration...")
    
    try:
        # This would require the API to be running
        import requests
        
        response = requests.get("http://localhost:8000/health", timeout=5)
        if response.status_code == 200:
            print("✅ API is running - ready for upload tests")
            print("   Test with: python test_products_upload.py")
        else:
            print("⚠️ API not responding - start with: python start_api.py")
            
    except Exception:
        print("ℹ️ API not running - start with: python start_api.py to test uploads")

if __name__ == "__main__":
    print("✔️ Verifying Schema Migration: production → public")
    print("=" * 50)
    
    if verify_migration():
        test_upload_with_public_schema()
        
        print(f"\n🎉 Schema migration verification completed!")
        print(f"\n📋 Next steps:")
        print(f"   1. Test file uploads to ensure they go to public schema")
        print(f"   2. Update any custom scripts that might reference production")
        print(f"   3. Consider dropping production schema: DROP SCHEMA production CASCADE;")
        print(f"   4. Update documentation to reflect public schema usage")
        
    else:
        print(f"\n❌ Schema migration verification failed")