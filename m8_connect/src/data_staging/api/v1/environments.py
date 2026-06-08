"""
API endpoints for managing database environment profiles.
Environments are stored in a local JSON file: data/environments.json
"""

import json
import logging
import uuid
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime

import psycopg2
from fastapi import APIRouter, HTTPException
from data_staging.schemas.environments import EnvironmentProfile, EnvironmentProfileDB


logger = logging.getLogger(__name__)

router = APIRouter()

ENVIRONMENTS_FILE = Path("./data/environments.json")


# ────────────────────────── Helpers ──────────────────────────

def _load_envs() -> List[Dict]:
    ENVIRONMENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not ENVIRONMENTS_FILE.exists():
        return []
    try:
        return json.loads(ENVIRONMENTS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_envs(envs: List[Dict]) -> None:
    ENVIRONMENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    ENVIRONMENTS_FILE.write_text(
        json.dumps(envs, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )


def _test_connection(db_url: str) -> Dict[str, Any]:
    """Try to open a psycopg2 connection and return result info."""
    try:
        conn = psycopg2.connect(db_url, connect_timeout=10)
        cur = conn.cursor()
        cur.execute("SELECT current_database(), version();")
        db_name, version = cur.fetchone()
        cur.close()
        conn.close()
        return {
            "status": "ok",
            "database": db_name,
            "version": version.split(",")[0],
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


# ────────────────────────── Routes ──────────────────────────

@router.get("/environments", response_model=List[Dict])
async def list_environments():
    """Return all saved environment profiles."""
    return _load_envs()


@router.post("/environments", response_model=Dict)
async def create_environment(profile: EnvironmentProfile):
    """Create a new environment profile (not activated automatically)."""
    envs = _load_envs()

    new_env = {
        "id": str(uuid.uuid4()),
        "name": profile.name,
        "db_url": profile.db_url,
        "description": profile.description,
        "color": profile.color,
        "is_active": len(envs) == 0,   # First one becomes active by default
        "created_at": datetime.now().isoformat(),
        "last_tested": None,
        "test_status": None,
    }
    envs.append(new_env)
    _save_envs(envs)
    logger.info(f"Created environment '{profile.name}' (id={new_env['id']})")
    return new_env


@router.put("/environments/{env_id}", response_model=Dict)
async def update_environment(env_id: str, profile: EnvironmentProfile):
    """Edit name, URL, description or color of an existing profile."""
    envs = _load_envs()
    for env in envs:
        if env["id"] == env_id:
            env.update({
                "name": profile.name,
                "db_url": profile.db_url,
                "description": profile.description,
                "color": profile.color,
                # Reset test status since URL may have changed
                "last_tested": None,
                "test_status": None,
            })
            _save_envs(envs)
            return env
    raise HTTPException(status_code=404, detail="Environment not found")


@router.delete("/environments/{env_id}")
async def delete_environment(env_id: str):
    """Delete an environment profile (cannot delete the active one)."""
    envs = _load_envs()
    target = next((e for e in envs if e["id"] == env_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Environment not found")
    if target.get("is_active"):
        raise HTTPException(status_code=400, detail="Cannot delete the active environment. Activate another one first.")
    envs = [e for e in envs if e["id"] != env_id]
    _save_envs(envs)
    return {"message": "Deleted"}


@router.post("/environments/{env_id}/activate")
async def activate_environment(env_id: str):
    """
    Set the given environment as active.
    This writes DATABASE_URL to the .env file and triggers a soft reload of the
    settings singleton so the running process picks it up on the next request.
    """
    from data_staging.config import settings as app_settings

    envs = _load_envs()
    target = next((e for e in envs if e["id"] == env_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Environment not found")

    # Mark active
    for env in envs:
        env["is_active"] = (env["id"] == env_id)
    _save_envs(envs)

    # Write to .env file so next process start uses this URL
    env_file = Path(".env")
    db_url = target["db_url"]

    updates = {"DATABASE_URL": db_url}

    if env_file.exists():
        lines = env_file.read_text(encoding="utf-8").splitlines()
        new_lines = []
        written_keys = set()
        for line in lines:
            matched = False
            for key, val in updates.items():
                if line.startswith(f"{key}="):
                    new_lines.append(f"{key}={val}")
                    written_keys.add(key)
                    matched = True
                    break
            if not matched:
                new_lines.append(line)
        # Append any keys not yet in the file
        for key, val in updates.items():
            if key not in written_keys:
                new_lines.append(f"{key}={val}")
        env_file.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    else:
        env_file.write_text(
            "\n".join(f"{k}={v}" for k, v in updates.items()) + "\n",
            encoding="utf-8"
        )

    logger.info(f"Activated environment '{target['name']}' — DATABASE_URL updated in .env")

    return {
        "message": f"Environment '{target['name']}' activated. Restart workers/API to apply the new connection.",
        "environment": target,
    }


@router.post("/environments/{env_id}/test")
async def test_environment(env_id: str):
    """Test the connection for the given environment profile."""
    envs = _load_envs()
    target = next((e for e in envs if e["id"] == env_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Environment not found")

    result = _test_connection(target["db_url"])

    # Persist result
    for env in envs:
        if env["id"] == env_id:
            env["last_tested"] = datetime.now().isoformat()
            env["test_status"] = result["status"]
    _save_envs(envs)

    return result


@router.get("/environments/active")
async def get_active_environment():
    """Return the currently active environment profile (or null)."""
    envs = _load_envs()
    active = next((e for e in envs if e.get("is_active")), None)
    return active or {}
