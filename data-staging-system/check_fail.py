
import os
import sys
import psycopg2
import json
from dotenv import load_dotenv

sys.path.append(os.path.join(os.getcwd(), 'src'))
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

def check_fail_status():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT batch_id, status, error_message, created_at
            FROM staging_meta.batch_control
            ORDER BY created_at DESC
            LIMIT 1
        """)
        
        row = cursor.fetchone()
        
        if row:
            print(f"Batch ID: {row[0]}")
            print(f"Status: {row[1]}")
            print(f"Error: {row[2]}")
            print(f"Created At: {row[3]}")
        else:
            print("No batches found")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if conn: conn.close()
        
if __name__ == "__main__":
    check_fail_status()
