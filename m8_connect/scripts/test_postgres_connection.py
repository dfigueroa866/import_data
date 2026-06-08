#!/usr/bin/env python3
"""Prueba conexión PostgreSQL usando DATABASE_URL del .env (útil con túnel Docker)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

def main() -> int:
    try:
        from data_staging.config import settings
        from data_staging.database import get_database_manager
    except Exception as e:
        print(f"Error cargando configuración: {e}")
        return 1

    url = str(settings.DATABASE_URL)
    # Ocultar contraseña en log
    safe = url.split("@")[-1] if "@" in url else url
    print(f"DATABASE_TYPE: {settings.DATABASE_TYPE}")
    print(f"Destino: ...@{safe}")

    if settings.DATABASE_TYPE and str(settings.DATABASE_TYPE) != "postgresql":
        print("ADVERTENCIA: DATABASE_TYPE no es postgresql. Workers y job_queue requieren PostgreSQL.")

    db = get_database_manager()
    info = db.test_connection()
    if info.get("status") == "connected":
        print("OK — Conexión exitosa")
        print(f"  Base de datos: {info.get('database')}")
        print(f"  Usuario: {info.get('user')}")
        print(f"  Versión: {str(info.get('version', ''))[:80]}...")
        return 0

    print(f"FALLO — {info}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
