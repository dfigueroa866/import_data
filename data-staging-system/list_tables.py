
import os
import sys
import psycopg2
from dotenv import load_dotenv

sys.path.append(os.path.join(os.getcwd(), 'src'))
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

def list_staging_tables():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'staging_data'
        """)
        
        rows = cursor.fetchall()
        print("Tables in staging_data:")
        for row in rows:
            print(f"- {row[0]}")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if conn: conn.close()
        
if __name__ == "__main__":
    list_staging_tables()
