"""
Script to manually create a job for the stuck batch
Run this to force-create the processing job
"""
import sys
sys.path.insert(0, r'd:\Desarroll os\data_staging_to_prod\data-staging-system\src')

from data_staging.workers.job_queue import create_job
from data_staging.config import settings

# Your batch ID from the screenshot
batch_id = "6453af7-99f8-4f48-a3bf-a0e16683949d"  # Complete with full ID

# Create the job
job_id = create_job(
    database_url=str(settings.DATABASE_URL),
    job_type="PROCESS_FILE",
    payload={
        "batch_id": batch_id,
        # These will be read from batch_control metadata by the worker
    },
    priority=0
)

print(f"✅ Job created successfully: {job_id}")
print(f"Worker should pick it up within seconds")
