#!/usr/bin/env python3
"""
Sally Health — Push all 236 patients to EHR patient list.

Sources merged:
  - BHI/CCM summary reports (March, April, June 2026): 193 patients
  - BHI April ClaimMD import: 1 additional
  - CCD clinical summaries (42 patients): 42 additional

Usage:
    cd "/Volumes/SHIP 2/ehr_system_dev"
    source venv/bin/activate
    python3 push_patient_list.py

    # Dry-run (no API calls, just print):
    python3 push_patient_list.py --dry-run

    # If your API runs on a different port:
    python3 push_patient_list.py --url http://localhost:5000
"""

import sys
import json
import argparse
import requests
from pathlib import Path

BASE_URL = "http://localhost:8000"

# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------
def upsert_patient(patient, base_url, dry_run):
    if dry_run:
        print(f"  [DRY] {patient['mrn']:14} {patient['first_name']:15} {patient['last_name']:20} "
              f"DOB:{patient.get('dob','?'):12} {','.join(patient.get('programs',[]))}")
        return True

    # Try the standard upsert endpoint
    for endpoint in ["/api/patients/upsert", "/api/patients", "/patients"]:
        try:
            r = requests.post(f"{base_url}{endpoint}", json=patient, timeout=10)
            if r.status_code in (200, 201):
                return True
            if r.status_code == 404:
                continue  # try next endpoint
            print(f"  [WARN] {patient['mrn']} -> HTTP {r.status_code}: {r.text[:120]}")
            return False
        except requests.exceptions.ConnectionError:
            print(f"  [ERROR] Cannot connect to {base_url}{endpoint}")
            return False
        except Exception as e:
            print(f"  [ERROR] {e}")
            return False
    return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=BASE_URL, help="EHR API base URL")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    data_file = Path(__file__).parent / "all_patients_merged.json"
    if not data_file.exists():
        sys.exit(f"[ERROR] {data_file} not found. Run ingest scripts first or pull from git.")

    patients = json.loads(data_file.read_text())
    print(f"Loaded {len(patients)} patients from {data_file.name}\n")

    # Check API
    if not args.dry_run:
        try:
            r = requests.get(f"{args.url}/api/sh/lism/dashboard", timeout=5)
            print(f"API reachable: {args.url}  (HTTP {r.status_code})\n")
        except Exception as e:
            print(f"[WARNING] Cannot reach API at {args.url}: {e}")
            print("Switching to dry-run mode.\n")
            args.dry_run = True

    ok_count = fail_count = 0

    for p in patients:
        payload = {
            "mrn":          p.get("mrn", ""),
            "first_name":   p.get("first_name", ""),
            "last_name":    p.get("last_name", ""),
            "dob":          p.get("dob", ""),
            "sex":          p.get("sex", ""),
            "phone":        p.get("phone", ""),
            "email":        p.get("email", ""),
            "address_line": p.get("address_line", ""),
            "city":         p.get("city", ""),
            "state":        p.get("state", ""),
            "zip":          p.get("zip", ""),
            "insurance":    p.get("insurance", ""),
            "member_id":    p.get("member_id", ""),
            "status":       p.get("status", "Active"),
            "facility":     p.get("facility", ""),
            "physician_npi":p.get("physician_npi", ""),
            "programs":     p.get("programs", []),
            "dx_codes":     p.get("dx_codes", []),
            "source":       p.get("source", ""),
        }
        if upsert_patient(payload, args.url, args.dry_run):
            ok_count += 1
        else:
            fail_count += 1
            if not args.dry_run:
                print(f"  [FAIL] MRN={p.get('mrn')} {p.get('first_name')} {p.get('last_name')}")

    print(f"\n{'='*60}")
    print(f"Patient list push complete")
    print(f"  Total   : {len(patients)}")
    print(f"  OK      : {ok_count}")
    print(f"  Failed  : {fail_count}")
    print(f"{'='*60}")

    # Programs breakdown
    from collections import Counter
    all_progs = []
    for p in patients:
        all_progs.extend(p.get("programs", []))
    prog_counts = Counter(all_progs)
    print("\nProgram enrollment:")
    for prog, cnt in sorted(prog_counts.items()):
        print(f"  {prog}: {cnt} patients")


if __name__ == "__main__":
    main()
