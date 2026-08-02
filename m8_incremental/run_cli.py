#!/usr/bin/env python3
"""CLI trigger for incremental loads."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT.parent / "m8_connect" / "src"))

from m8_incremental.services.orchestrator import run_all_pending, run_single_organization


def main():
    parser = argparse.ArgumentParser(description="M8 Incremental CLI")
    parser.add_argument("command", choices=["run", "run-all"])
    parser.add_argument("--org", help="Organization UUID for single-org run")
    args = parser.parse_args()

    if args.command == "run-all":
        ids = run_all_pending()
        print(f"Started runs: {ids}")
    elif args.command == "run":
        if not args.org:
            parser.error("--org is required for run")
        run_id = run_single_organization(args.org)
        print(f"Started run: {run_id}")


if __name__ == "__main__":
    main()
