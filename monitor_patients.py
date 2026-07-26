#!/usr/bin/env python3
"""
Monitor Sally Health patient records in the local SQLite mirror
(and optionally Postgres via DATABASE_URL / PG* env vars).

Designed for hourly automation + DataGrip workflows:
  - row counts, source mix, completeness
  - duplicate MRN / name+dob collisions
  - recent import_runs health
  - optional Postgres core.patients drift check

Usage:
    python3 monitor_patients.py
    python3 monitor_patients.py --json reports/monitor.json
    python3 monitor_patients.py --postgres
    python3 monitor_patients.py --fail-on-warn
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_DB = ROOT / "data" / "sally_health.db"


def sqlite_report(db_path: Path) -> dict:
    if not db_path.exists():
        return {
            "ok": False,
            "error": f"SQLite DB missing: {db_path}. Run python3 build_sqlite_db.py",
        }

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    def q(sql: str, args=()):
        return conn.execute(sql, args).fetchall()

    total = q("SELECT COUNT(*) AS c FROM patients")[0]["c"]
    by_source = {
        r["source"] or "unknown": r["c"]
        for r in q(
            "SELECT COALESCE(source,'(null)') AS source, COUNT(*) AS c "
            "FROM patients GROUP BY source ORDER BY c DESC"
        )
    }
    missing_dob = q("SELECT COUNT(*) AS c FROM patients WHERE dob IS NULL OR dob=''")[0][
        "c"
    ]
    missing_sex = q("SELECT COUNT(*) AS c FROM patients WHERE sex IS NULL OR sex=''")[0][
        "c"
    ]
    missing_insurance = q(
        "SELECT COUNT(*) AS c FROM patients WHERE insurance IS NULL OR insurance=''"
    )[0]["c"]
    blank_phone = q("SELECT COUNT(*) AS c FROM patients WHERE phone IS NULL OR phone=''")[
        0
    ]["c"]

    dup_names = [
        dict(r)
        for r in q(
            """
            SELECT lower(last_name) AS last_name, lower(first_name) AS first_name, dob,
                   COUNT(*) AS c, GROUP_CONCAT(mrn) AS mrns
            FROM patients
            WHERE dob IS NOT NULL AND dob != ''
            GROUP BY 1,2,3
            HAVING COUNT(*) > 1
            ORDER BY c DESC
            LIMIT 25
            """
        )
    ]

    programs = {
        r["program"]: r["c"]
        for r in q(
            "SELECT program, COUNT(*) AS c FROM patient_programs GROUP BY program"
        )
    }

    recent_imports = [
        dict(r)
        for r in q(
            """
            SELECT run_id, started_at, finished_at, source, files_seen, rows_loaded,
                   patients_upserted, status, message
            FROM import_runs
            ORDER BY run_id DESC
            LIMIT 10
            """
        )
    ]
    failed_imports = q(
        "SELECT COUNT(*) AS c FROM import_runs WHERE status='error'"
    )[0]["c"]
    stg_sheets = q("SELECT COUNT(*) AS c FROM stg_sheets")[0]["c"]
    stg_bhi = q("SELECT COUNT(*) AS c FROM stg_bhi_ccm")[0]["c"]
    meta = {r["key"]: r["value"] for r in q("SELECT key, value FROM meta")}

    warnings = []
    if total == 0:
        warnings.append("No patients in SQLite mirror")
    if missing_dob:
        warnings.append(f"{missing_dob} patients missing DOB")
    if missing_sex > total * 0.5:
        warnings.append(f"{missing_sex}/{total} patients missing sex")
    if dup_names:
        warnings.append(f"{len(dup_names)} possible name+DOB duplicate groups")
    if failed_imports:
        warnings.append(f"{failed_imports} failed import_runs")

    report = {
        "ok": len(warnings) == 0 or total > 0,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "engine": "sqlite",
        "db_path": str(db_path),
        "patients": total,
        "by_source": by_source,
        "programs": programs,
        "completeness": {
            "missing_dob": missing_dob,
            "missing_sex": missing_sex,
            "missing_insurance": missing_insurance,
            "missing_phone": blank_phone,
        },
        "duplicate_name_dob_groups": dup_names,
        "staging": {"stg_sheets": stg_sheets, "stg_bhi_ccm": stg_bhi},
        "recent_imports": recent_imports,
        "meta": meta,
        "warnings": warnings,
    }
    conn.close()
    return report


def integration_status() -> dict:
    """Report DataGrip/Postgres + Google Drive readiness for hourly runs."""
    imports_dir = ROOT / "imports"
    sheet_exts = {".xlsx", ".xlsm", ".csv", ".tsv"}
    pending = []
    if imports_dir.exists():
        pending = sorted(
            p.name
            for p in imports_dir.rglob("*")
            if p.is_file() and p.suffix.lower() in sheet_exts
        )
    creds = ROOT / "secrets" / "google_credentials.json"
    folder = os.environ.get("GOOGLE_DRIVE_FOLDER_ID")
    pg_configured = bool(os.environ.get("DATABASE_URL") or os.environ.get("PGHOST"))
    status = {
        "datagrip_postgres": {
            "configured": pg_configured,
            "reachable": None,
            "note": (
                "Set DATABASE_URL or PG* env to monitor local DataGrip Postgres"
                if not pg_configured
                else "Postgres env present; use --postgres to probe"
            ),
        },
        "google_drive": {
            "credentials_present": creds.exists(),
            "folder_id_set": bool(folder),
            "ready": creds.exists() and bool(folder),
            "credentials_path": str(creds),
            "folder_id": folder or None,
        },
        "local_imports": {
            "path": str(imports_dir),
            "pending_sheets": pending,
            "pending_count": len(pending),
        },
        "sqlite_mirror": {
            "path": str(DEFAULT_DB),
            "exists": DEFAULT_DB.exists(),
        },
    }
    if not status["google_drive"]["ready"]:
        status["google_drive"]["note"] = (
            "Place secrets/google_credentials.json and set GOOGLE_DRIVE_FOLDER_ID "
            "for Drive API sync; otherwise drop exports into imports/"
        )
    return status


def postgres_report() -> dict | None:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn and not os.environ.get("PGHOST"):
        return None
    try:
        import psycopg2
        import psycopg2.extras
    except ImportError:
        return {
            "ok": False,
            "error": "psycopg2 not installed (pip install psycopg2-binary)",
        }

    try:
        if dsn:
            conn = psycopg2.connect(dsn)
        else:
            conn = psycopg2.connect(
                host=os.environ.get("PGHOST", "localhost"),
                port=os.environ.get("PGPORT", "5432"),
                dbname=os.environ.get("PGDATABASE", "sally_health"),
                user=os.environ.get("PGUSER", "postgres"),
                password=os.environ.get("PGPASSWORD", ""),
            )
    except Exception as exc:
        return {"ok": False, "error": f"Postgres connection failed: {exc}"}

    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute(
            "SELECT COUNT(*) AS c FROM core.patients"
        )
        total = cur.fetchone()["c"]
        cur.execute(
            """
            SELECT COUNT(*) AS c FROM core.patients
            WHERE dob IS NULL
            """
        )
        missing_dob = cur.fetchone()["c"]
        cur.execute(
            """
            SELECT mrn, last_name, first_name, dob
            FROM core.patients
            ORDER BY updated_at DESC NULLS LAST
            LIMIT 5
            """
        )
        recent = [dict(r) for r in cur.fetchall()]
        staging = {}
        try:
            cur.execute("SELECT COUNT(*) AS c FROM stg.bhi_ccm_summary")
            staging["bhi_ccm_summary"] = cur.fetchone()["c"]
        except Exception:
            conn.rollback()
            staging["bhi_ccm_summary"] = None

        warnings = []
        if total == 0:
            warnings.append("Postgres core.patients is empty")
        if missing_dob:
            warnings.append(f"{missing_dob} Postgres patients missing DOB")

        return {
            "ok": True,
            "engine": "postgres",
            "patients": total,
            "missing_dob": missing_dob,
            "recent": recent,
            "staging": staging,
            "warnings": warnings,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
    finally:
        cur.close()
        conn.close()


def compare_counts(sqlite_n: int, pg: dict | None) -> list[str]:
    notes = []
    if not pg or not pg.get("ok"):
        return notes
    pg_n = pg.get("patients")
    if pg_n is None:
        return notes
    if sqlite_n != pg_n:
        notes.append(f"Drift: SQLite={sqlite_n} Postgres={pg_n}")
    return notes


def print_human(report: dict, pg: dict | None, integrations: dict | None = None) -> None:
    print("=== Sally Health patient monitor ===")
    print(f"checked_at: {report.get('checked_at')}")
    if report.get("error"):
        print(f"ERROR: {report['error']}")
        return
    print(f"sqlite patients: {report['patients']}")
    print(f"by source: {report['by_source']}")
    print(f"programs: {report['programs']}")
    print(f"completeness: {report['completeness']}")
    print(f"staging: {report['staging']}")
    if report["duplicate_name_dob_groups"]:
        print(f"name+dob dup groups: {len(report['duplicate_name_dob_groups'])}")
        for g in report["duplicate_name_dob_groups"][:5]:
            print(f"  {g['last_name']}, {g['first_name']} {g['dob']} → {g['mrns']}")
    if report["recent_imports"]:
        print("recent imports:")
        for r in report["recent_imports"][:5]:
            print(
                f"  #{r['run_id']} {r['status']} {r['source']} "
                f"rows={r['rows_loaded']} msg={r['message']}"
            )
    for w in report.get("warnings") or []:
        print(f"WARN: {w}")
    if integrations:
        drive = integrations.get("google_drive") or {}
        imports = integrations.get("local_imports") or {}
        pg_i = integrations.get("datagrip_postgres") or {}
        print("--- integrations ---")
        print(
            f"Drive ready: {drive.get('ready')} "
            f"(creds={drive.get('credentials_present')} folder={drive.get('folder_id_set')})"
        )
        print(
            f"imports pending: {imports.get('pending_count')} "
            f"postgres configured: {pg_i.get('configured')}"
        )
        if drive.get("note") and not drive.get("ready"):
            print(f"NOTE: {drive['note']}")
    if pg:
        print("--- postgres ---")
        if pg.get("error"):
            print(f"ERROR: {pg['error']}")
        else:
            print(f"postgres patients: {pg.get('patients')}")
            for w in pg.get("warnings") or []:
                print(f"WARN: {w}")
            for note in compare_counts(report.get("patients", 0), pg):
                print(f"WARN: {note}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--json", type=Path, help="Write JSON report path")
    parser.add_argument(
        "--postgres",
        action="store_true",
        help="Also check Postgres (DATABASE_URL or PG* env)",
    )
    parser.add_argument(
        "--fail-on-warn",
        action="store_true",
        help="Exit 1 when warnings are present",
    )
    args = parser.parse_args()

    # Ensure DB exists for monitoring in automation runs
    if not args.db.exists():
        build = ROOT / "build_sqlite_db.py"
        if build.exists():
            import subprocess

            subprocess.check_call([sys.executable, str(build), "--db", str(args.db)])

    report = sqlite_report(args.db)
    integrations = integration_status()
    pg = postgres_report() if args.postgres else None
    if pg is None and args.postgres:
        pg = {"ok": False, "error": "No DATABASE_URL / PGHOST configured"}

    drift = compare_counts(report.get("patients", 0), pg)
    if drift:
        report.setdefault("warnings", []).extend(drift)

    print_human(report, pg, integrations)

    payload = {"sqlite": report, "postgres": pg, "integrations": integrations}
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(payload, indent=2))
        print(f"Wrote {args.json}")

    # Always write latest report for the automation trail
    latest = ROOT / "reports" / "latest_monitor.json"
    latest.parent.mkdir(parents=True, exist_ok=True)
    latest.write_text(json.dumps(payload, indent=2))

    warnings = list(report.get("warnings") or [])
    if pg:
        warnings.extend(pg.get("warnings") or [])
    if report.get("error") or (pg and pg.get("error") and args.postgres):
        sys.exit(2)
    if args.fail_on_warn and warnings:
        sys.exit(1)


if __name__ == "__main__":
    main()
