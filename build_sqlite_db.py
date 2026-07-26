#!/usr/bin/env python3
"""
Build / refresh the Sally Health SQLite patient mirror from
all_patients_merged.json (and optionally CCD seed JSON).

Usage:
    python3 build_sqlite_db.py
    python3 build_sqlite_db.py --db data/sally_health.db
    python3 build_sqlite_db.py --export-sql sql/patients_seed.sql
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_DB = ROOT / "data" / "sally_health.db"
SCHEMA = ROOT / "sqlite_schema.sql"
MERGED = ROOT / "all_patients_merged.json"
CCD = ROOT / "ccd_parsed.json"


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def apply_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA.read_text())
    conn.commit()


def upsert_patient(conn: sqlite3.Connection, p: dict, source_fallback: str) -> str:
    mrn = (p.get("mrn") or "").strip()
    if not mrn:
        raise ValueError("patient missing mrn")

    existing = conn.execute(
        "SELECT patient_id FROM patients WHERE mrn = ?", (mrn,)
    ).fetchone()
    patient_id = existing["patient_id"] if existing else str(uuid.uuid4())

    addr = p.get("address") or {}
    if isinstance(addr, str):
        address_line, city, state, zipcode = addr, "", "", ""
    else:
        address_line = addr.get("street") or p.get("address_line") or ""
        city = addr.get("city") or p.get("city") or ""
        state = addr.get("state") or p.get("state") or ""
        zipcode = addr.get("zip") or p.get("zip") or ""

    conn.execute(
        """
        INSERT INTO patients (
            patient_id, mrn, last_name, first_name, middle_name, dob, sex,
            address_line, city, state, zip, phone, email,
            insurance, member_id, status, facility, physician, physician_npi,
            source, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        ON CONFLICT(mrn) DO UPDATE SET
            last_name=excluded.last_name,
            first_name=excluded.first_name,
            middle_name=COALESCE(excluded.middle_name, patients.middle_name),
            dob=COALESCE(NULLIF(excluded.dob,''), patients.dob),
            sex=COALESCE(NULLIF(excluded.sex,''), patients.sex),
            address_line=COALESCE(NULLIF(excluded.address_line,''), patients.address_line),
            city=COALESCE(NULLIF(excluded.city,''), patients.city),
            state=COALESCE(NULLIF(excluded.state,''), patients.state),
            zip=COALESCE(NULLIF(excluded.zip,''), patients.zip),
            phone=COALESCE(NULLIF(excluded.phone,''), patients.phone),
            email=COALESCE(NULLIF(excluded.email,''), patients.email),
            insurance=COALESCE(NULLIF(excluded.insurance,''), patients.insurance),
            member_id=COALESCE(NULLIF(excluded.member_id,''), patients.member_id),
            status=COALESCE(NULLIF(excluded.status,''), patients.status),
            facility=COALESCE(NULLIF(excluded.facility,''), patients.facility),
            physician=COALESCE(NULLIF(excluded.physician,''), patients.physician),
            physician_npi=COALESCE(NULLIF(excluded.physician_npi,''), patients.physician_npi),
            source=excluded.source,
            updated_at=datetime('now')
        """,
        (
            patient_id,
            mrn,
            (p.get("last_name") or "").strip(),
            (p.get("first_name") or "").strip(),
            (p.get("middle_name") or "").strip() or None,
            (p.get("dob") or "").strip() or None,
            (p.get("sex") or "").strip() or None,
            address_line or None,
            city or None,
            state or None,
            zipcode or None,
            (p.get("phone") or "").strip() or None,
            (p.get("email") or "").strip() or None,
            (p.get("insurance") or "").strip() or None,
            (p.get("member_id") or "").strip() or None,
            (p.get("status") or "").strip() or None,
            (p.get("facility") or "").strip() or None,
            (p.get("physician") or "").strip() or None,
            (p.get("physician_npi") or "").strip() or None,
            (p.get("source") or source_fallback),
        ),
    )

    for program in p.get("programs") or []:
        program = str(program).strip().upper()
        if program:
            conn.execute(
                "INSERT OR IGNORE INTO patient_programs (mrn, program) VALUES (?, ?)",
                (mrn, program),
            )

    for dx in p.get("dx_codes") or []:
        dx = str(dx).strip().upper()
        if dx:
            conn.execute(
                "INSERT OR IGNORE INTO patient_dx (mrn, icd10) VALUES (?, ?)",
                (mrn, dx),
            )

    return patient_id


def load_merged(conn: sqlite3.Connection) -> int:
    if not MERGED.exists():
        raise SystemExit(f"[ERROR] missing {MERGED}")
    patients = json.loads(MERGED.read_text())
    for p in patients:
        upsert_patient(conn, p, "BHI_CCM")
    return len(patients)


def enrich_from_ccd(conn: sqlite3.Connection) -> int:
    """Fill demographics from CCD parse when merged row is sparse."""
    if not CCD.exists():
        return 0
    data = json.loads(CCD.read_text())
    # ccd_parsed.json may be list or {patients: [...]}
    if isinstance(data, dict):
        patients = data.get("patients") or data.get("records") or []
        if not patients and all(isinstance(v, dict) for v in data.values()):
            patients = list(data.values())
    else:
        patients = data

    updated = 0
    for p in patients:
        if not isinstance(p, dict):
            continue
        demo = p.get("demographics") or p
        mrn = (demo.get("mrn") or p.get("mrn") or "").strip()
        if not mrn:
            continue
        row = conn.execute("SELECT mrn FROM patients WHERE mrn = ?", (mrn,)).fetchone()
        if not row:
            upsert_patient(
                conn,
                {
                    "mrn": mrn,
                    "first_name": demo.get("first_name") or "",
                    "last_name": demo.get("last_name") or "",
                    "dob": demo.get("dob"),
                    "sex": demo.get("sex"),
                    "phone": demo.get("phone"),
                    "email": demo.get("email"),
                    "address_line": demo.get("address_line") or demo.get("street"),
                    "city": demo.get("city"),
                    "state": demo.get("state"),
                    "zip": demo.get("zip") or demo.get("postalCode"),
                    "source": "CCD",
                    "programs": [],
                    "dx_codes": [
                        x.get("icd10") or x.get("code")
                        for x in (p.get("problems") or [])
                        if isinstance(x, dict)
                    ],
                },
                "CCD",
            )
            updated += 1
            continue

        conn.execute(
            """
            UPDATE patients SET
                phone = COALESCE(NULLIF(?, ''), phone),
                email = COALESCE(NULLIF(?, ''), email),
                address_line = COALESCE(NULLIF(?, ''), address_line),
                city = COALESCE(NULLIF(?, ''), city),
                state = COALESCE(NULLIF(?, ''), state),
                zip = COALESCE(NULLIF(?, ''), zip),
                sex = COALESCE(NULLIF(?, ''), sex),
                dob = COALESCE(NULLIF(?, ''), dob),
                updated_at = datetime('now')
            WHERE mrn = ?
            """,
            (
                (demo.get("phone") or "") ,
                (demo.get("email") or ""),
                (demo.get("address_line") or demo.get("street") or ""),
                (demo.get("city") or ""),
                (demo.get("state") or ""),
                (demo.get("zip") or demo.get("postalCode") or ""),
                (demo.get("sex") or ""),
                (demo.get("dob") or ""),
                mrn,
            ),
        )
        updated += 1
    return updated


def export_sql(conn: sqlite3.Connection, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "-- Auto-generated from SQLite patient mirror",
        "-- Load into Postgres (core.patients) after schema apply:",
        "--   psql sally_health -f sql/patients_seed_postgres.sql",
        "",
        "BEGIN;",
        "",
    ]
    rows = conn.execute(
        """
        SELECT mrn, first_name, last_name, middle_name, dob, sex,
               address_line, city, state, zip, phone, email
        FROM patients
        ORDER BY last_name, first_name
        """
    ).fetchall()

    for r in rows:
        def q(v):
            if v is None or v == "":
                return "NULL"
            return "'" + str(v).replace("'", "''") + "'"

        lines.append(
            "INSERT INTO core.patients "
            "(mrn, first_name, last_name, middle_name, dob, sex, "
            "address_line, city, state, zip, phone, email) VALUES ("
            f"{q(r['mrn'])}, {q(r['first_name'])}, {q(r['last_name'])}, "
            f"{q(r['middle_name'])}, {q(r['dob'])}::date, {q(r['sex'])}, "
            f"{q(r['address_line'])}, {q(r['city'])}, {q(r['state'])}, "
            f"{q(r['zip'])}, {q(r['phone'])}, {q(r['email'])}"
            ") ON CONFLICT (mrn) DO UPDATE SET "
            "first_name=EXCLUDED.first_name, last_name=EXCLUDED.last_name, "
            "dob=COALESCE(EXCLUDED.dob, core.patients.dob), "
            "phone=COALESCE(EXCLUDED.phone, core.patients.phone), "
            "email=COALESCE(EXCLUDED.email, core.patients.email), "
            "updated_at=now();"
        )

    lines += ["", "COMMIT;", ""]
    out_path.write_text("\n".join(lines))
    print(f"Wrote Postgres seed: {out_path} ({len(rows)} patients)")


def export_sqlite_dump(conn: sqlite3.Connection, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as f:
        for line in conn.iterdump():
            f.write(f"{line}\n")
    print(f"Wrote SQLite dump: {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Sally Health SQLite mirror")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument(
        "--export-sql",
        type=Path,
        default=ROOT / "sql" / "patients_seed_postgres.sql",
    )
    parser.add_argument(
        "--export-dump",
        type=Path,
        default=ROOT / "sql" / "sally_health_sqlite_dump.sql",
    )
    args = parser.parse_args()

    conn = connect(args.db)
    apply_schema(conn)

    run_id = conn.execute(
        "INSERT INTO import_runs (source, status) VALUES ('json_seed', 'running')"
    ).lastrowid

    try:
        n = load_merged(conn)
        ccd_n = enrich_from_ccd(conn)
        total = conn.execute("SELECT COUNT(*) AS c FROM patients").fetchone()["c"]
        conn.execute(
            """
            UPDATE import_runs SET finished_at=datetime('now'), files_seen=2,
                rows_loaded=?, patients_upserted=?, status='ok',
                message=?
            WHERE run_id=?
            """,
            (n, total, f"merged={n} ccd_enriched={ccd_n} total={total}", run_id),
        )
        conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES ('patient_count', ?)",
            (str(total),),
        )
        conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES ('built_at', datetime('now'))"
        )
        conn.commit()
        print(f"SQLite ready: {args.db}")
        print(f"  patients loaded from merged JSON: {n}")
        print(f"  CCD enrich touches: {ccd_n}")
        print(f"  total patients: {total}")

        if args.export_sql:
            export_sql(conn, args.export_sql)
        if args.export_dump:
            export_sqlite_dump(conn, args.export_dump)
    except Exception as exc:
        conn.execute(
            """
            UPDATE import_runs SET finished_at=datetime('now'), status='error', message=?
            WHERE run_id=?
            """,
            (str(exc), run_id),
        )
        conn.commit()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
