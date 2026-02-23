
import os
import sys
import psycopg2
import json
from dotenv import load_dotenv

sys.path.append(os.path.join(os.getcwd(), 'src'))
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

def check_latest_batch_status():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT batch_id, status, records_count, metadata, error_message, created_at
            FROM staging_meta.batch_control
            ORDER BY created_at DESC
            LIMIT 1
        """)
        
        row = cursor.fetchone()
        
        if row:
            batch_id, status, count, metadata, error, created_at = row
            print(f"Batch ID: {batch_id}")
            print(f"Status: {status}")
            print(f"Records Count: {count}")
            print(f"Error Message: {error}")
            print(f"Created At: {created_at}")
            
            if metadata:
                print("Metadata Promoted Count:", metadata.get("promoted_count"))
                print("Metadata Promoted At:", metadata.get("promoted_at"))
        else:
            print("No batches found")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if conn: conn.close()
        
if __name__ == "__main__":
    check_latest_batch_status()
