#!/usr/bin/env python3
"""
Register Data Source Script
File: scripts/register_data_source.py

This script registers Data Source Configuration files in the database,
making them available for the data staging system to use.
"""

import sys
import json
import argparse
from pathlib import Path
from typing import Dict, Any, List, Optional
import logging

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

try:
    from data_staging.database import get_database_manager
    from sqlalchemy import text
    DATABASE_AVAILABLE = True
except ImportError as e:
    print(f"❌ Database not available: {e}")
    print("   Make sure dependencies are installed: pip install -r requirements.txt")
    DATABASE_AVAILABLE = False
    sys.exit(1)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DataSourceRegistrar:
    """Handle registration of data source configurations"""
    
    def __init__(self):
        if not DATABASE_AVAILABLE:
            raise ImportError("Database components not available")
        
        self.db_manager = get_database_manager()
    
    def register_config(
        self, 
        config_file: str, 
        overwrite: bool = False,
        validate_tables: bool = True
    ) -> bool:
        """Register a data source configuration from file"""
        
        config_path = Path(config_file)
        
        if not config_path.exists():
            logger.error(f"Configuration file not found: {config_file}")
            return False
        
        try:
            # Load configuration
            with open(config_path, 'r') as f:
                config = json.load(f)
            
            # Validate configuration
            if not self._validate_config(config):
                logger.error(f"Configuration validation failed: {config_file}")
                return False
            
            # Check if tables exist (if requested)
            if validate_tables:
                if not self._validate_target_tables(config):
                    logger.warning("Target tables don't exist - continuing anyway")
            
            # Register in database
            success = self._insert_or_update_config(config, overwrite)
            
            if success:
                logger.info(f"✅ Successfully registered: {config['source_name']}")
                return True
            else:
                logger.error(f"❌ Failed to register: {config['source_name']}")
                return False
                
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in {config_file}: {e}")
            return False
        except Exception as e:
            logger.error(f"Error registering {config_file}: {e}")
            return False
    
    def register_directory(
        self, 
        directory: str, 
        pattern: str = "*.json",
        overwrite: bool = False,
        validate_tables: bool = False
    ) -> Dict[str, bool]:
        """Register all configuration files in a directory"""
        
        dir_path = Path(directory)
        
        if not dir_path.exists():
            logger.error(f"Directory not found: {directory}")
            return {}
        
        config_files = list(dir_path.glob(pattern))
        
        if not config_files:
            logger.warning(f"No configuration files found in {directory} matching {pattern}")
            return {}
        
        results = {}
        
        logger.info(f"Found {len(config_files)} configuration files")
        
        for config_file in config_files:
            logger.info(f"Processing: {config_file.name}")
            success = self.register_config(
                str(config_file), 
                overwrite=overwrite,
                validate_tables=validate_tables
            )
            results[str(config_file)] = success
        
        return results
    
    def list_registered_sources(self, active_only: bool = True) -> List[Dict[str, Any]]:
        """List all registered data sources"""
        
        try:
            with self.db_manager.get_session() as session:
                where_clause = "WHERE is_active = true" if active_only else ""
                
                query = text(f"""
                    SELECT 
                        source_id,
                        source_name,
                        source_type,
                        description,
                        target_table,
                        target_schema,
                        is_active,
                        created_at
                    FROM staging_meta.data_sources
                    {where_clause}
                    ORDER BY source_name
                """)
                
                result = session.execute(query)
                
                sources = []
                for row in result:
                    sources.append({
                        "source_id": row.source_id,
                        "source_name": row.source_name,
                        "source_type": row.source_type,
                        "description": row.description,
                        "target_table": row.target_table,
                        "target_schema": row.target_schema,
                        "is_active": row.is_active,
                        "created_at": row.created_at.isoformat() if row.created_at else None
                    })
                
                return sources
                
        except Exception as e:
            logger.error(f"Error listing data sources: {e}")
            return []
    
    def unregister_source(self, source_name: str, hard_delete: bool = False) -> bool:
        """Unregister (deactivate or delete) a data source"""
        
        try:
            with self.db_manager.get_session() as session:
                if hard_delete:
                    # Completely remove the source
                    query = text("""
                        DELETE FROM staging_meta.data_sources 
                        WHERE source_name = :source_name
                    """)
                    action = "deleted"
                else:
                    # Just deactivate
                    query = text("""
                        UPDATE staging_meta.data_sources 
                        SET is_active = false 
                        WHERE source_name = :source_name
                    """)
                    action = "deactivated"
                
                result = session.execute(query, {"source_name": source_name})
                session.commit()
                
                if result.rowcount > 0:
                    logger.info(f"✅ Data source '{source_name}' {action}")
                    return True
                else:
                    logger.warning(f"Data source '{source_name}' not found")
                    return False
                    
        except Exception as e:
            logger.error(f"Error unregistering {source_name}: {e}")
            return False
    
    def update_source_status(self, source_name: str, active: bool) -> bool:
        """Update the active status of a data source"""
        
        try:
            with self.db_manager.get_session() as session:
                query = text("""
                    UPDATE staging_meta.data_sources 
                    SET is_active = :active 
                    WHERE source_name = :source_name
                """)
                
                result = session.execute(query, {
                    "source_name": source_name,
                    "active": active
                })
                session.commit()
                
                if result.rowcount > 0:
                    status = "activated" if active else "deactivated"
                    logger.info(f"✅ Data source '{source_name}' {status}")
                    return True
                else:
                    logger.warning(f"Data source '{source_name}' not found")
                    return False
                    
        except Exception as e:
            logger.error(f"Error updating {source_name}: {e}")
            return False
    
    def get_source_details(self, source_name: str) -> Optional[Dict[str, Any]]:
        """Get detailed information about a data source"""
        
        try:
            with self.db_manager.get_session() as session:
                query = text("""
                    SELECT 
                        source_id,
                        source_name,
                        source_type,
                        description,
                        connection_config,
                        validation_rules,
                        transformation_rules,
                        target_table,
                        target_schema,
                        is_active,
                        max_retries,
                        timeout_seconds,
                        batch_size,
                        tags,
                        owner,
                        created_at,
                        updated_at
                    FROM staging_meta.data_sources
                    WHERE source_name = :source_name
                """)
                
                result = session.execute(query, {"source_name": source_name})
                row = result.fetchone()
                
                if not row:
                    return None
                
                return {
                    "source_id": row.source_id,
                    "source_name": row.source_name,
                    "source_type": row.source_type,
                    "description": row.description,
                    "connection_config": json.loads(row.connection_config) if row.connection_config else {},
                    "validation_rules": json.loads(row.validation_rules) if row.validation_rules else {},
                    "transformation_rules": json.loads(row.transformation_rules) if row.transformation_rules else [],
                    "target_table": row.target_table,
                    "target_schema": row.target_schema,
                    "is_active": row.is_active,
                    "max_retries": row.max_retries,
                    "timeout_seconds": row.timeout_seconds,
                    "batch_size": row.batch_size,
                    "tags": row.tags,
                    "owner": row.owner,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "updated_at": row.updated_at.isoformat() if row.updated_at else None
                }
                
        except Exception as e:
            logger.error(f"Error getting details for {source_name}: {e}")
            return None
    
    def _validate_config(self, config: Dict[str, Any]) -> bool:
        """Validate configuration structure"""
        
        required_fields = ["source_name", "source_type", "target_table"]
        
        for field in required_fields:
            if field not in config:
                logger.error(f"Missing required field: {field}")
                return False
        
        # Validate source_name format
        source_name = config["source_name"]
        if not source_name or not isinstance(source_name, str):
            logger.error("source_name must be a non-empty string")
            return False
        
        # Validate source_type
        valid_types = ["file", "api", "database", "stream", "ftp"]
        if config["source_type"] not in valid_types:
            logger.error(f"source_type must be one of: {valid_types}")
            return False
        
        # Validate JSON fields if present
        json_fields = ["validation_rules", "transformation_rules", "connection_config"]
        for field in json_fields:
            if field in config:
                try:
                    json.dumps(config[field])
                except (TypeError, ValueError) as e:
                    logger.error(f"Invalid JSON in {field}: {e}")
                    return False
        
        return True
    
    def _validate_target_tables(self, config: Dict[str, Any]) -> bool:
        """Validate that target tables exist"""
        
        try:
            with self.db_manager.get_session() as session:
                # Check staging table
                staging_schema = config.get("target_schema", "staging_data")
                staging_table = config["target_table"]
                
                staging_exists = session.execute(text("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.tables 
                        WHERE table_schema = :schema AND table_name = :table
                    )
                """), {"schema": staging_schema, "table": staging_table}).scalar()
                
                if not staging_exists:
                    logger.warning(f"Staging table {staging_schema}.{staging_table} does not exist")
                    return False
                
                # Check production table if specified
                if "production_table" in config:
                    prod_schema = config.get("production_schema", "public")
                    prod_table = config["production_table"]
                    
                    prod_exists = session.execute(text("""
                        SELECT EXISTS (
                            SELECT 1 FROM information_schema.tables 
                            WHERE table_schema = :schema AND table_name = :table
                        )
                    """), {"schema": prod_schema, "table": prod_table}).scalar()
                    
                    if not prod_exists:
                        logger.warning(f"Production table {prod_schema}.{prod_table} does not exist")
                        return False
                
                return True
                
        except Exception as e:
            logger.error(f"Error validating tables: {e}")
            return False
    
    def _insert_or_update_config(self, config: Dict[str, Any], overwrite: bool) -> bool:
        """Insert or update configuration in database"""
        
        try:
            with self.db_manager.get_session() as session:
                # Check if source already exists
                exists_query = text("""
                    SELECT COUNT(*) FROM staging_meta.data_sources 
                    WHERE source_name = :source_name
                """)
                
                exists = session.execute(exists_query, {
                    "source_name": config["source_name"]
                }).scalar()
                
                if exists > 0 and not overwrite:
                    logger.error(f"Data source '{config['source_name']}' already exists. Use --overwrite to update.")
                    return False
                
                # Prepare data for insertion/update
                data = {
                    "source_name": config["source_name"],
                    "source_type": config["source_type"],
                    "description": config.get("description", ""),
                    "connection_config": json.dumps(config.get("connection_config", {})),
                    "validation_rules": json.dumps(config.get("validation_rules", {})),
                    "transformation_rules": json.dumps(config.get("transformation_rules", [])),
                    "target_table": config["target_table"],
                    "target_schema": config.get("target_schema", "staging_data"),
                    "is_active": config.get("is_active", True),
                    "max_retries": config.get("max_retries", 3),
                    "timeout_seconds": config.get("timeout_seconds", 300),
                    "batch_size": config.get("batch_size", 1000),
                    "tags": config.get("tags", []),
                    "owner": config.get("owner", ""),
                    "schedule_expression": config.get("schedule_expression"),
                    "last_processed_at": None,
                    "next_scheduled_at": None
                }
                
                if exists > 0:
                    # Update existing
                    update_query = text("""
                        UPDATE staging_meta.data_sources 
                        SET 
                            source_type = :source_type,
                            description = :description,
                            connection_config = :connection_config,
                            validation_rules = :validation_rules,
                            transformation_rules = :transformation_rules,
                            target_table = :target_table,
                            target_schema = :target_schema,
                            is_active = :is_active,
                            max_retries = :max_retries,
                            timeout_seconds = :timeout_seconds,
                            batch_size = :batch_size,
                            tags = :tags,
                            owner = :owner,
                            schedule_expression = :schedule_expression,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE source_name = :source_name
                    """)
                    
                    session.execute(update_query, data)
                    logger.info(f"Updated existing data source: {config['source_name']}")
                    
                else:
                    # Insert new
                    insert_query = text("""
                        INSERT INTO staging_meta.data_sources 
                        (source_name, source_type, description, connection_config, 
                         validation_rules, transformation_rules, target_table, target_schema,
                         is_active, max_retries, timeout_seconds, batch_size, tags, owner,
                         schedule_expression, last_processed_at, next_scheduled_at)
                        VALUES 
                        (:source_name, :source_type, :description, :connection_config,
                         :validation_rules, :transformation_rules, :target_table, :target_schema,
                         :is_active, :max_retries, :timeout_seconds, :batch_size, :tags, :owner,
                         :schedule_expression, :last_processed_at, :next_scheduled_at)
                    """)
                    
                    session.execute(insert_query, data)
                    logger.info(f"Registered new data source: {config['source_name']}")
                
                session.commit()
                return True
                
        except Exception as e:
            logger.error(f"Database error: {e}")
            return False

def main():
    """Main CLI function"""
    
    parser = argparse.ArgumentParser(
        description="Register Data Source Configurations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Register a single configuration
  python scripts/register_data_source.py --config config/sources/products_config.json
  
  # Register all configurations in a directory
  python scripts/register_data_source.py --directory config/sources
  
  # List all registered sources
  python scripts/register_data_source.py --list
  
  # Get details about a specific source
  python scripts/register_data_source.py --details products_data
  
  # Deactivate a source
  python scripts/register_data_source.py --deactivate products_data
        """
    )
    
    # Input options
    parser.add_argument("--config", type=str, help="Path to configuration file")
    parser.add_argument("--directory", type=str, help="Directory containing configuration files")
    parser.add_argument("--pattern", type=str, default="*.json", help="File pattern for directory scan")
    
    # Actions
    parser.add_argument("--list", action="store_true", help="List all registered data sources")
    parser.add_argument("--list-all", action="store_true", help="List all data sources (including inactive)")
    parser.add_argument("--details", type=str, help="Get detailed information about a data source")
    parser.add_argument("--activate", type=str, help="Activate a data source")
    parser.add_argument("--deactivate", type=str, help="Deactivate a data source")
    parser.add_argument("--unregister", type=str, help="Unregister (deactivate) a data source")
    parser.add_argument("--delete", type=str, help="Permanently delete a data source")
    
    # Options
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing configurations")
    parser.add_argument("--skip-table-validation", action="store_true", help="Skip validation of target tables")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without making changes")
    
    args = parser.parse_args()
    
    if not DATABASE_AVAILABLE:
        print("❌ Database not available")
        sys.exit(1)
    
    registrar = DataSourceRegistrar()
    
    # Handle list operations
    if args.list or args.list_all:
        sources = registrar.list_registered_sources(active_only=not args.list_all)
        
        if not sources:
            print("No data sources found")
        else:
            print(f"\n📋 Registered Data Sources ({len(sources)}):")
            print("-" * 80)
            print(f"{'Name':<25} {'Type':<10} {'Target Table':<20} {'Active':<8} {'Created'}")
            print("-" * 80)
            
            for source in sources:
                active_symbol = "✅" if source["is_active"] else "❌"
                created_date = source["created_at"][:10] if source["created_at"] else "Unknown"
                target_table = f"{source['target_schema']}.{source['target_table']}"
                
                print(f"{source['source_name']:<25} {source['source_type']:<10} {target_table:<20} {active_symbol:<8} {created_date}")
        
        return
    
    # Handle details operation
    if args.details:
        details = registrar.get_source_details(args.details)
        
        if not details:
            print(f"❌ Data source '{args.details}' not found")
            return
        
        print(f"\n📋 Data Source Details: {args.details}")
        print("=" * 50)
        print(f"Source ID: {details['source_id']}")
        print(f"Source Type: {details['source_type']}")
        print(f"Description: {details['description']}")
        print(f"Target Table: {details['target_schema']}.{details['target_table']}")
        print(f"Active: {'✅ Yes' if details['is_active'] else '❌ No'}")
        print(f"Max Retries: {details['max_retries']}")
        print(f"Timeout: {details['timeout_seconds']}s")
        print(f"Batch Size: {details['batch_size']}")
        print(f"Owner: {details['owner']}")
        print(f"Created: {details['created_at']}")
        print(f"Updated: {details['updated_at']}")
        
        if details['tags']:
            print(f"Tags: {', '.join(details['tags'])}")
        
        # Show validation rules summary
        validation_rules = details['validation_rules']
        if validation_rules:
            print(f"\nValidation Rules ({len(validation_rules)}):")
            for rule_name in validation_rules.keys():
                print(f"  • {rule_name}")
        
        # Show transformation rules summary
        transformation_rules = details['transformation_rules']
        if transformation_rules:
            print(f"\nTransformation Rules ({len(transformation_rules)}):")
            for rule in transformation_rules:
                print(f"  • {rule.get('name', 'Unknown')}")
        
        return
    
    # Handle activation/deactivation
    if args.activate:
        success = registrar.update_source_status(args.activate, True)
        sys.exit(0 if success else 1)
    
    if args.deactivate:
        success = registrar.update_source_status(args.deactivate, False)
        sys.exit(0 if success else 1)
    
    if args.unregister:
        success = registrar.unregister_source(args.unregister, hard_delete=False)
        sys.exit(0 if success else 1)
    
    if args.delete:
        if not args.dry_run:
            confirm = input(f"Are you sure you want to permanently delete '{args.delete}'? (yes/no): ")
            if confirm.lower() != "yes":
                print("Operation cancelled")
                return
        
        if args.dry_run:
            print(f"Would delete data source: {args.delete}")
        else:
            success = registrar.unregister_source(args.delete, hard_delete=True)
            sys.exit(0 if success else 1)
        return
    
    # Handle registration operations
    if args.config:
        if args.dry_run:
            print(f"Would register configuration: {args.config}")
        else:
            success = registrar.register_config(
                args.config,
                overwrite=args.overwrite,
                validate_tables=not args.skip_table_validation
            )
            sys.exit(0 if success else 1)
    
    elif args.directory:
        if args.dry_run:
            print(f"Would register all configurations in: {args.directory}")
        else:
            results = registrar.register_directory(
                args.directory,
                pattern=args.pattern,
                overwrite=args.overwrite,
                validate_tables=not args.skip_table_validation
            )
            
            # Summary
            total = len(results)
            successful = sum(1 for success in results.values() if success)
            failed = total - successful
            
            print(f"\n📊 Registration Summary:")
            print(f"  Total configurations: {total}")
            print(f"  Successful: {successful}")
            print(f"  Failed: {failed}")
            
            if failed > 0:
                print("\n❌ Failed configurations:")
                for config_file, success in results.items():
                    if not success:
                        print(f"  • {config_file}")
            
            sys.exit(0 if failed == 0 else 1)
    
    else:
        parser.print_help()

if __name__ == "__main__":
    main()