
import os
import sys
import psycopg2
from dotenv import load_dotenv

sys.path.append(os.path.join(os.getcwd(), 'src'))
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

def check_schema():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'staging_meta' AND table_name = 'batch_control'
        """)
        
        rows = cursor.fetchall()
        print("Columns in staging_meta.batch_control:")
        for row in rows:
            print(f"- {row[0]} ({row[1]})")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if conn: conn.close()
        
if __name__ == "__main__":
    check_schema()
