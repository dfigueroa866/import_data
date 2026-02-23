
import os
import sys
import psycopg2
from dotenv import load_dotenv

sys.path.append(os.path.join(os.getcwd(), 'src'))
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
BATCH_ID = "7c420b48-2d46-4406-b120-c9d994417534"

def fix_batch():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        print(f"Clearing error message for batch {BATCH_ID}...")
        cursor.execute("""
            UPDATE staging_meta.batch_control
            SET error_message = NULL
            WHERE batch_id = %s
        """, (BATCH_ID,))
        conn.commit()
        print("Done.")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if conn: conn.close()
        
if __name__ == "__main__":
    fix_batch()
