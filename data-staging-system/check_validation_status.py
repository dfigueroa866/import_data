
import os, sys, psycopg2
from dotenv import load_dotenv
sys.path.append(os.path.join(os.getcwd(), 'src'))
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

def check():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    
    # 1. Check validation_status distribution in stage_hist
    cur.execute("SELECT validation_status, COUNT(*) FROM staging_data.stage_hist GROUP BY validation_status")
    print("=== validation_status distribution (ALL batches in stage_hist) ===")
    for r in cur.fetchall():
        print(f"  {r[0]} -> {r[1]}")
    
    # 2. Check the COMPLETED batch that was promoted
    cur.execute("""
        SELECT batch_id, status, error_message 
        FROM staging_meta.batch_control 
        WHERE source_name = 'hist' AND status IN ('COMPLETED', 'PROMOTED')
        ORDER BY created_at DESC LIMIT 3
    """)
    print("\n=== Recent hist batches ===")
    for r in cur.fetchall():
        print(f"  batch_id={r[0]}, status={r[1]}, error={r[2][:80] if r[2] else 'None'}")
    
    # 3. For the latest batch, show per-row details  
    cur.execute("""
        SELECT batch_id FROM staging_meta.batch_control 
        WHERE source_name = 'hist' 
        ORDER BY created_at DESC LIMIT 1
    """)
    batch_id = cur.fetchone()[0]
    
    cur.execute("""
        SELECT validation_status, is_duplicate, processed_data->>'start_date' as start_date, validation_errors
        FROM staging_data.stage_hist 
        WHERE batch_id = %s
        ORDER BY id
    """, (batch_id,))
    
    print(f"\n=== Rows for batch {batch_id} ===")
    print(f"{'status':<10} | {'dup':<6} | {'start_date':<12} | errors")
    print("-" * 70)
    for r in cur.fetchall():
        print(f"{str(r[0]):<10} | {str(r[1]):<6} | {str(r[2]):<12} | {r[3]}")
    
    conn.close()

if __name__ == "__main__":
    check()
