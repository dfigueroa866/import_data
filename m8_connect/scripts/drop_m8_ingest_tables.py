#!/usr/bin/env python3
"""Elimina tablas de staging_meta creadas por m8_ingest."""

from __future__ import annotations

import sys
from pathlib import Path

import psycopg2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

SQL_FILE = ROOT / "scripts" / "schemas" / "drop_m8_ingest_tables.sql"


def main() -> int:
    from data_staging.config import settings

    if not SQL_FILE.is_file():
        print(f"No se encontró {SQL_FILE}")
        return 1

    sql = SQL_FILE.read_text(encoding="utf-8")
    safe = str(settings.DATABASE_URL).split("@")[-1] if "@" in str(settings.DATABASE_URL) else "..."
    print(f"Conectando a ...@{safe}")
    print("Se eliminarán: ingest_deposits, organization_api_keys, organization_ingest_profiles")
    print("También se borrarán jobs RUN_SCHEDULED_LOAD en job_queue (si existen).")

    confirm = input("¿Continuar? [y/N]: ").strip().lower()
    if confirm not in ("y", "yes", "s", "si", "sí"):
        print("Cancelado.")
        return 0

    conn = psycopg2.connect(str(settings.DATABASE_URL))
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
        print("Tablas m8_ingest eliminadas correctamente.")
        return 0
    except Exception as exc:
        conn.rollback()
        print(f"Error: {exc}")
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
