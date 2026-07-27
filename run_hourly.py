#!/usr/bin/env python3
"""
Hourly Sally Health patient-records pipeline for DataGrip / SQLite / Drive.

Steps:
  1. Refresh SQLite mirror from all_patients_merged.json
  2. Convert Google Drive sheets (API if configured) or local imports/ → SQL
  3. Write reports/latest_monitor.json

Usage:
    python3 run_hourly.py
    python3 run_hourly.py --drive
    python3 run_hourly.py --postgres
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def run(cmd: list[str]) -> int:
    print("+", " ".join(cmd))
    return subprocess.call(cmd, cwd=ROOT)


def main() -> int:
    parser = argparse.ArgumentParser(description="Hourly patient-records monitor pipeline")
    parser.add_argument(
        "--drive",
        action="store_true",
        help="Attempt Google Drive sync (needs secrets + GOOGLE_DRIVE_FOLDER_ID)",
    )
    parser.add_argument(
        "--no-promote",
        action="store_true",
        help="Stage sheets without upserting into patients",
    )
    parser.add_argument(
        "--postgres",
        action="store_true",
        help="Also probe Postgres (DATABASE_URL / PG*)",
    )
    parser.add_argument(
        "--with-dump",
        action="store_true",
        help="Also export full SQLite dump SQL",
    )
    args = parser.parse_args()

    py = sys.executable
    build = [py, str(ROOT / "build_sqlite_db.py")]
    if args.with_dump:
        build.append("--with-dump")
    rc = run(build)
    if rc != 0:
        return rc

    sheets = [py, str(ROOT / "sheets_to_sqlite.py"), "--imports", str(ROOT / "imports")]
    if not args.no_promote:
        sheets.append("--promote")
    if args.drive or os.environ.get("GOOGLE_DRIVE_FOLDER_ID"):
        sheets.append("--drive")
        folder = os.environ.get("GOOGLE_DRIVE_FOLDER_ID")
        if folder:
            sheets.extend(["--folder-id", folder])
    rc = run(sheets)
    if rc != 0:
        return rc

    monitor = [py, str(ROOT / "monitor_patients.py")]
    if args.postgres:
        monitor.append("--postgres")
    return run(monitor)


if __name__ == "__main__":
    raise SystemExit(main())
