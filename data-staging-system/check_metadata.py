
import os
import sys
import psycopg2
import json
from dotenv import load_dotenv

sys.path.append(os.path.join(os.getcwd(), 'src'))
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
BATCH_ID = "7c420b48-2d46-4406-b120-c9d994417534"

def check_batch_metadata():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        cursor.execute("SELECT metadata FROM staging_meta.batch_control WHERE batch_id = %s", (BATCH_ID,))
        row = cursor.fetchone()
        
        if row:
            metadata = row[0]
            print("Metadata Keys:", metadata.keys())
            print("Column Mappings (Wizard):", json.dumps(metadata.get("column_mappings", {}), indent=2))
            # print("Full Metadata:", json.dumps(metadata, indent=2)) 
        else:
            print("Batch not found")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if conn: conn.close()
        
if __name__ == "__main__":
    check_batch_metadata()
