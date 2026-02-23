
import os
import sys
import psycopg2
from dotenv import load_dotenv

# Add src to path
sys.path.append(os.path.join(os.getcwd(), 'src'))

# Load environment variables
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

def check_status():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        batch_id = 'f5d8109e-cc04-41ce-93ef-a917e2d1a4c7'
        table_name = 'staging_data.stage_hist'
        
        print(f"Checking batch {batch_id} in {table_name}")
        
        cursor.execute(f"""
            SELECT validation_status, count(*)
            FROM {table_name}
            WHERE batch_id = %s
            GROUP BY validation_status
        """, (batch_id,))
        
        rows = cursor.fetchall()
        print("Validation Status Counts:")
        for row in rows:
            print(f"- {row[0]}: {row[1]}")
            
        # Also check error_details for one failed row if any
        cursor.execute(f"""
            SELECT error_details
            FROM {table_name}
            WHERE batch_id = %s AND validation_status = 'FAILED'
            LIMIT 1
        """, (batch_id,))
        error_row = cursor.fetchone()
        if error_row:
            print(f"Sample Error Details: {error_row[0]}")
            
        # Check if validation_status defaults to PASSED if null?
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if conn: conn.close()

if __name__ == "__main__":
    check_status()
