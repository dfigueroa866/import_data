#!/usr/bin/env python3
"""
scripts/update_core_files_schema.py
Update core system files to use public schema instead of production
"""

import sys
from pathlib import Path
import re

def update_file_schema_references(file_path, backup=True):
    """Update schema references in a file from production to public"""
    
    if not file_path.exists():
        return False
    
    try:
        # Read file content
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Create backup if requested
        if backup:
            backup_path = file_path.with_suffix(file_path.suffix + '.backup')
            with open(backup_path, 'w', encoding='utf-8') as f:
                f.write(content)
        
        # Update schema references
        original_content = content
        
        # Replace production schema references
        patterns = [
            (r'production\.(\w+)', r'm8_schema.\1'),  # production.table_name
            (r'"production"', r'"m8_schema"'),        # "production" strings
            (r"'production'", r"'m8_schema'"),        # 'production' strings
            (r'production_schema.*?=.*?"production"', r'production_schema = "m8_schema"'),
            (r'production_schema.*?=.*?\'production\'', r'production_schema = \'m8_schema\''),
            (r'target_schema.*?=.*?"production"', r'target_schema = "m8_schema"'),
            (r'target_schema.*?=.*?\'production\'', r'target_schema = \'m8_schema\''),
        ]
        
        for pattern, replacement in patterns:
            content = re.sub(pattern, replacement, content)
        
        # Only write if changes were made
        if content != original_content:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            return True
        
        return False
        
    except Exception as e:
        print(f"❌ Error updating {file_path}: {e}")
        return False

def update_core_files():
    """Update core system files to use public schema"""
    
    # List of files to update
    files_to_update = [
        # Core system files
        "src/data_staging/core/etl/staging_pipeline.py",
        "src/data_staging/api/v1/upload.py",
        "src/data_staging/api/v1/staging.py",
        
        # Configuration files
        "src/data_staging/config.py",
        
        # Example files
        "examples/data_source_configuration.py",
        "examples/file_upload_examples.py",
        
        # Test files
        "test_products_upload.py",
        "test_history_upload.py",
        
        # Any other Python files that might reference production schema
    ]
    
    project_root = Path(__file__).parent.parent
    updated_files = []
    
    print("🔄 Updating core system files...")
    
    for file_path in files_to_update:
        full_path = project_root / file_path
        
        if full_path.exists():
            if update_file_schema_references(full_path):
                updated_files.append(file_path)
                print(f"   ✅ Updated: {file_path}")
            else:
                print(f"   ⏭️ No changes: {file_path}")
        else:
            print(f"   ⚠️ Not found: {file_path}")
    
    # Update any additional files found with schema references
    src_dir = project_root / "src"
    if src_dir.exists():
        for py_file in src_dir.rglob("*.py"):
            relative_path = py_file.relative_to(project_root)
            if str(relative_path) not in files_to_update:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    if 'production.' in content or '"production"' in content or "'production'" in content:
                        if update_file_schema_references(py_file):
                            updated_files.append(str(relative_path))
                            print(f"   ✅ Updated: {relative_path}")
    
    return updated_files

if __name__ == "__main__":
    print("🔄 Updating Core Files: production → public schema")
    print("=" * 50)
    
    updated_files = update_core_files()
    
    print(f"\n📊 Summary:")
    print(f"   Updated files: {len(updated_files)}")
    
    if updated_files:
        print(f"\n📋 Updated files:")
        for file_path in updated_files:
            print(f"   • {file_path}")
        
        print(f"\n💾 Backup files created with .backup extension")
    
    print(f"\n✅ Core files update completed!")