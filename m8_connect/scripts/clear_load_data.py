#!/usr/bin/env python3
"""Vacía datos de cargas, catálogos e historia sin eliminar tablas.

Por seguridad, la ejecución sin ``--execute`` solo muestra el plan.
La configuración, organizaciones, usuarios y roles se conservan.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable

import psycopg2
from psycopg2 import sql

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

CATALOG_DEFINITIONS = ROOT / "src" / "data" / "catalog_definitions.json"
CONFIRMATION = "ELIMINAR CARGAS"

LOAD_TABLES = (
    ("staging_meta", "job_queue"),
    ("staging_meta", "validation_logs"),
    ("staging_meta", "load_history"),
    ("staging_meta", "rejected_records"),
    ("staging_meta", "batch_control"),
    ("staging_meta", "source_load_summary"),
    ("staging_meta", "incremental_runs"),
    ("staging_meta", "incremental_retention_log"),
)

HISTORY_TABLE = ("public", "sales_history")

PROTECTED_TABLES = {
    ("public", "organizations"),
    ("public", "users"),
    ("staging_meta", "alembic_version"),
    ("staging_meta", "data_sources"),
    ("staging_meta", "incremental_schedule"),
    ("staging_meta", "incremental_org_profiles"),
    ("staging_meta", "incremental_org_tables"),
    ("m8_schema", "connect_user_roles"),
    ("m8_schema", "loader_profile"),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Vacía las tablas operativas de M8 Connect. Sin --execute solo "
            "muestra las tablas afectadas."
        )
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Ejecuta la limpieza; sin esta opción se muestra una vista previa.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Omite la confirmación interactiva (útil en automatizaciones).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Permite continuar aunque existan batches o jobs activos.",
    )
    return parser.parse_args()


def catalog_tables() -> set[tuple[str, str]]:
    """Obtiene destinos de todos los catálogos configurados."""
    if not CATALOG_DEFINITIONS.is_file():
        raise FileNotFoundError(
            f"No existe el archivo de catálogos: {CATALOG_DEFINITIONS}"
        )

    payload = json.loads(CATALOG_DEFINITIONS.read_text(encoding="utf-8"))
    targets: set[tuple[str, str]] = set()
    for entry in payload.get("catalogs", []):
        schema = str(entry.get("target_schema") or "public").strip()
        table = str(entry.get("target_table") or entry.get("name") or "").strip()
        if table:
            targets.add((schema, table))

    protected = targets & PROTECTED_TABLES
    if protected:
        names = ", ".join(f"{schema}.{table}" for schema, table in sorted(protected))
        raise RuntimeError(
            f"La configuración de catálogos apunta a tablas protegidas: {names}"
        )
    return targets


def existing_tables(
    cursor,
    candidates: Iterable[tuple[str, str]],
) -> set[tuple[str, str]]:
    """Filtra candidatos que existen como tablas o tablas particionadas."""
    result: set[tuple[str, str]] = set()
    for schema, table in candidates:
        cursor.execute(
            """
            SELECT EXISTS (
                SELECT 1
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = %s
                  AND c.relname = %s
                  AND c.relkind IN ('r', 'p')
            )
            """,
            (schema, table),
        )
        if cursor.fetchone()[0]:
            result.add((schema, table))
    return result


def staging_data_tables(cursor) -> set[tuple[str, str]]:
    """Incluye todas las tablas temporales de staging_data."""
    cursor.execute(
        """
        SELECT n.nspname, c.relname
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'staging_data'
          AND c.relkind IN ('r', 'p')
        """
    )
    return {(schema, table) for schema, table in cursor.fetchall()}


def active_work(cursor) -> tuple[int, int]:
    """Cuenta trabajos que podrían estar escribiendo mientras se limpia."""
    cursor.execute(
        """
        SELECT
            (
                SELECT COUNT(*)
                FROM staging_meta.job_queue
                WHERE status IN ('PENDING', 'PROCESSING')
            ),
            (
                SELECT COUNT(*)
                FROM staging_meta.batch_control
                WHERE status IN (
                    'PENDING', 'PENDING_PROCESS', 'PENDING_MAPPING',
                    'PENDING_PREVIEW', 'UPLOADED', 'PROCESSING', 'VALIDATING',
                    'TRANSFORMING', 'LOADING', 'RETRY'
                )
            )
        """
    )
    jobs, batches = cursor.fetchone()
    return int(jobs), int(batches)


def truncate_tables(cursor, tables: set[tuple[str, str]]) -> None:
    identifiers = [
        sql.Identifier(schema, table) for schema, table in sorted(tables)
    ]
    statement = sql.SQL("TRUNCATE TABLE {} RESTART IDENTITY").format(
        sql.SQL(", ").join(identifiers)
    )
    cursor.execute(statement)


def safe_database_target(database_url: str) -> str:
    return database_url.rsplit("@", 1)[-1] if "@" in database_url else "configurada"


def print_plan(
    target: str,
    catalog_targets: set[tuple[str, str]],
    history_targets: set[tuple[str, str]],
    staging_targets: set[tuple[str, str]],
    load_targets: set[tuple[str, str]],
) -> None:
    print(f"Base de datos: ...@{target}")
    groups = (
        ("Catálogos", catalog_targets),
        ("Historia", history_targets),
        ("Datos temporales", staging_targets),
        ("Control de cargas", load_targets),
    )
    for title, tables in groups:
        print(f"\n{title}:")
        if not tables:
            print("  (ninguna tabla existente)")
        for schema, table in sorted(tables):
            print(f"  - {schema}.{table}")

    print("\nSe conservan configuraciones, organizaciones, usuarios, roles y esquemas.")
    print("Este script no elimina archivos subidos del disco.")


def main() -> int:
    args = parse_args()

    from data_staging.config import settings

    database_url = str(settings.DATABASE_URL)
    conn = psycopg2.connect(database_url, connect_timeout=10)
    try:
        with conn.cursor() as cursor:
            configured_catalogs = catalog_tables()
            catalog_targets = existing_tables(cursor, configured_catalogs)
            history_targets = existing_tables(cursor, {HISTORY_TABLE})
            staging_targets = staging_data_tables(cursor)
            load_targets = existing_tables(cursor, LOAD_TABLES)
            all_targets = (
                catalog_targets
                | history_targets
                | staging_targets
                | load_targets
            )

            print_plan(
                safe_database_target(database_url),
                catalog_targets,
                history_targets,
                staging_targets,
                load_targets,
            )

            if not args.execute:
                print("\nVista previa solamente. Usa --execute para limpiar.")
                return 0
            if not all_targets:
                print("\nNo hay tablas que limpiar.")
                return 0

            jobs, batches = active_work(cursor)
            if (jobs or batches) and not args.force:
                print(
                    "\nLimpieza cancelada: hay "
                    f"{jobs} job(s) y {batches} batch(es) activos."
                )
                print("Detén API/workers o usa --force si confirmas el riesgo.")
                return 2

            if not args.yes:
                print("\nADVERTENCIA: esta operación no se puede deshacer.")
                confirmation = input(
                    f'Escribe "{CONFIRMATION}" para continuar: '
                ).strip()
                if confirmation != CONFIRMATION:
                    print("Cancelado.")
                    return 0

            truncate_tables(cursor, all_targets)
        conn.commit()
        print("\nLimpieza completada correctamente.")
        return 0
    except Exception as exc:
        conn.rollback()
        print(f"\nError; no se aplicó ningún cambio: {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
