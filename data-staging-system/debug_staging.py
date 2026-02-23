import sys
import os
sys.path.append('src')
from sqlalchemy import create_engine, text
from data_staging.config import settings

# Setup DB connection
engine = create_engine(str(settings.DATABASE_URL))

# Batch ID from logs
batch_id = 'c1f2fc09-8a1f-4d43-8daf-fd30aab889be'

print(f"Checking batch: {batch_id}")

with engine.connect() as conn:
    # 1. Check batch_control metadata
    result = conn.execute(text("SELECT status, metadata, source_name FROM staging_meta.batch_control WHERE batch_id = :b"), {"b": batch_id}).fetchone()
    print(f"Batch Status: {result.status}")
    print(f"Batch Metadata: {result.metadata}")
    print(f"Source Name: {result.source_name}")
    
    # 2. Check staging table records (sample)
    # staging table name is usually stage_{source_name} normalized
    safe_source_name = result.source_name.lower().replace(' ', '_').replace('-', '_')
    staging_table = f"stage_{safe_source_name}"
    print(f"Querying table: staging_data.{staging_table}")

    try:
        query = text(f"SELECT batch_id, source_row_number, validation_status, error_details, raw_data FROM staging_data.{staging_table} WHERE batch_id = :b")
        rows = conn.execute(query, {"b": batch_id}).fetchall()
        print(f"Found {len(rows)} records in staging_data.{staging_table}")
        for row in rows[:5]:
            print(f"Row {row.source_row_number}: {row.validation_status} - Errors: {row.error_details}")
            # print(f"Raw: {row.raw_data}") 
    except Exception as e:
        print(f"Error querying staging table: {e}")
