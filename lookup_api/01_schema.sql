-- ============================================================
-- Sally Health — Patient Lookup Backend
-- Schema: lookup   (lives in the sallyhealth DB on vm-01)
-- ============================================================
-- Design:
--   patient        : one row per unique person (dedup key: member_id, else name+dob)
--   encounter      : one row per DOS / claim line (many per patient)
--   test_result    : tests performed at an encounter (many per encounter)
--   import_batch   : provenance — which uploaded sheet a row came from
-- ============================================================

CREATE SCHEMA IF NOT EXISTS lookup;
SET search_path TO lookup, public;

CREATE TABLE IF NOT EXISTS import_batch (
    batch_id      BIGSERIAL PRIMARY KEY,
    source_name   TEXT NOT NULL,
    row_count     INT,
    loaded_at     TIMESTAMPTZ DEFAULT now(),
    loaded_by     TEXT
);

CREATE TABLE IF NOT EXISTS patient (
    patient_id    BIGSERIAL PRIMARY KEY,
    member_id     TEXT,
    last_name     TEXT NOT NULL,
    first_name    TEXT NOT NULL,
    middle_name   TEXT,
    dob           DATE,
    sex           CHAR(1),
    created_at    TIMESTAMPTZ DEFAULT now(),
    updated_at    TIMESTAMPTZ DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_patient_member
    ON patient (member_id) WHERE member_id IS NOT NULL AND member_id <> '';
CREATE UNIQUE INDEX IF NOT EXISTS ux_patient_name_dob
    ON patient (lower(last_name), lower(first_name), dob)
    WHERE member_id IS NULL OR member_id = '';

CREATE INDEX IF NOT EXISTS ix_patient_last  ON patient (lower(last_name));
CREATE INDEX IF NOT EXISTS ix_patient_first ON patient (lower(first_name));
CREATE INDEX IF NOT EXISTS ix_patient_dob   ON patient (dob);

CREATE TABLE IF NOT EXISTS encounter (
    encounter_id  BIGSERIAL PRIMARY KEY,
    patient_id    BIGINT NOT NULL REFERENCES patient(patient_id) ON DELETE CASCADE,
    service_date  DATE,
    payer_name    TEXT,
    payer_id      TEXT,
    provider_npi  TEXT,
    provider_name TEXT,
    status        TEXT,
    notes         TEXT,
    batch_id      BIGINT REFERENCES import_batch(batch_id),
    created_at    TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_enc_patient ON encounter (patient_id);
CREATE INDEX IF NOT EXISTS ix_enc_dos     ON encounter (service_date);
CREATE UNIQUE INDEX IF NOT EXISTS ux_enc_dedup
    ON encounter (patient_id, service_date, coalesce(payer_id,''), coalesce(provider_npi,''));

CREATE TABLE IF NOT EXISTS test_result (
    test_id       BIGSERIAL PRIMARY KEY,
    encounter_id  BIGINT NOT NULL REFERENCES encounter(encounter_id) ON DELETE CASCADE,
    patient_id    BIGINT NOT NULL REFERENCES patient(patient_id) ON DELETE CASCADE,
    test_date     DATE,
    cpt_code      TEXT,
    test_name     TEXT,
    icd10_code    TEXT,
    result_value  TEXT,
    result_status TEXT,
    batch_id      BIGINT REFERENCES import_batch(batch_id),
    created_at    TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_test_patient ON test_result (patient_id);
CREATE INDEX IF NOT EXISTS ix_test_enc     ON test_result (encounter_id);
CREATE INDEX IF NOT EXISTS ix_test_cpt     ON test_result (cpt_code);

CREATE OR REPLACE VIEW lookup.v_patient_summary AS
SELECT
    p.patient_id, p.member_id, p.last_name, p.first_name, p.middle_name,
    p.dob, p.sex,
    max(e.service_date)               AS last_dos,
    count(DISTINCT e.encounter_id)    AS encounter_count,
    count(DISTINCT t.test_id)         AS test_count
FROM patient p
LEFT JOIN encounter   e ON e.patient_id = p.patient_id
LEFT JOIN test_result t ON t.patient_id = p.patient_id
GROUP BY p.patient_id;

-- Run once as superuser to create role:
-- CREATE ROLE izzy WITH LOGIN PASSWORD 'your-strong-password';
-- GRANT CONNECT ON DATABASE sallyhealth TO izzy;
-- GRANT USAGE ON SCHEMA lookup TO izzy;
-- GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA lookup TO izzy;
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA lookup TO izzy;
-- ALTER DEFAULT PRIVILEGES IN SCHEMA lookup GRANT SELECT, INSERT, UPDATE ON TABLES TO izzy;
-- ALTER DEFAULT PRIVILEGES IN SCHEMA lookup GRANT USAGE, SELECT ON SEQUENCES TO izzy;
