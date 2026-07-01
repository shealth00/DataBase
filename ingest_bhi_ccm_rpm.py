#!/usr/bin/env python3
"""
Sally Health — BHI / CCM / RPM patient ingest
Reads all uploaded summary reports and ClaimMD import files,
deduplicates by MRN, then POSTs to the local EHR API.

Usage (run on your Mac with Flask running):
    cd "/Volumes/SHIP 2/ehr_system_dev"
    source venv/bin/activate
    python3 ingest_bhi_ccm_rpm.py
"""

import re
import sys
import json
import requests
from datetime import datetime, timedelta, time as dt_time
from pathlib import Path

try:
    import openpyxl
except ImportError:
    sys.exit("Run:  pip install openpyxl")

# ---------------------------------------------------------------------------
# Config — adjust paths if files are elsewhere
# ---------------------------------------------------------------------------
BASE_URL = "http://localhost:8000"

FILES = {
    "BHI_MAR": {"path": "BHI_MARCH_2026_Billable_Summary_Report.xlsx",  "program": "BHI", "month": "2026-03"},
    "CCM_MAR": {"path": "CCM_MARCH_2026_Billable_Summary_Report.xlsx",  "program": "CCM", "month": "2026-03"},
    "BHI_APR": {"path": "BHI_APRIL_2026_Billable_Summary_Report.xlsx",  "program": "BHI", "month": "2026-04"},
    "BHI_APR_CLAIM": {"path": "BHI_APRIL_2026_ClaimMD_Import.xlsx",     "program": "BHI", "month": "2026-04"},
    "BHI_JUN": {"path": "BHI_JUNE_2026_Billable_Summary_Report.xlsx",   "program": "BHI", "month": "2026-06"},
}

# Column indices for summary report sheets (0-based)
COL = {
    "first_name":     0,
    "middle_name":    1,
    "last_name":      2,
    "mrn":            3,
    "insurance_name": 4,
    "member_id":      5,
    "status":         6,
    "dob":            7,
    "icd_text":       8,
    "facility":       9,
    "physician_name": 10,
    "physician_npi":  11,
    "care_coord":     12,
    "clinician":      13,
    "consent":        14,
    "month_year":     15,
    "duration":       16,
    "min_duration":   17,
    "total_time":     18,
    "eligible_dos":   19,
    "cpt_code":       20,
    "service_type":   21,
    "service_notes":  22,
    "summary_notes":  23,
    "warning":        24,
    "care_status":    25,
    "consented":      26,
    "dx1": 27, "dx2": 28, "dx3": 29, "dx4": 30,
    "dx5": 31, "dx6": 32, "dx7": 33, "dx8": 34,
    "dx9": 35, "dx10": 36,
}

# ClaimMD import column names (row 1 headers)
CLAIM_COLS = [
    "pcn","payerid","payer_name","pat_name_l","pat_name_f","pat_name_m",
    "pat_dob","pat_sex","pat_rel","ins_number","ins_name_l","ins_name_f",
    "accept_assign","ref_npi","mrn","prov_npi","from_date","thru_date",
    "place_of_service","proc_code","diag_ref","diag_1","diag_2","diag_3",
    "diag_4","diag_5","diag_6","diag_7","diag_8","diag_9","diag_10",
    "units","charge","bill_npi","narrative",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def parse_timedelta_to_minutes(val):
    if isinstance(val, timedelta):
        return round(val.total_seconds() / 60, 1)
    if isinstance(val, dt_time):
        return val.hour * 60 + val.minute + val.second / 60
    return None


def parse_dx_text(text):
    """Extract ICD-10 codes from 'Chronic - E78.5 (desc)' blobs."""
    if not text:
        return []
    return re.findall(r'[A-Z]\d{2}(?:\.\d+)?', str(text))


def clean_date(val):
    if not val:
        return None
    if isinstance(val, datetime):
        return val.strftime("%Y-%m-%d")
    s = str(val).strip()
    for fmt in ("%m-%d-%Y", "%m/%d/%Y", "%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return s


def is_patient_row(row):
    """Summary files alternate: patient row (str first cell) then session rows (datetime/timedelta)."""
    return isinstance(row[0], str) and bool(row[0].strip())


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------
def parse_summary_file(path, program, month):
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb.worksheets[0]
    records = []
    rows = list(ws.iter_rows(min_row=5, values_only=True))  # skip title + blank + header

    i = 0
    while i < len(rows):
        row = rows[i]
        if not is_patient_row(row):
            i += 1
            continue

        # collect session sub-rows immediately following this patient row
        sessions = []
        j = i + 1
        while j < len(rows) and not is_patient_row(rows[j]):
            sub = rows[j]
            if any(v is not None for v in sub):
                sessions.append(sub)
            j += 1

        # pull dx codes from named dx columns AND from the icd_text blob
        dx_codes = []
        for k in range(27, 37):
            v = row[k] if k < len(row) else None
            if v:
                dx_codes += parse_dx_text(str(v))
        if not dx_codes:
            dx_codes = parse_dx_text(row[COL["icd_text"]] if len(row) > COL["icd_text"] else None)
        dx_codes = list(dict.fromkeys(dx_codes))  # dedupe, preserve order

        rec = {
            "program":        program,
            "report_month":   month,
            "first_name":     str(row[COL["first_name"]]).strip(),
            "middle_name":    str(row[COL["middle_name"]]).strip() if row[COL["middle_name"]] else None,
            "last_name":      str(row[COL["last_name"]]).strip() if len(row) > COL["last_name"] else None,
            "mrn":            str(row[COL["mrn"]]).strip() if len(row) > COL["mrn"] else None,
            "insurance_name": row[COL["insurance_name"]] if len(row) > COL["insurance_name"] else None,
            "member_id":      str(row[COL["member_id"]]).strip() if len(row) > COL["member_id"] else None,
            "status":         row[COL["status"]] if len(row) > COL["status"] else None,
            "dob":            clean_date(row[COL["dob"]] if len(row) > COL["dob"] else None),
            "facility":       row[COL["facility"]] if len(row) > COL["facility"] else None,
            "physician_name": row[COL["physician_name"]] if len(row) > COL["physician_name"] else None,
            "physician_npi":  str(row[COL["physician_npi"]]).strip() if len(row) > COL["physician_npi"] and row[COL["physician_npi"]] else None,
            "clinician":      row[COL["clinician"]] if len(row) > COL["clinician"] else None,
            "consent":        row[COL["consent"]] if len(row) > COL["consent"] else None,
            "cpt_code":       row[COL["cpt_code"]] if len(row) > COL["cpt_code"] else None,
            "service_type":   row[COL["service_type"]] if len(row) > COL["service_type"] else None,
            "eligible_dos":   clean_date(row[COL["eligible_dos"]] if len(row) > COL["eligible_dos"] else None),
            "duration_min":   parse_timedelta_to_minutes(row[COL["duration"]] if len(row) > COL["duration"] else None),
            "total_time_min": parse_timedelta_to_minutes(row[COL["total_time"]] if len(row) > COL["total_time"] else None),
            "summary_notes":  row[COL["summary_notes"]] if len(row) > COL["summary_notes"] else None,
            "dx_codes":       dx_codes,
            "session_count":  len(sessions),
        }
        records.append(rec)
        i = j

    return records


def parse_claimmd_file(path, program, month):
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb.worksheets[0]
    records = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not any(row):
            continue
        r = dict(zip(CLAIM_COLS, row))
        dx_codes = [str(r[f"diag_{n}"]).strip() for n in range(1, 11)
                    if r.get(f"diag_{n}")]
        records.append({
            "program":        program,
            "report_month":   month,
            "first_name":     r.get("pat_name_f"),
            "last_name":      r.get("pat_name_l"),
            "middle_name":    r.get("pat_name_m"),
            "mrn":            r.get("mrn"),
            "dob":            clean_date(r.get("pat_dob")),
            "sex":            r.get("pat_sex"),
            "insurance_name": r.get("payer_name"),
            "member_id":      r.get("ins_number"),
            "physician_npi":  r.get("prov_npi"),
            "cpt_code":       r.get("proc_code"),
            "eligible_dos":   clean_date(r.get("from_date")),
            "dx_codes":       dx_codes,
            "charge":         r.get("charge"),
            "narrative":      r.get("narrative"),
            "pcn":            r.get("pcn"),
        })
    return records


# ---------------------------------------------------------------------------
# API calls
# ---------------------------------------------------------------------------
def post(endpoint, payload, label=""):
    try:
        r = requests.post(f"{BASE_URL}{endpoint}", json=payload, timeout=10)
        if r.status_code in (200, 201):
            return True, r.json()
        return False, {"status": r.status_code, "body": r.text[:200]}
    except Exception as e:
        return False, {"error": str(e)}


def ingest_patient(rec, program_enrollments):
    mrn = rec.get("mrn", "").strip()
    if not mrn:
        return None

    # 1. Upsert patient demographics
    ok, resp = post("/api/patients/upsert", {
        "mrn":          mrn,
        "first_name":   rec.get("first_name"),
        "last_name":    rec.get("last_name"),
        "middle_name":  rec.get("middle_name"),
        "dob":          rec.get("dob"),
        "sex":          rec.get("sex"),
        "insurance":    rec.get("insurance_name"),
        "member_id":    rec.get("member_id"),
        "facility":     rec.get("facility"),
        "provider_npi": rec.get("physician_npi"),
    })
    patient_id = resp.get("patient_id") or resp.get("id") if ok else None

    # 2. Enroll in program (BHI / CCM / RPM) — once per mrn+program
    key = f"{mrn}:{rec['program']}"
    if key not in program_enrollments:
        program_enrollments.add(key)
        post("/api/rpm/enroll", {
            "mrn":         mrn,
            "patient_id":  patient_id,
            "program":     rec["program"],
            "consent":     rec.get("consent"),
            "clinician":   rec.get("clinician"),
            "enrolled_at": rec.get("eligible_dos") or rec.get("report_month"),
        })

    # 3. Post service/billing record
    if rec.get("cpt_code"):
        post("/api/rpm/service", {
            "mrn":          mrn,
            "patient_id":   patient_id,
            "program":      rec["program"],
            "cpt_code":     rec.get("cpt_code"),
            "dos":          rec.get("eligible_dos"),
            "duration_min": rec.get("duration_min"),
            "total_min":    rec.get("total_time_min"),
            "dx_codes":     rec.get("dx_codes", []),
            "narrative":    rec.get("narrative") or rec.get("service_type"),
            "charge":       rec.get("charge"),
            "pcn":          rec.get("pcn"),
            "report_month": rec.get("report_month"),
        })

    return {"mrn": mrn, "ok": ok, "patient_id": patient_id}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    script_dir = Path(__file__).parent
    all_records = []

    parsers = {
        "BHI_MAR":      (parse_summary_file,  "BHI_MARCH_2026_Billable_Summary_Report.xlsx",  "BHI", "2026-03"),
        "CCM_MAR":      (parse_summary_file,  "CCM_MARCH_2026_Billable_Summary_Report.xlsx",  "CCM", "2026-03"),
        "BHI_APR":      (parse_summary_file,  "BHI_APRIL_2026_Billable_Summary_Report.xlsx",  "BHI", "2026-04"),
        "BHI_APR_CLAIM":(parse_claimmd_file,  "BHI_APRIL_2026_ClaimMD_Import.xlsx",           "BHI", "2026-04"),
        "BHI_JUN":      (parse_summary_file,  "BHI_JUNE_2026_Billable_Summary_Report.xlsx",   "BHI", "2026-06"),
    }

    for label, (fn, filename, program, month) in parsers.items():
        # Try same directory as script, then Downloads
        for search_dir in [script_dir, Path.home() / "Downloads", Path("/Volumes/SHIP 2/ehr_system_dev")]:
            path = search_dir / filename
            if path.exists():
                break
        else:
            print(f"[SKIP] {label}: file not found ({filename})")
            continue

        recs = fn(path, program, month)
        print(f"[READ] {label}: {len(recs)} records from {path.name}")
        all_records.extend(recs)

    print(f"\nTotal records across all files: {len(all_records)}")

    # Deduplicate patients by MRN for summary
    unique_patients = {}
    for r in all_records:
        mrn = (r.get("mrn") or "").strip()
        if mrn and mrn not in unique_patients:
            unique_patients[mrn] = r
    print(f"Unique patients (by MRN): {len(unique_patients)}")

    # Check API is up
    try:
        ping = requests.get(f"{BASE_URL}/api/sh/lism/dashboard", timeout=5)
        print(f"API reachable: {BASE_URL}  (status {ping.status_code})\n")
    except Exception as e:
        print(f"\n[ERROR] Cannot reach API at {BASE_URL}: {e}")
        print("Make sure Flask is running:  source venv/bin/activate && python3 app.py")
        print("\nFalling back to dry-run — printing first 5 records:\n")
        for rec in all_records[:5]:
            print(json.dumps(rec, indent=2, default=str))
        return

    # Ingest
    results = {"ok": 0, "fail": 0, "skip": 0}
    program_enrollments = set()

    for rec in all_records:
        if not rec.get("mrn"):
            results["skip"] += 1
            continue
        res = ingest_patient(rec, program_enrollments)
        if res and res.get("ok"):
            results["ok"] += 1
        else:
            results["fail"] += 1
            print(f"  [FAIL] MRN={rec.get('mrn')} {rec.get('first_name')} {rec.get('last_name')}")

    print(f"\n{'='*50}")
    print(f"Ingest complete")
    print(f"  Posted OK : {results['ok']}")
    print(f"  Failed    : {results['fail']}")
    print(f"  Skipped   : {results['skip']}")
    print(f"  Programs  : {len(program_enrollments)} enrollments")
    print(f"{'='*50}")

    # Write summary JSON
    out = script_dir / "ingest_summary.json"
    out.write_text(json.dumps({
        "run_at": datetime.now().isoformat(),
        "total_records": len(all_records),
        "unique_patients": len(unique_patients),
        "results": results,
        "program_enrollments": list(program_enrollments),
    }, indent=2))
    print(f"Summary written to {out}")


if __name__ == "__main__":
    main()
