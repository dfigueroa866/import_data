#!/usr/bin/env python3
"""
Register catalog data sources (skus, location) in staging_meta.data_sources.
Run from m8_connect: python scripts/register_catalog_sources.py
"""

import sys
from pathlib import Path

_scripts = Path(__file__).parent
sys.path.insert(0, str(_scripts.parent / "src"))
sys.path.insert(0, str(_scripts))

from register_data_source import DataSourceRegistrar  # noqa: E402

CONFIG_DIR = Path(__file__).parent.parent / "config" / "catalog"


def main():
    registrar = DataSourceRegistrar()
    configs = ["skus_config.json", "location_config.json"]
    ok = 0
    for name in configs:
        path = CONFIG_DIR / name
        if not path.exists():
            print(f"Skip missing: {path}")
            continue
        if registrar.register_config(str(path), overwrite=True, validate_tables=False):
            ok += 1
    print(f"Registered {ok}/{len(configs)} catalog sources.")
    return 0 if ok == len(configs) else 1


if __name__ == "__main__":
    sys.exit(main())
