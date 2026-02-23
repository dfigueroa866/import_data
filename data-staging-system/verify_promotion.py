
import os, psycopg2, json
from dotenv import load_dotenv
load_dotenv()

conn = psycopg2.connect(os.getenv("DATABASE_URL"))
cur = conn.cursor()

print("=" * 70)
print("  VERIFICACIÓN COMPLETA DE PROMOCIÓN")
print("=" * 70)

# 1. Batch Control Status
print("\n1. ESTADO DEL BATCH EN batch_control:")
print("-" * 50)
cur.execute("""
    SELECT batch_id, source_name, status, records_count, error_message,
           metadata->>'promoted_count' as promoted_count,
           metadata->>'promoted_at' as promoted_at,
           metadata->>'promotion_progress' as progress,
           created_at
    FROM staging_meta.batch_control 
    ORDER BY created_at DESC LIMIT 5
""")
for r in cur.fetchall():
    print(f"  Batch ID:        {r[0]}")
    print(f"  Source:           {r[1]}")
    print(f"  Status:           {r[2]}")
    print(f"  Records Count:    {r[3]}")
    print(f"  Error:            {r[4] or 'None'}")
    print(f"  Promoted Count:   {r[5] or 'N/A'}")
    print(f"  Promoted At:      {r[6] or 'N/A'}")
    print(f"  Progress:         {r[7] or 'N/A'}%")
    print(f"  Created:          {r[8]}")
    print()

# 2. Production table count
print("\n2. REGISTROS EN PRODUCCIÓN (public.hist):")
print("-" * 50)
try:
    cur.execute("SELECT COUNT(*) FROM public.hist")
    prod_count = cur.fetchone()[0]
    print(f"  Total records in public.hist: {prod_count:,}")
except Exception as e:
    print(f"  Error querying public.hist: {e}")

# 3. Staging cleanup verification
print("\n3. ESTADO DE STAGING (stage_hist):")
print("-" * 50)
try:
    cur.execute("SELECT COUNT(*) FROM staging_data.stage_hist")
    staging_count = cur.fetchone()[0]
    print(f"  Remaining records in staging: {staging_count:,}")
    
    if staging_count > 0:
        cur.execute("SELECT validation_status, COUNT(*) FROM staging_data.stage_hist GROUP BY validation_status")
        print("  Breakdown by status:")
        for r in cur.fetchall():
            print(f"    {r[0]}: {r[1]:,}")
    else:
        print("  ✅ Staging is clean (all records removed)")
except Exception as e:
    print(f"  Table may not exist or error: {e}")

# 4. Check all staging tables
print("\n4. TODAS LAS TABLAS EN staging_data:")
print("-" * 50)
cur.execute("""
    SELECT table_name 
    FROM information_schema.tables 
    WHERE table_schema = 'staging_data'
    ORDER BY table_name
""")
tables = cur.fetchall()
for t in tables:
    cur.execute(f"SELECT COUNT(*) FROM staging_data.{t[0]}")
    count = cur.fetchone()[0]
    status = "✅ empty" if count == 0 else f"⚠️ {count:,} records"
    print(f"  {t[0]}: {status}")

# 5. Sample production data
print("\n5. MUESTRA DE DATOS EN PRODUCCIÓN (últimos 5):")
print("-" * 50)
try:
    cur.execute("""
        SELECT * FROM public.hist 
        ORDER BY imported_at DESC NULLS LAST
        LIMIT 5
    """)
    cols = [desc[0] for desc in cur.description]
    print(f"  Columns: {cols}")
    for i, r in enumerate(cur.fetchall()):
        print(f"\n  Row {i+1}:")
        for c, v in zip(cols, r):
            print(f"    {c}: {v}")
except Exception as e:
    print(f"  Error: {e}")

print("\n" + "=" * 70)
print("  FIN DE VERIFICACIÓN")
print("=" * 70)

conn.close()
