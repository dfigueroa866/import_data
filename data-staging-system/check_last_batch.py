
import os
import sys
import psycopg2
from dotenv import load_dotenv

sys.path.append(os.path.join(os.getcwd(), 'src'))
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

def check_last_batch():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT batch_id, source_name, status, error_message, created_at
            FROM staging_meta.batch_control
            ORDER BY created_at DESC
            LIMIT 1
        """)
        
        row = cursor.fetchone()
        
        if row:
            print(f"Batch ID: {row[0]}")
            print(f"Source Name: {row[1]}")
            print(f"Status: {row[2]}")
            print(f"Error Message: {row[3]}")
            print(f"Created At: {row[4]}")
        else:
            print("No batches found")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if conn: conn.close()
        
if __name__ == "__main__":
    check_last_batch()
