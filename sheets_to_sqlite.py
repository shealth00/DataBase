#!/usr/bin/env python3
"""
Convert Google Drive spreadsheets (or local exports) into SQLite staging +
optional patient upserts. Emits SQL suitable for DataGrip / Postgres.

Modes:
  1) Local folder (default) — drop Drive Desktop / exported .xlsx/.csv into imports/
  2) Google Drive API — list & download Sheets when credentials are present

Usage:
    python3 sheets_to_sqlite.py
    python3 sheets_to_sqlite.py --imports ./imports --promote
    python3 sheets_to_sqlite.py --drive --folder-id <GOOGLE_DRIVE_FOLDER_ID>
    python3 sheets_to_sqlite.py --file imports/BHI_JUNE_2026_Billable_Summary_Report.xlsx --program BHI

Credentials (optional, Drive API):
    secrets/google_credentials.json   # OAuth client or service account
    secrets/google_token.json         # OAuth token (created on first login)
    env GOOGLE_DRIVE_FOLDER_ID
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_DB = ROOT / "data" / "sally_health.db"
DEFAULT_IMPORTS = ROOT / "imports"
SCHEMA = ROOT / "sqlite_schema.sql"
SECRETS = ROOT / "secrets"
PATIENT_NS = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")


def patient_id_for(mrn: str) -> str:
    return str(uuid.uuid5(PATIENT_NS, mrn.strip()))

# Column layout from ingest_bhi_ccm_rpm.py summary reports
BHI_COL = {
    "first_name": 0,
    "middle_name": 1,
    "last_name": 2,
    "mrn": 3,
    "insurance_name": 4,
    "member_id": 5,
    "status": 6,
    "dob": 7,
    "facility": 9,
    "physician_name": 10,
    "physician_npi": 11,
    "cpt_code": 20,
    "service_type": 21,
    "dx1": 27,
    "dx2": 28,
    "dx3": 29,
    "dx4": 30,
    "dx5": 31,
    "dx6": 32,
    "dx7": 33,
    "dx8": 34,
    "dx9": 35,
    "dx10": 36,
}

SHEET_EXTS = {".xlsx", ".xlsm", ".csv", ".tsv", ".gsheet"}


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if SCHEMA.exists():
        conn.executescript(SCHEMA.read_text())
        conn.commit()
    return conn


def slug(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", s).strip("_")[:80]


def infer_program(path: Path, override: str | None) -> str | None:
    if override:
        return override.upper()
    name = path.name.upper()
    for prog in ("BHI", "CCM", "RPM"):
        if prog in name:
            return prog
    return None


def infer_month(path: Path) -> str | None:
    m = re.search(
        r"(JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER)[_\s-]*(\d{4})",
        path.name,
        re.I,
    )
    if not m:
        m2 = re.search(r"(20\d{2})[-_](\d{2})", path.name)
        return f"{m2.group(1)}-{m2.group(2)}" if m2 else None
    months = {
        "january": "01",
        "february": "02",
        "march": "03",
        "april": "04",
        "may": "05",
        "june": "06",
        "july": "07",
        "august": "08",
        "september": "09",
        "october": "10",
        "november": "11",
        "december": "12",
    }
    return f"{m.group(2)}-{months[m.group(1).lower()]}"


def cell(row: list, idx: int) -> str:
    if idx >= len(row):
        return ""
    v = row[idx]
    if v is None:
        return ""
    return str(v).strip()


def normalize_dob(val: str) -> str:
    if not val:
        return ""
    val = val.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y", "%Y/%m/%d", "%m/%d/%y"):
        try:
            return datetime.strptime(val[:10], fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    # Excel serial as string
    if re.fullmatch(r"\d{5}(\.\d+)?", val):
        try:
            from datetime import date, timedelta

            base = date(1899, 12, 30)
            return (base + timedelta(days=int(float(val)))).isoformat()
        except Exception:
            return val
    return val


def read_csv(path: Path) -> list[tuple[str, list[list]]]:
    dialect = "excel-tab" if path.suffix.lower() == ".tsv" else "excel"
    with path.open(newline="", encoding="utf-8-sig", errors="replace") as f:
        rows = [list(r) for r in csv.reader(f, dialect=dialect)]
    return [(path.stem, rows)]


def read_xlsx(path: Path) -> list[tuple[str, list[list]]]:
    try:
        import openpyxl
    except ImportError:
        sys.exit("Install openpyxl: pip install openpyxl")
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    out = []
    for ws in wb.worksheets:
        rows = []
        for row in ws.iter_rows(values_only=True):
            rows.append([("" if c is None else c) for c in row])
        out.append((ws.title, rows))
    return out


def read_workbook(path: Path) -> list[tuple[str, list[list]]]:
    ext = path.suffix.lower()
    if ext in {".csv", ".tsv"}:
        return read_csv(path)
    if ext in {".xlsx", ".xlsm"}:
        return read_xlsx(path)
    raise ValueError(f"Unsupported file type: {path}")


def looks_like_bhi_header(row: list) -> bool:
    joined = " ".join(str(c).lower() for c in row[:8])
    return "mrn" in joined and ("first" in joined or "patient" in joined)


def load_sheet_rows(
    conn: sqlite3.Connection,
    path: Path,
    batch_id: str,
    program: str | None,
    month_label: str | None,
    drive_file_id: str | None = None,
) -> tuple[int, int]:
    sheets = read_workbook(path)
    rows_loaded = 0
    bhi_rows = 0

    # Replacing the same batch_id keeps fixture/hourly re-runs idempotent.
    conn.execute("DELETE FROM stg_sheets WHERE batch_id = ?", (batch_id,))
    conn.execute("DELETE FROM stg_bhi_ccm WHERE batch_id = ?", (batch_id,))

    for sheet_name, rows in sheets:
        start = 0
        if rows and looks_like_bhi_header(rows[0]):
            start = 1
        for i, row in enumerate(rows[start:], start=start + 1):
            if not any(str(c).strip() for c in row if c is not None):
                continue
            raw = {f"c{idx}": ("" if c is None else str(c)) for idx, c in enumerate(row)}
            # Prefer header names when present
            if start == 1 and rows:
                headers = [str(h or f"c{n}").strip() or f"c{n}" for n, h in enumerate(rows[0])]
                raw = {
                    headers[n] if n < len(headers) else f"c{n}": (
                        "" if c is None else str(c)
                    )
                    for n, c in enumerate(row)
                }

            conn.execute(
                """
                INSERT INTO stg_sheets
                    (batch_id, source_file, sheet_name, drive_file_id, row_num, raw_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    batch_id,
                    path.name,
                    sheet_name,
                    drive_file_id,
                    i,
                    json.dumps(raw, ensure_ascii=False),
                ),
            )
            rows_loaded += 1

            # Structured BHI/CCM staging when layout matches
            if program or "Billable_Summary" in path.name or "ClaimMD" in path.name:
                first = cell(row, BHI_COL["first_name"])
                last = cell(row, BHI_COL["last_name"])
                mrn = cell(row, BHI_COL["mrn"])
                if not (first or last or mrn):
                    continue
                conn.execute(
                    """
                    INSERT INTO stg_bhi_ccm (
                        batch_id, source_file, program, month_label,
                        first_name, middle_name, last_name, mrn,
                        insurance_name, member_id, status, dob, facility,
                        physician_name, physician_npi, cpt_code, service_type,
                        dx1, dx2, dx3, dx4, dx5, dx6, dx7, dx8, dx9, dx10, raw_json
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        batch_id,
                        path.name,
                        program,
                        month_label,
                        first,
                        cell(row, BHI_COL["middle_name"]),
                        last,
                        mrn,
                        cell(row, BHI_COL["insurance_name"]),
                        cell(row, BHI_COL["member_id"]),
                        cell(row, BHI_COL["status"]),
                        normalize_dob(cell(row, BHI_COL["dob"])),
                        cell(row, BHI_COL["facility"]),
                        cell(row, BHI_COL["physician_name"]),
                        cell(row, BHI_COL["physician_npi"]),
                        cell(row, BHI_COL["cpt_code"]),
                        cell(row, BHI_COL["service_type"]),
                        cell(row, BHI_COL["dx1"]),
                        cell(row, BHI_COL["dx2"]),
                        cell(row, BHI_COL["dx3"]),
                        cell(row, BHI_COL["dx4"]),
                        cell(row, BHI_COL["dx5"]),
                        cell(row, BHI_COL["dx6"]),
                        cell(row, BHI_COL["dx7"]),
                        cell(row, BHI_COL["dx8"]),
                        cell(row, BHI_COL["dx9"]),
                        cell(row, BHI_COL["dx10"]),
                        json.dumps(raw, ensure_ascii=False),
                    ),
                )
                bhi_rows += 1

    return rows_loaded, bhi_rows


def promote_bhi_to_patients(conn: sqlite3.Connection, batch_id: str) -> int:
    rows = conn.execute(
        """
        SELECT * FROM stg_bhi_ccm
        WHERE batch_id = ? AND mrn IS NOT NULL AND TRIM(mrn) != ''
        """,
        (batch_id,),
    ).fetchall()
    upserted = 0
    for r in rows:
        mrn = r["mrn"].strip()
        existing = conn.execute(
            "SELECT patient_id FROM patients WHERE mrn = ?", (mrn,)
        ).fetchone()
        patient_id = existing["patient_id"] if existing else patient_id_for(mrn)
        source = f"sheet:{r['source_file']}"
        conn.execute(
            """
            INSERT INTO patients (
                patient_id, mrn, last_name, first_name, middle_name, dob, sex,
                insurance, member_id, status, facility, physician, physician_npi,
                source, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(mrn) DO UPDATE SET
                last_name=excluded.last_name,
                first_name=excluded.first_name,
                middle_name=COALESCE(excluded.middle_name, patients.middle_name),
                dob=COALESCE(NULLIF(excluded.dob,''), patients.dob),
                insurance=COALESCE(NULLIF(excluded.insurance,''), patients.insurance),
                member_id=COALESCE(NULLIF(excluded.member_id,''), patients.member_id),
                status=COALESCE(NULLIF(excluded.status,''), patients.status),
                facility=COALESCE(NULLIF(excluded.facility,''), patients.facility),
                physician=COALESCE(NULLIF(excluded.physician,''), patients.physician),
                physician_npi=COALESCE(NULLIF(excluded.physician_npi,''), patients.physician_npi),
                -- Keep canonical seed source (BHI_CCM/CCD); only stamp sheet source on inserts.
                source=COALESCE(NULLIF(patients.source, ''), excluded.source),
                updated_at=datetime('now')
            """,
            (
                patient_id,
                mrn,
                (r["last_name"] or "").strip(),
                (r["first_name"] or "").strip(),
                (r["middle_name"] or None),
                (r["dob"] or None),
                (r["insurance_name"] or None),
                (r["member_id"] or None),
                (r["status"] or None),
                (r["facility"] or None),
                (r["physician_name"] or None),
                (r["physician_npi"] or None),
                source,
            ),
        )
        if r["program"]:
            conn.execute(
                "INSERT OR IGNORE INTO patient_programs (mrn, program) VALUES (?, ?)",
                (mrn, r["program"].upper()),
            )
        for key in (
            "dx1",
            "dx2",
            "dx3",
            "dx4",
            "dx5",
            "dx6",
            "dx7",
            "dx8",
            "dx9",
            "dx10",
        ):
            dx = (r[key] or "").strip().upper()
            if dx:
                conn.execute(
                    "INSERT OR IGNORE INTO patient_dx (mrn, icd10) VALUES (?, ?)",
                    (mrn, dx),
                )
        upserted += 1
    return upserted


def export_staging_sql(conn: sqlite3.Connection, batch_id: str, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rows = conn.execute(
        "SELECT * FROM stg_bhi_ccm WHERE batch_id = ? ORDER BY row_id", (batch_id,)
    ).fetchall()
    lines = [
        f"-- Staging SQL generated {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')} batch={batch_id}",
        "-- Apply after sally_health_schema.sql (stg.bhi_ccm_summary).",
        "BEGIN;",
        "",
    ]

    def q(v):
        if v is None or v == "":
            return "NULL"
        return "'" + str(v).replace("'", "''") + "'"

    for r in rows:
        lines.append(
            "INSERT INTO stg.bhi_ccm_summary ("
            "batch_id, source_file, program, month_label, first_name, middle_name, "
            "last_name, mrn, insurance_name, member_id, status, dob, facility, "
            "physician_name, physician_npi, cpt_code, service_type, "
            "dx1, dx2, dx3, dx4, dx5, dx6, dx7, dx8, dx9, dx10, raw_row"
            ") VALUES ("
            f"{q(r['batch_id'])}, {q(r['source_file'])}, {q(r['program'])}, "
            f"{q(r['month_label'])}, {q(r['first_name'])}, {q(r['middle_name'])}, "
            f"{q(r['last_name'])}, {q(r['mrn'])}, {q(r['insurance_name'])}, "
            f"{q(r['member_id'])}, {q(r['status'])}, {q(r['dob'])}, {q(r['facility'])}, "
            f"{q(r['physician_name'])}, {q(r['physician_npi'])}, {q(r['cpt_code'])}, "
            f"{q(r['service_type'])}, {q(r['dx1'])}, {q(r['dx2'])}, {q(r['dx3'])}, "
            f"{q(r['dx4'])}, {q(r['dx5'])}, {q(r['dx6'])}, {q(r['dx7'])}, {q(r['dx8'])}, "
            f"{q(r['dx9'])}, {q(r['dx10'])}, {q(r['raw_json'])}::jsonb);"
        )
    lines += ["", "COMMIT;", ""]
    out_path.write_text("\n".join(lines))
    print(f"Wrote Postgres staging SQL: {out_path} ({len(rows)} rows)")


def list_local_files(imports_dir: Path, single: Path | None) -> list[Path]:
    if single:
        return [single]
    files = []
    for p in sorted(imports_dir.rglob("*")):
        if p.is_file() and p.suffix.lower() in SHEET_EXTS - {".gsheet"}:
            files.append(p)
    return files


def drive_download(folder_id: str, dest: Path) -> list[Path]:
    """Download Google Sheets / Excel from a Drive folder when creds exist."""
    creds_path = SECRETS / "google_credentials.json"
    token_path = SECRETS / "google_token.json"
    if not creds_path.exists():
        print(
            "[WARN] secrets/google_credentials.json not found — "
            "skipping Drive API; use local imports/ exports instead."
        )
        return []

    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google.oauth2 import service_account
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaIoBaseDownload
    except ImportError:
        print(
            "[WARN] Google API libs missing. Install: "
            "pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib"
        )
        return []

    import io

    SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
    info = json.loads(creds_path.read_text())
    dest.mkdir(parents=True, exist_ok=True)

    if info.get("type") == "service_account":
        creds = service_account.Credentials.from_service_account_file(
            str(creds_path), scopes=SCOPES
        )
    else:
        creds = None
        if token_path.exists():
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
                # Cloud agents cannot open a browser — fail clearly.
                raise SystemExit(
                    "OAuth browser flow required. Place a service-account JSON in "
                    "secrets/google_credentials.json, or pre-create secrets/google_token.json."
                )
            token_path.write_text(creds.to_json())

    service = build("drive", "v3", credentials=creds)
    query = (
        f"'{folder_id}' in parents and trashed=false and ("
        "mimeType='application/vnd.google-apps.spreadsheet' or "
        "mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' or "
        "mimeType='text/csv')"
    )
    resp = (
        service.files()
        .list(q=query, fields="files(id,name,mimeType)", pageSize=100)
        .execute()
    )
    downloaded: list[Path] = []
    for fmeta in resp.get("files", []):
        fid, name, mime = fmeta["id"], fmeta["name"], fmeta["mimeType"]
        if mime == "application/vnd.google-apps.spreadsheet":
            out = dest / f"{slug(name)}.xlsx"
            request = service.files().export_media(
                fileId=fid,
                mimeType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        else:
            ext = ".csv" if mime == "text/csv" else ".xlsx"
            if not name.lower().endswith(ext):
                name = f"{name}{ext}"
            out = dest / name
            request = service.files().get_media(fileId=fid)

        with out.open("wb") as fh:
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
        # stash drive id beside file for provenance
        (out.parent / f"{out.name}.drive.json").write_text(
            json.dumps({"id": fid, "name": fmeta["name"], "mimeType": mime}, indent=2)
        )
        downloaded.append(out)
        print(f"  downloaded: {out.name}")
    return downloaded


def process_files(
    conn: sqlite3.Connection,
    files: list[Path],
    promote: bool,
    program_override: str | None,
    batch_id_override: str | None = None,
) -> None:
    if not files:
        print("No spreadsheet files found to convert.")
        return

    for path in files:
        batch_id = batch_id_override or (
            f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{slug(path.stem)}"
        )
        program = infer_program(path, program_override)
        month_label = infer_month(path)
        drive_meta = path.with_suffix(path.suffix + ".drive.json")
        drive_id = None
        if drive_meta.exists():
            drive_id = json.loads(drive_meta.read_text()).get("id")

        run_id = conn.execute(
            "INSERT INTO import_runs (source, status, message) VALUES (?, 'running', ?)",
            ("google_drive" if drive_id else "local_sheet", path.name),
        ).lastrowid

        try:
            rows_loaded, bhi_rows = load_sheet_rows(
                conn, path, batch_id, program, month_label, drive_id
            )
            promoted = promote_bhi_to_patients(conn, batch_id) if promote else 0
            sql_out = ROOT / "sql" / f"stg_{batch_id}.sql"
            export_staging_sql(conn, batch_id, sql_out)
            conn.execute(
                """
                UPDATE import_runs SET finished_at=datetime('now'), files_seen=1,
                    rows_loaded=?, patients_upserted=?, status='ok',
                    message=?
                WHERE run_id=?
                """,
                (
                    rows_loaded,
                    promoted,
                    f"bhi_rows={bhi_rows} promote={promote} batch={batch_id}",
                    run_id,
                ),
            )
            conn.commit()
            print(
                f"OK {path.name}: staged={rows_loaded} bhi={bhi_rows} "
                f"promoted={promoted} batch={batch_id}"
            )
        except Exception as exc:
            conn.execute(
                """
                UPDATE import_runs SET finished_at=datetime('now'), status='error', message=?
                WHERE run_id=?
                """,
                (str(exc), run_id),
            )
            conn.commit()
            print(f"ERROR {path.name}: {exc}", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description="Google Drive / sheets → SQLite → SQL")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--imports", type=Path, default=DEFAULT_IMPORTS)
    parser.add_argument("--file", type=Path, help="Convert a single spreadsheet")
    parser.add_argument("--drive", action="store_true", help="Pull from Google Drive")
    parser.add_argument("--folder-id", default=None, help="Drive folder id")
    parser.add_argument(
        "--promote",
        action="store_true",
        help="Upsert stg_bhi_ccm rows into patients",
    )
    parser.add_argument("--program", default=None, help="Force program BHI|CCM|RPM")
    parser.add_argument(
        "--batch-id",
        default=None,
        help="Force staging batch id (useful for fixtures / deterministic SQL)",
    )
    args = parser.parse_args()

    args.imports.mkdir(parents=True, exist_ok=True)
    conn = connect(args.db)

    files: list[Path] = []
    if args.drive:
        folder_id = args.folder_id or __import__("os").environ.get("GOOGLE_DRIVE_FOLDER_ID")
        creds = SECRETS / "google_credentials.json"
        if not creds.exists():
            print(
                "[WARN] --drive set but secrets/google_credentials.json missing; "
                "falling back to local imports/"
            )
        elif not folder_id:
            print(
                "[WARN] --drive set but no --folder-id / GOOGLE_DRIVE_FOLDER_ID; "
                "falling back to local imports/"
            )
        else:
            print(f"Fetching Drive folder {folder_id} …")
            files.extend(drive_download(folder_id, args.imports / "drive"))

    files.extend(list_local_files(args.imports, args.file))
    # de-dupe by resolved path
    seen = set()
    uniq = []
    for f in files:
        rp = f.resolve()
        if rp not in seen:
            seen.add(rp)
            uniq.append(f)

    process_files(conn, uniq, args.promote, args.program, args.batch_id)
    total = conn.execute("SELECT COUNT(*) AS c FROM patients").fetchone()["c"]
    staged = conn.execute("SELECT COUNT(*) AS c FROM stg_sheets").fetchone()["c"]
    print(f"DB {args.db}: patients={total} stg_sheets={staged}")
    conn.close()


if __name__ == "__main__":
    main()
