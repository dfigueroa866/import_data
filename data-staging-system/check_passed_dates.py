
import os, psycopg2
from dotenv import load_dotenv
load_dotenv()

conn = psycopg2.connect(os.getenv("DATABASE_URL"))
cur = conn.cursor()

# 1. Schema of stage_hist
cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_schema='staging_data' AND table_name='stage_hist' ORDER BY ordinal_position")
print("=== stage_hist columns ===")
for r in cur.fetchall():
    print(f"  {r[0]} ({r[1]})")

batch_id = "02a4f334-0968-44d3-8265-f7aff44a1b20"

# 2. All rows for the batch
cur.execute("""
    SELECT validation_status, is_duplicate, 
           processed_data->>'start_date' as start_date,
           processed_data->>'loc' as loc,
           processed_data->>'qty' as qty
    FROM staging_data.stage_hist 
    WHERE batch_id = %s
""", (batch_id,))

print(f"\n=== Rows for batch {batch_id} ===")
print(f"{'status':<10} | {'dup':<6} | {'start_date':<15} | {'loc':<8} | qty")
print("-" * 60)
for r in cur.fetchall():
    print(f"{str(r[0]):<10} | {str(r[1]):<6} | {str(r[2]):<15} | {str(r[3]):<8} | {r[4]}")

# 3. PASSED rows with bad dates
cur.execute("""
    SELECT COUNT(*) 
    FROM staging_data.stage_hist 
    WHERE batch_id = %s 
      AND validation_status = 'PASSED'
      AND (processed_data->>'start_date' IS NULL 
           OR processed_data->>'start_date' !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}')
""", (batch_id,))
print(f"\nPASSED rows with BAD start_date: {cur.fetchone()[0]}")

conn.close()
