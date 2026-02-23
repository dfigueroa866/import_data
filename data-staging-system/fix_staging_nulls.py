
import os
import sys
import psycopg2
import json
from dotenv import load_dotenv

sys.path.append(os.path.join(os.getcwd(), 'src'))
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
BATCH_ID = "cb281275-28fa-466f-b27e-301f3643655d" # Latest failing batch

def fix_nulls():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        print(f"Patching batch {BATCH_ID}...")
        
        # 1. Update processed_data JSONB to set dmd_group = 'DEFAULT' where it is null
        # Note: We also need to update the status from FAILED_PROMOTION (if set) back to COMPLETED?
        # Actually, the batch status might be COMPLETED but with error_message.
        # Promotion worker filters by validation_status='PASSED'.
        
        cursor.execute("""
            UPDATE staging_data.stage_hist
            SET processed_data = jsonb_set(processed_data, '{dmd_group}', '"DEFAULT"')
            WHERE batch_id = %s
              AND (processed_data->>'dmd_group' IS NULL OR processed_data->>'dmd_group' = '')
              AND validation_status = 'PASSED'
        """, (BATCH_ID,))
        
        updated = cursor.rowcount
        print(f"Updated {updated} rows in stage_hist.")
        
        # 2. Clear the error message in batch_control so user sees "Promote" again (if UI checks error)
        # Actually UI shows Promote if status is COMPLETED.
        cursor.execute("""
            UPDATE staging_meta.batch_control
            SET error_message = NULL
            WHERE batch_id = %s
        """, (BATCH_ID,))
        
        conn.commit()
        print("Done. Batch patched.")
            
    except Exception as e:
        print(f"Error: {e}")
        conn.rollback()
    finally:
        if conn: conn.close()
        
if __name__ == "__main__":
    fix_nulls()
