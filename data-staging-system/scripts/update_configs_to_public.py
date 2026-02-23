#!/usr/bin/env python3
"""
scripts/update_configs_to_public.py
Update all data source configurations to use public schema
"""

import sys
import json
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from data_staging.database import get_database_manager
from sqlalchemy import text

def update_configurations_to_public():
    """Update all data source configurations to use public schema"""
    
    try:
        db_manager = get_database_manager()
        
        with db_manager.get_session() as session:
            # Get all data sources that use production schema
            query = text("""
                SELECT source_id, source_name, connection_config, validation_rules, transformation_rules
                FROM staging_meta.data_sources 
                WHERE target_schema = 'production' OR 
                      connection_config::text LIKE '%production%' OR
                      validation_rules::text LIKE '%production%' OR
                      transformation_rules::text LIKE '%production%'
            """)
            
            sources = session.execute(query).fetchall()
            
            if not sources:
                print("ℹ️ No data sources found using production schema")
                return True
            
            print(f"🔄 Updating {len(sources)} data source configurations...")
            
            for source in sources:
                source_id, source_name, connection_config, validation_rules, transformation_rules = source
                
                print(f"   Updating: {source_name}")
                
                # Update configuration JSONs to replace 'production' with 'public'
                updated_connection = json.dumps(
                    json.loads(connection_config or '{}')
                ).replace('production', 'public') if connection_config else None
                
                updated_validation = json.dumps(
                    json.loads(validation_rules or '{}')
                ).replace('production', 'public') if validation_rules else None
                
                updated_transformation = json.dumps(
                    json.loads(transformation_rules or '{}')
                ).replace('production', 'public') if transformation_rules else None
                
                # Update the database record
                update_query = text("""
                    UPDATE staging_meta.data_sources 
                    SET 
                        target_schema = 'public',
                        connection_config = :connection_config,
                        validation_rules = :validation_rules,
                        transformation_rules = :transformation_rules
                    WHERE source_id = :source_id
                """)
                
                session.execute(update_query, {
                    "source_id": source_id,
                    "connection_config": updated_connection,
                    "validation_rules": updated_validation,
                    "transformation_rules": updated_transformation
                })
            
            session.commit()
            print(f"✅ Updated {len(sources)} data source configurations")
            
            # Verify updates
            verify_query = text("""
                SELECT source_name, target_schema 
                FROM staging_meta.data_sources 
                WHERE target_schema = 'public'
                ORDER BY source_name
            """)
            
            updated_sources = session.execute(verify_query).fetchall()
            print(f"\n📋 Data sources now using public schema:")
            for source_name, target_schema in updated_sources:
                print(f"   • {source_name} → {target_schema}")
                
            return True
            
    except Exception as e:
        print(f"❌ Error updating configurations: {e}")
        return False

def update_config_files():
    """Update configuration files in config/sources/ directory"""
    
    config_dir = Path(__file__).parent.parent / "config" / "sources"
    
    if not config_dir.exists():
        print("ℹ️ No config/sources directory found")
        return
    
    config_files = list(config_dir.glob("*.json"))
    
    if not config_files:
        print("ℹ️ No configuration files found")
        return
    
    print(f"\n🔄 Updating {len(config_files)} configuration files...")
    
    for config_file in config_files:
        try:
            with open(config_file, 'r') as f:
                config = json.load(f)
            
            # Update schema references
            updated = False
            
            if config.get('target_schema') == 'production':
                config['target_schema'] = 'm8_schema'
                updated = True
            
            if config.get('production_schema') == 'production':
                config['production_schema'] = 'm8_schema'
                updated = True
            
            # Update any references in nested configurations
            def update_nested_refs(obj):
                if isinstance(obj, dict):
                    for key, value in obj.items():
                        if isinstance(value, str) and 'production.' in value:
                            obj[key] = value.replace('production.', 'm8_schema.')
                            return True
                        elif isinstance(value, (dict, list)):
                            if update_nested_refs(value):
                                return True
                elif isinstance(obj, list):
                    for item in obj:
                        if update_nested_refs(item):
                            return True
                return False
            
            if update_nested_refs(config):
                updated = True
            
            if updated:
                with open(config_file, 'w') as f:
                    json.dump(config, f, indent=2)
                print(f"   ✅ Updated: {config_file.name}")
            else:
                print(f"   ⏭️ No changes: {config_file.name}")
                
        except Exception as e:
            print(f"   ❌ Error updating {config_file.name}: {e}")

if __name__ == "__main__":
    print("🔄 Updating Data Source Configurations: production → public")
    print("=" * 60)
    
    # Update database configurations
    db_success = update_configurations_to_public()
    
    # Update configuration files
    update_config_files()
    
    if db_success:
        print("\n🎉 Schema migration configuration update completed!")
        print("\n📋 Next steps:")
        print("   1. Test file uploads to verify they go to public schema")
        print("   2. Update any custom scripts that reference 'production' schema")
        print("   3. Consider dropping production schema if no longer needed")
    else:
        print("\n❌ Schema migration configuration update failed")