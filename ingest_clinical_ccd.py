#!/usr/bin/env python3
"""
Sally Health — CCD/CDA Clinical Summary ingest
Parses HL7 C-CDA XML files and POSTs to the local EHR API.

42 patients: demographics, problems, vitals, medications, labs, allergies.

Usage (run on your Mac with Flask running):
    cd "/Volumes/SHIP 2/ehr_system_dev"
    source venv/bin/activate
    python3 ingest_clinical_ccd.py --dir ~/Downloads/ClinicalSummary_Subset_of_Patients1
    # or place the folder next to this script and run without --dir
"""

import re
import sys
import json
import argparse
import requests
from pathlib import Path
from datetime import datetime
import xml.etree.ElementTree as ET

BASE_URL = "http://localhost:8000"
NS = "urn:hl7-org:v3"

def t(tag):
    return f"{{{NS}}}{tag}"

# ---------------------------------------------------------------------------
# XML helpers
# ---------------------------------------------------------------------------
def text(el, tag):
    found = el.find(t(tag)) if el is not None else None
    return found.text if found is not None else None

def attr(el, tag, attribute):
    found = el.find(t(tag)) if el is not None else None
    return found.get(attribute) if found is not None else None

def parse_date(val):
    if not val:
        return None
    val = str(val).strip()[:8]
    try:
        return datetime.strptime(val, "%Y%m%d").strftime("%Y-%m-%d")
    except ValueError:
        return val

def find_section(root, loinc):
    for section in root.findall(f".//{t('section')}"):
        code_el = section.find(t("code"))
        if code_el is not None and code_el.get("code") == loinc:
            return section
    return None

# ---------------------------------------------------------------------------
# Section parsers
# ---------------------------------------------------------------------------
def parse_demographics(root):
    pt_role = root.find(f".//{t('patientRole')}")
    if pt_role is None:
        return {}

    id_el = pt_role.find(t("id"))
    mrn = id_el.get("extension") if id_el is not None else None

    addr = pt_role.find(t("addr"))
    street, city, state, zipcode = None, None, None, None
    if addr is not None:
        street  = text(addr, "streetAddressLine")
        city    = text(addr, "city")
        state   = text(addr, "state")
        zipcode = text(addr, "postalCode")

    telecoms = pt_role.findall(t("telecom"))
    phone = next(
        (x.get("value", "").replace("tel:", "") for x in telecoms
         if x.get("use") in ("MC", "HP") and "tel:" in x.get("value", "")),
        None,
    )
    email = next(
        (x.get("value", "").replace("mailto:", "") for x in telecoms
         if "mailto:" in x.get("value", "")),
        None,
    )

    pat = pt_role.find(t("patient"))
    if pat is None:
        return {"mrn": mrn}

    name_el = pat.find(t("name"))
    given  = text(name_el, "given") if name_el is not None else None
    family = text(name_el, "family") if name_el is not None else None

    sex_el = pat.find(t("administrativeGenderCode"))
    sex = sex_el.get("code") if sex_el is not None else None

    dob_el = pat.find(t("birthTime"))
    dob = parse_date(dob_el.get("value")) if dob_el is not None else None

    race_el = pat.find(t("raceCode"))
    race = race_el.get("displayName") if race_el is not None else None

    return {
        "mrn":          mrn,
        "first_name":   given,
        "last_name":    family,
        "dob":          dob,
        "sex":          sex,
        "race":         race,
        "phone":        phone,
        "email":        email,
        "address_line": street,
        "city":         city,
        "state":        state,
        "zip":          zipcode,
    }


def parse_problems(root):
    section = find_section(root, "11450-4")
    if section is None:
        return []
    problems = []
    for obs in section.findall(f".//{t('observation')}"):
        val = obs.find(f".//{t('value')}")
        eff = obs.find(t("effectiveTime"))
        status_el = obs.find(f".//{t('statusCode')}")
        if val is not None and val.get("code"):
            onset = None
            if eff is not None:
                low = eff.find(t("low"))
                onset = parse_date(low.get("value") if low is not None else eff.get("value"))
            problems.append({
                "code":        val.get("code"),
                "code_system": val.get("codeSystem"),
                "description": val.get("displayName"),
                "onset_date":  onset,
                "status":      status_el.get("code") if status_el is not None else None,
            })
    return problems


def parse_vitals(root):
    section = find_section(root, "8716-3")
    if section is None:
        return []
    vitals = []
    for obs in section.findall(f".//{t('observation')}"):
        code_el = obs.find(t("code"))
        val_el  = obs.find(t("value"))
        eff_el  = obs.find(t("effectiveTime"))
        if code_el is None or val_el is None:
            continue
        vitals.append({
            "name":       code_el.get("displayName"),
            "loinc":      code_el.get("code"),
            "value":      val_el.get("value"),
            "unit":       val_el.get("unit"),
            "recorded_at": parse_date(eff_el.get("value") if eff_el is not None else None),
        })
    return vitals


def parse_medications(root):
    section = find_section(root, "10160-0")
    if section is None:
        return []
    meds = []
    for entry in section.findall(f".//{t('substanceAdministration')}"):
        mat = entry.find(f".//{t('manufacturedMaterial')}")
        name_el = mat.find(t("name")) if mat is not None else None
        code_el = mat.find(t("code")) if mat is not None else None
        dose_el = entry.find(t("doseQuantity"))
        route_el = entry.find(t("routeCode"))
        eff = entry.find(t("effectiveTime"))
        if name_el is None and code_el is None:
            continue
        meds.append({
            "name":       name_el.text if name_el is not None else (code_el.get("displayName") if code_el is not None else None),
            "rxnorm":     code_el.get("code") if code_el is not None else None,
            "dose":       dose_el.get("value") if dose_el is not None else None,
            "dose_unit":  dose_el.get("unit") if dose_el is not None else None,
            "route":      route_el.get("displayName") if route_el is not None else None,
            "start_date": parse_date(eff.get("value") if eff is not None else None),
        })
    return meds


def parse_allergies(root):
    section = find_section(root, "48765-2")
    if section is None:
        return []
    allergies = []
    for obs in section.findall(f".//{t('observation')}"):
        val = obs.find(f".//{t('value')}")
        participant = obs.find(f".//{t('participantRole')}")
        substance_el = None
        if participant is not None:
            substance_el = participant.find(f".//{t('code')}")
        if val is not None or substance_el is not None:
            allergies.append({
                "substance": substance_el.get("displayName") if substance_el is not None else None,
                "reaction":  val.get("displayName") if val is not None else None,
                "code":      val.get("code") if val is not None else None,
            })
    return allergies


def parse_labs(root):
    section = find_section(root, "30954-2")
    if section is None:
        return []
    labs = []
    for obs in section.findall(f".//{t('observation')}"):
        code_el = obs.find(t("code"))
        val_el  = obs.find(t("value"))
        eff_el  = obs.find(t("effectiveTime"))
        ref_el  = obs.find(t("referenceRange"))
        interp  = obs.find(t("interpretationCode"))
        if code_el is None or val_el is None:
            continue
        ref_text = None
        if ref_el is not None:
            obs_range = ref_el.find(f".//{t('observationRange')}")
            if obs_range is not None:
                txt = obs_range.find(t("text"))
                ref_text = txt.text if txt is not None else None
        labs.append({
            "name":        code_el.get("displayName"),
            "loinc":       code_el.get("code"),
            "value":       val_el.get("value"),
            "unit":        val_el.get("unit"),
            "ref_range":   ref_text,
            "flag":        interp.get("code") if interp is not None else None,
            "resulted_at": parse_date(eff_el.get("value") if eff_el is not None else None),
        })
    return labs


def parse_encounters(root):
    section = find_section(root, "46240-8")
    if section is None:
        return []
    encounters = []
    for enc in section.findall(f".//{t('encounter')}"):
        code_el = enc.find(t("code"))
        eff     = enc.find(t("effectiveTime"))
        provider = enc.find(f".//{t('assignedPerson')}")
        pname = None
        if provider is not None:
            pname_el = provider.find(t("name"))
            if pname_el is not None:
                g = text(pname_el, "given") or ""
                f = text(pname_el, "family") or ""
                pname = f"{g} {f}".strip()
        encounters.append({
            "type":         code_el.get("displayName") if code_el is not None else None,
            "code":         code_el.get("code") if code_el is not None else None,
            "dos":          parse_date(eff.get("value") if eff is not None else None),
            "provider":     pname,
        })
    return encounters


# ---------------------------------------------------------------------------
# Parse one CCD file
# ---------------------------------------------------------------------------
def parse_ccd(path):
    tree = ET.parse(path)
    root = tree.getroot()
    demo = parse_demographics(root)
    return {
        **demo,
        "source_file":  path.name,
        "problems":     parse_problems(root),
        "vitals":       parse_vitals(root),
        "medications":  parse_medications(root),
        "allergies":    parse_allergies(root),
        "labs":         parse_labs(root),
        "encounters":   parse_encounters(root),
    }


# ---------------------------------------------------------------------------
# API calls
# ---------------------------------------------------------------------------
def post(endpoint, payload):
    try:
        r = requests.post(f"{BASE_URL}{endpoint}", json=payload, timeout=10)
        if r.status_code in (200, 201):
            return True, r.json()
        return False, {"status": r.status_code, "body": r.text[:300]}
    except Exception as e:
        return False, {"error": str(e)}


def ingest_record(rec):
    mrn = (rec.get("mrn") or "").strip()
    if not mrn:
        return False, "no MRN"

    # 1. Upsert patient demographics
    ok, resp = post("/api/patients/upsert", {
        "mrn":          mrn,
        "first_name":   rec.get("first_name"),
        "last_name":    rec.get("last_name"),
        "dob":          rec.get("dob"),
        "sex":          rec.get("sex"),
        "race":         rec.get("race"),
        "phone":        rec.get("phone"),
        "email":        rec.get("email"),
        "address_line": rec.get("address_line"),
        "city":         rec.get("city"),
        "state":        rec.get("state"),
        "zip":          rec.get("zip"),
    })
    patient_id = resp.get("patient_id") or resp.get("id") if ok else None

    # 2. Problems / diagnoses
    if rec["problems"]:
        post("/api/patients/problems", {
            "mrn": mrn, "patient_id": patient_id,
            "problems": rec["problems"],
        })

    # 3. Vitals → rpm_vitals
    for vital in rec["vitals"]:
        post("/api/rpm/vitals/ingest", {
            "mrn":         mrn,
            "patient_id":  patient_id,
            "device_type": "CCD Import",
            "analyte":     vital["name"],
            "value":       vital["value"],
            "unit":        vital["unit"],
            "recorded_at": vital["recorded_at"],
            "source":      "clinical_summary",
        })

    # 4. Medications
    if rec["medications"]:
        post("/api/patients/medications", {
            "mrn": mrn, "patient_id": patient_id,
            "medications": rec["medications"],
        })

    # 5. Allergies
    if rec["allergies"]:
        post("/api/patients/allergies", {
            "mrn": mrn, "patient_id": patient_id,
            "allergies": rec["allergies"],
        })

    # 6. Labs → lab_results
    if rec["labs"]:
        post("/api/labs/ingest", {
            "mrn": mrn, "patient_id": patient_id,
            "labs": rec["labs"],
        })

    # 7. Encounters
    if rec["encounters"]:
        post("/api/patients/encounters", {
            "mrn": mrn, "patient_id": patient_id,
            "encounters": rec["encounters"],
        })

    return ok, resp


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", default=None,
        help="Directory containing ClinicalSummary XML files")
    parser.add_argument("--dry-run", action="store_true",
        help="Parse only — do not POST to API")
    args = parser.parse_args()

    script_dir = Path(__file__).parent

    if args.dir:
        xml_dir = Path(args.dir)
    else:
        # Search common locations
        candidates = [
            script_dir / "ClinicalSummary_Subset_of_Patients1",
            Path.home() / "Downloads" / "ClinicalSummary_Subset_of_Patients1",
            Path("/Volumes/SHIP 2/ehr_system_dev/ClinicalSummary_Subset_of_Patients1"),
            script_dir,  # files dropped directly next to script
        ]
        xml_dir = next((p for p in candidates if p.exists()), script_dir)

    xml_files = sorted(xml_dir.glob("*ClinicalSummary.xml"))
    print(f"Found {len(xml_files)} CCD files in {xml_dir}\n")

    if not xml_files:
        print("No XML files found. Use --dir to specify the folder.")
        sys.exit(1)

    # Check API
    if not args.dry_run:
        try:
            r = requests.get(f"{BASE_URL}/api/sh/lism/dashboard", timeout=5)
            print(f"API reachable: {BASE_URL}  (HTTP {r.status_code})\n")
        except Exception as e:
            print(f"[WARNING] API unreachable: {e}")
            print("Running in dry-run mode instead.\n")
            args.dry_run = True

    results = {"ok": 0, "fail": 0}
    all_parsed = []

    for xml_file in xml_files:
        try:
            rec = parse_ccd(xml_file)
        except Exception as e:
            print(f"  [PARSE ERROR] {xml_file.name}: {e}")
            results["fail"] += 1
            continue

        mrn = rec.get("mrn", "?")
        name = f"{rec.get('first_name','')} {rec.get('last_name','')}".strip()

        if args.dry_run:
            print(f"  [DRY] {mrn:12} {name:30} "
                  f"Px:{len(rec['problems'])} Vx:{len(rec['vitals'])} "
                  f"Rx:{len(rec['medications'])} Lx:{len(rec['labs'])}")
            all_parsed.append(rec)
            results["ok"] += 1
            continue

        ok, resp = ingest_record(rec)
        status = "OK  " if ok else "FAIL"
        print(f"  [{status}] {mrn:12} {name:30} "
              f"Px:{len(rec['problems'])} Vx:{len(rec['vitals'])} "
              f"Rx:{len(rec['medications'])} Lx:{len(rec['labs'])}")
        if not ok:
            print(f"         -> {resp}")
            results["fail"] += 1
        else:
            results["ok"] += 1
        all_parsed.append(rec)

    print(f"\n{'='*60}")
    print(f"CCD Ingest complete  ({len(xml_files)} files)")
    print(f"  OK   : {results['ok']}")
    print(f"  FAIL : {results['fail']}")
    print(f"{'='*60}")

    # Write parsed data as JSON for inspection / fallback SQL
    out = script_dir / "ccd_parsed.json"
    out.write_text(json.dumps(all_parsed, indent=2, default=str))
    print(f"Parsed data saved to {out}")

    # Also generate SQL inserts as fallback
    sql_out = script_dir / "ccd_patients_seed.sql"
    with open(sql_out, "w") as f:
        f.write("-- Auto-generated from ClinicalSummary CCD files\n")
        f.write("-- Run against your EHR database if the API route is unavailable\n\n")
        for rec in all_parsed:
            mrn = (rec.get("mrn") or "").replace("'", "''")
            fn  = (rec.get("first_name") or "").replace("'", "''")
            ln  = (rec.get("last_name") or "").replace("'", "''")
            dob = rec.get("dob") or ""
            sex = rec.get("sex") or ""
            ph  = (rec.get("phone") or "").replace("'", "''")
            em  = (rec.get("email") or "").replace("'", "''")
            addr = (rec.get("address_line") or "").replace("'", "''")
            city = (rec.get("city") or "").replace("'", "''")
            st  = (rec.get("state") or "")
            zp  = (rec.get("zip") or "")

            f.write(
                f"INSERT INTO patients (mrn, first_name, last_name, dob, sex, phone, email, "
                f"address_line, city, state, zip) VALUES "
                f"('{mrn}','{fn}','{ln}',"
                f"{'NULL' if not dob else repr(dob)},"
                f"'{sex}','{ph}','{em}','{addr}','{city}','{st}','{zp}')\n"
                f"ON CONFLICT (mrn) DO UPDATE SET "
                f"first_name=EXCLUDED.first_name, last_name=EXCLUDED.last_name, "
                f"dob=EXCLUDED.dob, phone=EXCLUDED.phone, email=EXCLUDED.email;\n\n"
            )
    print(f"Fallback SQL written to {sql_out}")


if __name__ == "__main__":
    main()
