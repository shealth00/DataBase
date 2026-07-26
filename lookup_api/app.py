#!/usr/bin/env python3
"""
Sally Health — Patient Lookup API
Runs on vm-01 (129.80.132.81). Bridges Apps Script -> Postgres.

Endpoints:
  GET  /api/sh/health
  GET  /api/sh/patient-lookup?q=...&last=...&first=...&dob=YYYY-MM-DD
  GET  /api/sh/patient/<patient_id>
  POST /api/sh/import
  GET  /api/sh/report?type=status|payer|dos_range|incomplete

Auth: X-API-Key header (set SALLY_API_KEY env var).
"""
import os
from datetime import datetime, date
from flask import Flask, request, jsonify
from flask_cors import CORS
import psycopg
from psycopg.rows import dict_row

app = Flask(__name__)
CORS(app)

DSN = os.environ.get(
    "SALLY_DSN",
    "host=127.0.0.1 port=5432 dbname=sallyhealth user=izzy options='-c search_path=lookup,public'"
)
API_KEY = os.environ.get("SALLY_API_KEY", "change-me-in-prod")


def db():
    return psycopg.connect(DSN, row_factory=dict_row)


def require_key():
    return request.headers.get("X-API-Key") == API_KEY


def parse_date(s):
    if not s:
        return None
    s = str(s).strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def jdefault(o):
    if isinstance(o, (date, datetime)):
        return o.isoformat()
    return str(o)


def _dump(obj):
    import json
    return json.dumps(obj, default=jdefault)


@app.get("/api/sh/health")
def health():
    try:
        with db() as c, c.cursor() as cur:
            cur.execute("SELECT count(*) AS n FROM lookup.patient")
            n = cur.fetchone()["n"]
        return jsonify(ok=True, patients=n)
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 500


@app.get("/api/sh/patient-lookup")
def patient_lookup():
    if not require_key():
        return jsonify(error="unauthorized"), 401
    q     = (request.args.get("q") or "").strip()
    last  = (request.args.get("last") or "").strip()
    first = (request.args.get("first") or "").strip()
    dob   = parse_date(request.args.get("dob"))

    where, params = [], []
    if q:
        where.append("(member_id ILIKE %s OR last_name ILIKE %s OR first_name ILIKE %s)")
        params += [f"%{q}%", f"%{q}%", f"%{q}%"]
    if last:
        where.append("last_name ILIKE %s");  params.append(f"{last}%")
    if first:
        where.append("first_name ILIKE %s"); params.append(f"{first}%")
    if dob:
        where.append("dob = %s");             params.append(dob)

    sql = "SELECT * FROM lookup.v_patient_summary"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY last_name, first_name LIMIT 50"

    with db() as c, c.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
    return app.response_class(_dump({"count": len(rows), "results": rows}),
                              mimetype="application/json")


@app.get("/api/sh/patient/<int:pid>")
def patient_detail(pid):
    if not require_key():
        return jsonify(error="unauthorized"), 401
    with db() as c, c.cursor() as cur:
        cur.execute("SELECT * FROM lookup.patient WHERE patient_id=%s", (pid,))
        pt = cur.fetchone()
        if not pt:
            return jsonify(error="not found"), 404
        cur.execute("SELECT * FROM lookup.encounter WHERE patient_id=%s ORDER BY service_date DESC", (pid,))
        encs = cur.fetchall()
        cur.execute("SELECT * FROM lookup.test_result WHERE patient_id=%s ORDER BY test_date DESC", (pid,))
        tests = cur.fetchall()
    return app.response_class(_dump({"patient": pt, "encounters": encs, "tests": tests}),
                              mimetype="application/json")


@app.post("/api/sh/import")
def bulk_import():
    if not require_key():
        return jsonify(error="unauthorized"), 401
    body = request.get_json(force=True)
    source    = body.get("source", "unknown")
    rows      = body.get("rows", [])
    loaded_by = body.get("loaded_by", "appscript")

    ins_p = ins_e = ins_t = 0
    with db() as c, c.cursor() as cur:
        cur.execute(
            "INSERT INTO lookup.import_batch(source_name,row_count,loaded_by) VALUES (%s,%s,%s) RETURNING batch_id",
            (source, len(rows), loaded_by))
        batch_id = cur.fetchone()["batch_id"]

        for r in rows:
            member = (r.get("member_id") or "").strip()
            last   = (r.get("last_name") or "").strip()
            first  = (r.get("first_name") or "").strip()
            dob    = parse_date(r.get("dob"))
            if not last and not first and not member:
                continue

            if member:
                cur.execute("""
                    INSERT INTO lookup.patient(member_id,last_name,first_name,middle_name,dob,sex)
                    VALUES (%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (member_id) WHERE member_id IS NOT NULL AND member_id<>''
                    DO UPDATE SET last_name=EXCLUDED.last_name, first_name=EXCLUDED.first_name,
                                  dob=EXCLUDED.dob, updated_at=now()
                    RETURNING patient_id""",
                    (member, last, first, r.get("middle_name"), dob, (r.get("sex") or "")[:1] or None))
            else:
                cur.execute("""
                    INSERT INTO lookup.patient(last_name,first_name,middle_name,dob,sex)
                    VALUES (%s,%s,%s,%s,%s)
                    ON CONFLICT (lower(last_name),lower(first_name),dob)
                    WHERE member_id IS NULL OR member_id=''
                    DO UPDATE SET updated_at=now()
                    RETURNING patient_id""",
                    (last, first, r.get("middle_name"), dob, (r.get("sex") or "")[:1] or None))
            pid = cur.fetchone()["patient_id"]
            ins_p += 1

            dos = parse_date(r.get("service_date"))
            if dos or r.get("payer_name") or r.get("status"):
                cur.execute("""
                    INSERT INTO lookup.encounter(patient_id,service_date,payer_name,payer_id,
                        provider_npi,provider_name,status,notes,batch_id)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (patient_id,service_date,coalesce(payer_id,''),coalesce(provider_npi,''))
                    DO UPDATE SET status=EXCLUDED.status, notes=EXCLUDED.notes
                    RETURNING encounter_id""",
                    (pid, dos, r.get("payer_name"), r.get("payer_id"), r.get("provider_npi"),
                     r.get("provider_name"), r.get("status"), r.get("notes"), batch_id))
                eid = cur.fetchone()["encounter_id"]
                ins_e += 1

                if r.get("cpt_code") or r.get("test_name"):
                    cur.execute("""
                        INSERT INTO lookup.test_result(encounter_id,patient_id,test_date,
                            cpt_code,test_name,icd10_code,result_value,result_status,batch_id)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (eid, pid, parse_date(r.get("test_date")) or dos, r.get("cpt_code"),
                         r.get("test_name"), r.get("icd10_code"), r.get("result_value"),
                         r.get("result_status"), batch_id))
                    ins_t += 1
        c.commit()
    return jsonify(ok=True, batch_id=batch_id, patients=ins_p, encounters=ins_e, tests=ins_t)


@app.get("/api/sh/report")
def report():
    if not require_key():
        return jsonify(error="unauthorized"), 401
    rtype = request.args.get("type", "status")
    with db() as c, c.cursor() as cur:
        if rtype == "status":
            cur.execute("SELECT status, count(*) AS n FROM lookup.encounter GROUP BY status ORDER BY n DESC")
        elif rtype == "payer":
            cur.execute("SELECT payer_name, count(*) AS n FROM lookup.encounter GROUP BY payer_name ORDER BY n DESC")
        elif rtype == "dos_range":
            start = parse_date(request.args.get("start"))
            end   = parse_date(request.args.get("end"))
            cur.execute("""SELECT p.member_id,p.last_name,p.first_name,e.service_date,e.payer_name,e.status
                           FROM lookup.encounter e JOIN lookup.patient p USING(patient_id)
                           WHERE e.service_date BETWEEN %s AND %s ORDER BY e.service_date""", (start, end))
        elif rtype == "incomplete":
            cur.execute("""SELECT p.last_name,p.first_name,p.dob,e.status,e.notes
                           FROM lookup.encounter e JOIN lookup.patient p USING(patient_id)
                           WHERE e.status ILIKE '%%incomplete%%' OR e.status ILIKE '%%verify%%'""")
        else:
            return jsonify(error="unknown report type"), 400
        rows = cur.fetchall()
    return app.response_class(_dump({"type": rtype, "rows": rows}), mimetype="application/json")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
