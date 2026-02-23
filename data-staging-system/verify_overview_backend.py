
import requests
import sys
import json
from datetime import datetime

API_BASE = "http://localhost:8000"
GREEN = "\033[92m"
RED = "\033[91m"
RESET = "\033[0m"

def log(msg, status="INFO", color=RESET):
    print(f"{color}[{status}] {msg}{RESET}")

def check_endpoint(name, url):
    log(f"Checking {name} at {url}...", "TEST")
    try:
        start = datetime.now()
        response = requests.get(url, timeout=5)
        duration = (datetime.now() - start).total_seconds()
        
        if response.status_code == 200:
            log(f"Success ({duration:.2f}s)", "PASS", GREEN)
            try:
                data = response.json()
                print(json.dumps(data, indent=2))
                return data
            except:
                log("Invalid JSON response", "FAIL", RED)
                return None
        else:
            log(f"Failed with status {response.status_code}", "FAIL", RED)
            print(response.text)
            return None
    except Exception as e:
        log(f"Connection failed: {e}", "FAIL", RED)
        return None

def validate_overview():
    print("="*50)
    print("VALIDATING OVERVIEW BACKEND")
    print("="*50)
    
    # 1. Health Check
    health = check_endpoint("Health Check", f"{API_BASE}/health")
    if health and health.get("status") == "healthy":
        log("System is healthy", "PASS", GREEN)
    else:
        log("System is unhealthy or status unknown", "WARN", RED)

    # 2. System Metrics
    metrics = check_endpoint("System Metrics", f"{API_BASE}/api/v1/monitoring/system-status")
    if metrics:
        batch_stats = metrics.get("batch_statistics", {})
        log(f"Recent Batches: {batch_stats.get('recent_batches')}", "INFO")
        log(f"Success Rate: {batch_stats.get('success_rate')}%", "INFO")
        # Note: Active Sources might not be in this endpoint based on code review, but checking response
    
    # 3. Load History
    history = check_endpoint("Load History", f"{API_BASE}/api/v1/upload/batches?limit=5")
    if history:
        batches = history.get("batches", [])
        log(f"Found {len(batches)} recent batches", "INFO")
        if batches:
            log(f"Latest batch: {batches[0].get('batch_id')} - {batches[0].get('status')}", "INFO")

if __name__ == "__main__":
    validate_overview()
