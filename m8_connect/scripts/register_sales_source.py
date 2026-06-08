#!/usr/bin/env python3
"""
scripts/register_sales_source.py
Register sales data source with comprehensive validation
"""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from data_staging.database import get_database_manager
from sqlalchemy import text

def register_sales_source():
    """Register sales data source configuration"""
    
    config_file = Path(__file__).parent.parent / "config/sources/sales_data.json"
    
    if not config_file.exists():
        print(f"❌ Configuration file not found: {config_file}")
        return False
    
    with open(config_file, 'r') as f:
        config = json.load(f)
    
    try:
        db_manager = get_database_manager()
        
        with db_manager.get_session() as session:
            # Check if source exists
            check_query = text("""
                SELECT COUNT(*) FROM staging_meta.data_sources 
                WHERE source_name = :source_name
            """)
            
            exists = session.execute(check_query, {"source_name": config["source_name"]}).scalar()
            
            if exists > 0:
                print(f"⚠️ Updating existing sales data source...")
                update_query = text("""
                    UPDATE staging_meta.data_sources 
                    SET 
                        description = :description,
                        connection_config = :connection_config,
                        validation_rules = :validation_rules,
                        transformation_rules = :transformation_rules,
                        target_table = :target_table,
                        target_schema = :target_schema,
                        is_active = :is_active
                    WHERE source_name = :source_name
                """)
                
                session.execute(update_query, {
                    "source_name": config["source_name"],
                    "description": config["description"],
                    "connection_config": json.dumps(config["connection_config"]),
                    "validation_rules": json.dumps(config["validation_rules"]),
                    "transformation_rules": json.dumps(config["transformation_rules"]),
                    "target_table": config["target_table"],
                    "target_schema": config["target_schema"],
                    "is_active": config["is_active"]
                })
            else:
                print(f"➕ Creating new sales data source...")
                insert_query = text("""
                    INSERT INTO staging_meta.data_sources 
                    (source_name, source_type, description, connection_config, 
                     validation_rules, transformation_rules, target_table, target_schema, is_active)
                    VALUES 
                    (:source_name, :source_type, :description, :connection_config,
                     :validation_rules, :transformation_rules, :target_table, :target_schema, :is_active)
                """)
                
                session.execute(insert_query, {
                    "source_name": config["source_name"],
                    "source_type": config["source_type"],
                    "description": config["description"],
                    "connection_config": json.dumps(config["connection_config"]),
                    "validation_rules": json.dumps(config["validation_rules"]),
                    "transformation_rules": json.dumps(config["transformation_rules"]),
                    "target_table": config["target_table"],
                    "target_schema": config["target_schema"],
                    "is_active": config["is_active"]
                })
            
            session.commit()
            print(f"✅ Sales data source configured successfully!")
            return True
            
    except Exception as e:
        print(f"❌ Error registering sales data source: {e}")
        return False

if __name__ == "__main__":
    print("📝 Registering Sales Data Source with Referential Integrity")
    print("=" * 60)
    
    success = register_sales_source()
    
    if success:
        print("\n🎉 Sales data source ready!")
        print("\n📋 Validation features enabled:")
        print("   • Referential integrity checks (products, locations, customers)")
        print("   • Business rule validation (total amount calculations)")
        print("   • Conditional validation (discount consistency)")
        print("   • Lookup validation (sale types, payment methods)")
        print("   • Range and pattern validation")
        print("\n📄 Next: Create sample sales data and test upload")
    else:
        print("\n❌ Failed to register sales data source")