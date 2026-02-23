
import os
import sys
import psycopg2
import json
from dotenv import load_dotenv

sys.path.append(os.path.join(os.getcwd(), 'src'))
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
BATCH_ID = "a25da3ee-69f9-446d-be61-5626d0a5acb1"  # From logs in Step 2363

def check_staging_data():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        # Get source name to find table
        cursor.execute("SELECT source_name FROM staging_meta.batch_control WHERE batch_id = %s", (BATCH_ID,))
        row = cursor.fetchone()
        if not row:
            print("Batch not found")
            return
            
        source_name = row[0]
        safe_source_name = source_name.lower().replace(' ', '_').replace('-', '_')
        staging_table = f"stage_{safe_source_name}"
        
        print(f"Checking table: staging_data.{staging_table}")
        
        # Check counts by status
        cursor.execute(f"""
            SELECT validation_status, is_duplicate, COUNT(*)
            FROM staging_data.{staging_table}
            WHERE batch_id = %s
            GROUP BY validation_status, is_duplicate
        """, (BATCH_ID,))
        
        print("\nStaging Data Summary:")
        print("Status | Is Duplicate | Count")
        print("-" * 30)
        for row in cursor.fetchall():
            print(f"{row[0]} | {row[1]} | {row[2]}")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if conn: conn.close()
        
if __name__ == "__main__":
    check_staging_data()
