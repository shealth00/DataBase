-- ============================================================================
-- Sally Health — SQLite patient mirror
-- Portable local DB for monitoring + Google Drive sheet → SQL conversion.
-- Open in DataGrip as a SQLite data source, or rebuild with:
--   python3 build_sqlite_db.py
-- ============================================================================

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Core patient demographics (aligned with Postgres core.patients)
CREATE TABLE IF NOT EXISTS patients (
    patient_id    TEXT PRIMARY KEY,           -- uuid string
    mrn           TEXT UNIQUE,
    last_name     TEXT NOT NULL,
    first_name    TEXT NOT NULL,
    middle_name   TEXT,
    dob           TEXT,                       -- ISO date YYYY-MM-DD
    sex           TEXT,                       -- M|F|U|
    address_line  TEXT,
    city          TEXT,
    state         TEXT,
    zip           TEXT,
    phone         TEXT,
    email         TEXT,
    insurance     TEXT,
    member_id     TEXT,
    status        TEXT,
    facility      TEXT,
    physician     TEXT,
    physician_npi TEXT,
    source        TEXT,                       -- BHI_CCM | CCD | ClaimMD | sheet:...
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_patients_dob ON patients(dob);
CREATE INDEX IF NOT EXISTS idx_patients_name ON patients(last_name, first_name);
CREATE INDEX IF NOT EXISTS idx_patients_source ON patients(source);

CREATE TABLE IF NOT EXISTS patient_programs (
    mrn      TEXT NOT NULL,
    program  TEXT NOT NULL,                   -- BHI | CCM | RPM
    PRIMARY KEY (mrn, program),
    FOREIGN KEY (mrn) REFERENCES patients(mrn) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS patient_dx (
    mrn    TEXT NOT NULL,
    icd10  TEXT NOT NULL,
    PRIMARY KEY (mrn, icd10),
    FOREIGN KEY (mrn) REFERENCES patients(mrn) ON DELETE CASCADE
);

-- Raw Google Drive / spreadsheet landing zone (all text)
CREATE TABLE IF NOT EXISTS stg_sheets (
    row_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id      TEXT NOT NULL,
    source_file   TEXT NOT NULL,
    sheet_name    TEXT,
    drive_file_id TEXT,
    row_num       INTEGER,
    raw_json      TEXT NOT NULL,              -- full row as JSON
    loaded_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_stg_sheets_batch ON stg_sheets(batch_id);
CREATE INDEX IF NOT EXISTS idx_stg_sheets_file ON stg_sheets(source_file);

-- BHI / CCM / RPM billable summary staging (column-aligned with ingest_bhi_ccm_rpm.py)
CREATE TABLE IF NOT EXISTS stg_bhi_ccm (
    row_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id        TEXT NOT NULL,
    source_file     TEXT NOT NULL,
    program         TEXT,                     -- BHI | CCM | RPM
    month_label     TEXT,
    first_name      TEXT,
    middle_name     TEXT,
    last_name       TEXT,
    mrn             TEXT,
    insurance_name  TEXT,
    member_id       TEXT,
    status          TEXT,
    dob             TEXT,
    facility        TEXT,
    physician_name  TEXT,
    physician_npi   TEXT,
    cpt_code        TEXT,
    service_type    TEXT,
    dx1 TEXT, dx2 TEXT, dx3 TEXT, dx4 TEXT, dx5 TEXT,
    dx6 TEXT, dx7 TEXT, dx8 TEXT, dx9 TEXT, dx10 TEXT,
    raw_json        TEXT,
    loaded_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_stg_bhi_mrn ON stg_bhi_ccm(mrn);

-- Import audit log for monitoring
CREATE TABLE IF NOT EXISTS import_runs (
    run_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at    TEXT NOT NULL DEFAULT (datetime('now')),
    finished_at   TEXT,
    source        TEXT NOT NULL,              -- json_seed | local_sheet | google_drive
    files_seen    INTEGER NOT NULL DEFAULT 0,
    rows_loaded   INTEGER NOT NULL DEFAULT 0,
    patients_upserted INTEGER NOT NULL DEFAULT 0,
    status        TEXT NOT NULL DEFAULT 'running',  -- running|ok|error
    message       TEXT
);

CREATE VIEW IF NOT EXISTS v_patient_summary AS
SELECT
    p.mrn,
    p.first_name,
    p.last_name,
    p.dob,
    p.sex,
    p.insurance,
    p.status,
    p.facility,
    p.source,
    GROUP_CONCAT(DISTINCT pp.program) AS programs,
    GROUP_CONCAT(DISTINCT pd.icd10) AS dx_codes
FROM patients p
LEFT JOIN patient_programs pp ON pp.mrn = p.mrn
LEFT JOIN patient_dx pd ON pd.mrn = p.mrn
GROUP BY p.mrn;
