-- ============================================================================
-- Sally Health — Local PostgreSQL schema
-- EHR · eligibility · demographics · LIS · billing · coding · claims
-- ----------------------------------------------------------------------------
-- Target: PostgreSQL 14+ running locally, managed via DataGrip.
-- Run this whole file once against a fresh database.
--
--   In DataGrip:  open this file → select your Postgres data source →
--                 Execute (the whole script). Or from a shell:
--                 createdb sally_health
--                 psql sally_health -f sally_health_schema.sql
--
-- Design notes:
--   * All PHI-bearing tables use surrogate UUID PKs.
--   * Raw payloads (271 eligibility, 835 remits, lab results, card OCR) are
--     kept verbatim in jsonb columns — load messy source as-is, query later.
--   * stg_* staging tables accept raw text first; you validate and promote
--     into clean tables rather than failing an import on one bad row.
--   * Reference data (entities, providers, payers, CPT, ICD-10) is seeded so
--     fixed identifiers (CLIA/EIN/NPI) live in tables, never hardcoded.
--   * CPT/ICD-10 foreign keys block invalid codes from entering charges/dx.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 0. Extensions
-- ----------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";     -- uuid_generate_v4()
CREATE EXTENSION IF NOT EXISTS pgcrypto;        -- PHI column encryption (pgp_sym_*)
CREATE EXTENSION IF NOT EXISTS pg_trgm;         -- fuzzy patient matching (similarity)
CREATE EXTENSION IF NOT EXISTS fuzzystrmatch;   -- soundex / levenshtein matching

-- ----------------------------------------------------------------------------
-- 1. Schemas (logical separation; everything is one database)
-- ----------------------------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS ref;     -- reference / lookup data
CREATE SCHEMA IF NOT EXISTS core;    -- patients, coverage, encounters, dx
CREATE SCHEMA IF NOT EXISTS lis;     -- lab orders & results
CREATE SCHEMA IF NOT EXISTS billing; -- charges, claims, remits
CREATE SCHEMA IF NOT EXISTS stg;     -- raw spreadsheet/CSV landing zone

-- ============================================================================
-- 2. REFERENCE / LOOKUP
-- ============================================================================

-- Legal entities you operate or bill under.
CREATE TABLE ref.entities (
    entity_id     uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    name          text NOT NULL,
    npi           varchar(10),
    clia          varchar(20),
    ein           varchar(20),
    tax_id        varchar(20),
    uei           varchar(20),
    address_line  text,
    city          text,
    state         varchar(2),
    zip           varchar(10),
    notes         text,
    created_at    timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE ref.entities IS 'Billing/operating entities. Fixed identifiers live here, not in code.';

-- Rendering / referring providers.
CREATE TABLE ref.providers (
    provider_id   uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    npi           varchar(10) UNIQUE NOT NULL,
    last_name     text NOT NULL,
    first_name    text,
    credential    text,
    entity_id     uuid REFERENCES ref.entities(entity_id),
    active        boolean NOT NULL DEFAULT true
);

-- Payers, with the Claim.MD payer id mapping you normalize against.
CREATE TABLE ref.payers (
    payer_id          uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    name              text NOT NULL,
    claim_md_payer_id varchar(20),     -- clearinghouse payer id
    payer_type        text,            -- 'commercial' | 'medicare' | 'medicaid' | ...
    active            boolean NOT NULL DEFAULT true
);
CREATE INDEX idx_payers_claimmd ON ref.payers(claim_md_payer_id);

-- CPT / HCPCS procedure codes for coding validation.
CREATE TABLE ref.cpt_codes (
    cpt           varchar(5) PRIMARY KEY,
    description   text,
    active        boolean NOT NULL DEFAULT true
);

-- ICD-10-CM diagnosis codes for coding validation.
CREATE TABLE ref.icd10_codes (
    icd10         varchar(10) PRIMARY KEY,   -- store with decimal, e.g. 'E11.9'
    description   text,
    billable      boolean NOT NULL DEFAULT true
);

-- ============================================================================
-- 3. CORE — patients, coverage, encounters, diagnoses
-- ============================================================================

CREATE TABLE core.patients (
    patient_id    uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    mrn           text UNIQUE,                 -- your internal medical record number
    last_name     text NOT NULL,
    first_name    text NOT NULL,
    middle_name   text,
    dob           date,
    sex           varchar(1),                  -- 'M' | 'F' | 'U'
    ssn_enc       bytea,                       -- encrypted via pgcrypto; never plaintext
    address_line  text,
    city          text,
    state         varchar(2),
    zip           varchar(10),
    phone         varchar(20),
    email         text,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now()
);
-- Trigram index supports fuzzy de-duplication across messy source files.
CREATE INDEX idx_patients_name_trgm
    ON core.patients USING gin ((last_name || ' ' || first_name) gin_trgm_ops);
CREATE INDEX idx_patients_dob ON core.patients(dob);

COMMENT ON COLUMN core.patients.ssn_enc IS
  'Encrypt on write:  pgp_sym_encrypt(ssn_text, :key).  Decrypt on read:  pgp_sym_decrypt(ssn_enc, :key).';

CREATE TABLE core.coverage (
    coverage_id        uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    patient_id         uuid NOT NULL REFERENCES core.patients(patient_id) ON DELETE CASCADE,
    payer_id           uuid REFERENCES ref.payers(payer_id),
    rank               smallint NOT NULL DEFAULT 1,   -- 1=primary, 2=secondary
    member_id          text,
    group_no           text,
    plan_name          text,
    eligibility_status text,                           -- 'active' | 'inactive' | 'unknown'
    verified_at        timestamptz,
    raw_271            jsonb,                           -- full eligibility response, verbatim
    card_ocr           jsonb,                           -- insurance card OCR output, verbatim
    created_at         timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_coverage_patient ON core.coverage(patient_id);
CREATE INDEX idx_coverage_raw271 ON core.coverage USING gin (raw_271);

CREATE TABLE core.encounters (
    encounter_id      uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    patient_id        uuid NOT NULL REFERENCES core.patients(patient_id),
    provider_id       uuid REFERENCES ref.providers(provider_id),
    entity_id         uuid REFERENCES ref.entities(entity_id),  -- which entity is billing
    dos               date NOT NULL,                            -- date of service
    place_of_service  varchar(2),                               -- POS code, e.g. '11','81'
    notes             text,
    created_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_encounters_patient ON core.encounters(patient_id);
CREATE INDEX idx_encounters_dos ON core.encounters(dos);

CREATE TABLE core.diagnoses (
    dx_id         uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    encounter_id  uuid NOT NULL REFERENCES core.encounters(encounter_id) ON DELETE CASCADE,
    icd10         varchar(10) NOT NULL REFERENCES ref.icd10_codes(icd10),
    pointer       smallint,                  -- A/B/C/D ordering -> 1/2/3/4
    UNIQUE (encounter_id, icd10)
);

-- ============================================================================
-- 4. LIS — lab orders & results
-- ============================================================================

CREATE TABLE lis.lab_orders (
    order_id      uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    encounter_id  uuid REFERENCES core.encounters(encounter_id),
    patient_id    uuid NOT NULL REFERENCES core.patients(patient_id),
    accession     text,                       -- lab accession / requisition number
    ordered_at    timestamptz,
    status        text,                       -- 'ordered'|'collected'|'resulted'|'cancelled'
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_laborders_patient ON lis.lab_orders(patient_id);
CREATE INDEX idx_laborders_accession ON lis.lab_orders(accession);

CREATE TABLE lis.lab_results (
    result_id     uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    order_id      uuid NOT NULL REFERENCES lis.lab_orders(order_id) ON DELETE CASCADE,
    analyte       text NOT NULL,
    value         text,
    units         text,
    ref_range     text,
    abnormal_flag text,                       -- 'H'|'L'|'A'|null
    resulted_at   timestamptz,
    raw           jsonb,                       -- full result payload (HL7/JSON), verbatim
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_labresults_order ON lis.lab_results(order_id);

-- ============================================================================
-- 5. BILLING — charges, claims, claim lines, remits
-- ============================================================================

CREATE TABLE billing.charges (
    charge_id     uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    encounter_id  uuid NOT NULL REFERENCES core.encounters(encounter_id) ON DELETE CASCADE,
    cpt           varchar(5) NOT NULL REFERENCES ref.cpt_codes(cpt),
    modifier1     varchar(2),
    modifier2     varchar(2),
    units         numeric(7,2) NOT NULL DEFAULT 1,
    charge_amt    numeric(10,2) NOT NULL DEFAULT 0,
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_charges_encounter ON billing.charges(encounter_id);

-- Links each charge line to the diagnoses that justify it (dx pointers).
CREATE TABLE billing.charge_dx (
    charge_id     uuid NOT NULL REFERENCES billing.charges(charge_id) ON DELETE CASCADE,
    dx_id         uuid NOT NULL REFERENCES core.diagnoses(dx_id) ON DELETE CASCADE,
    PRIMARY KEY (charge_id, dx_id)
);

CREATE TABLE billing.claims (
    claim_id      uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    encounter_id  uuid NOT NULL REFERENCES core.encounters(encounter_id),
    payer_id      uuid REFERENCES ref.payers(payer_id),
    status        text NOT NULL DEFAULT 'draft',  -- draft|submitted|accepted|rejected|paid|denied
    claim_md_id   text,                            -- clearinghouse claim id
    total_charge  numeric(10,2),
    submitted_at  timestamptz,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_claims_encounter ON billing.claims(encounter_id);
CREATE INDEX idx_claims_status ON billing.claims(status);
CREATE INDEX idx_claims_claimmd ON billing.claims(claim_md_id);

CREATE TABLE billing.claim_lines (
    claim_id      uuid NOT NULL REFERENCES billing.claims(claim_id) ON DELETE CASCADE,
    charge_id     uuid NOT NULL REFERENCES billing.charges(charge_id),
    PRIMARY KEY (claim_id, charge_id)
);

CREATE TABLE billing.remits (
    era_id           uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    claim_id         uuid REFERENCES billing.claims(claim_id),
    paid_amt         numeric(10,2),
    patient_resp     numeric(10,2),
    adjustment_codes text,                  -- CARC/RARC summary
    check_eft        text,                  -- check / EFT trace number
    posted_at        timestamptz,
    raw_835          jsonb,                  -- full ERA/835 payload, verbatim
    created_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_remits_claim ON billing.remits(claim_id);

-- ============================================================================
-- 6. STAGING — raw spreadsheet / CSV landing zone (all text, no constraints)
-- ----------------------------------------------------------------------------
-- Import messy files here first (DataGrip: right-click table -> Import Data
-- from File). Then run validate-and-promote queries (section 8) into clean
-- tables. Keeps one bad row from failing an entire import.
-- ============================================================================

CREATE TABLE stg.labcorp_invoice (
    batch_id      text,
    raw_row       jsonb,           -- optionally keep the whole row as json too
    patient_last  text,
    patient_first text,
    dob           text,
    sex           text,
    member_id     text,
    payer_name    text,
    accession     text,
    dos           text,
    cpt           text,
    icd10         text,
    charge_amt    text,
    loaded_at     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE stg.eligibility (
    raw_row            jsonb,
    patient_last       text,
    patient_first      text,
    dob                text,
    member_id          text,
    payer_name         text,
    claim_md_payer_id  text,
    eligibility_status text,
    response_271       text,        -- raw 271 text/json, promoted to coverage.raw_271
    loaded_at          timestamptz NOT NULL DEFAULT now()
);

-- ============================================================================
-- 7. SEED DATA — known fixed identifiers
-- ----------------------------------------------------------------------------
-- Verify every value against your own records before relying on claims output.
-- ============================================================================

INSERT INTO ref.entities (name, npi, clia, ein, tax_id, uei, city, state) VALUES
  ('Sally Health & Innovative Partners LLC', '1174346415', '14D2332885', '920253967', '331399385', 'R5ADHS4PFJX3', 'Matteson', 'IL'),
  ('Miamar Health Clinic PLLC',              '1992494066', NULL, NULL, NULL, NULL, NULL, NULL),
  ('Serenity Choice Health',                 '1538057138', NULL, NULL, NULL, NULL, NULL, NULL),
  ('Lab Express Corporation',                '1891062287', NULL, NULL, NULL, NULL, NULL, NULL)
ON CONFLICT DO NOTHING;

-- Providers (entity_id left null here; link them after verifying associations).
INSERT INTO ref.providers (npi, last_name, first_name, credential) VALUES
  ('1174346415', 'Amu',                'I.',   NULL),
  ('1356714943', 'Olagbegi',           'B.',   NULL),
  ('1134766132', 'Hawkins',            'C.',   NULL),
  ('1871893859', 'Jain',               'Anuj', NULL)
ON CONFLICT (npi) DO NOTHING;

-- ============================================================================
-- 8. VALIDATE-AND-PROMOTE PATTERNS (run AFTER importing into stg.*)
-- ----------------------------------------------------------------------------
-- These are templates, not auto-run. Copy into a DataGrip console, inspect the
-- SELECT first, then run the INSERT. Adjust column parsing to your file format.
-- ============================================================================

/*  --- 8a. Inspect rows that would FAIL validation before promoting ---
SELECT *
FROM stg.labcorp_invoice s
WHERE NOT EXISTS (SELECT 1 FROM ref.cpt_codes   c WHERE c.cpt   = s.cpt)
   OR NOT EXISTS (SELECT 1 FROM ref.icd10_codes d WHERE d.icd10 = s.icd10)
   OR to_date(NULLIF(s.dos,''), 'MM/DD/YYYY') IS NULL;
*/

/*  --- 8b. Promote NEW patients from staging (fuzzy-dedupe by name+dob) ---
INSERT INTO core.patients (last_name, first_name, dob, sex)
SELECT DISTINCT s.patient_last, s.patient_first,
       to_date(NULLIF(s.dob,''), 'MM/DD/YYYY'), NULLIF(s.sex,'')
FROM stg.labcorp_invoice s
WHERE NOT EXISTS (
    SELECT 1 FROM core.patients p
    WHERE p.dob = to_date(NULLIF(s.dob,''), 'MM/DD/YYYY')
      AND similarity(p.last_name || ' ' || p.first_name,
                     s.patient_last || ' ' || s.patient_first) > 0.6
);
*/

/*  --- 8c. Find likely duplicate patients already in core (review manually) ---
SELECT a.patient_id, b.patient_id,
       a.last_name, a.first_name, a.dob,
       similarity(a.last_name||' '||a.first_name, b.last_name||' '||b.first_name) AS score
FROM core.patients a
JOIN core.patients b
  ON a.patient_id < b.patient_id
 AND a.dob = b.dob
 AND similarity(a.last_name||' '||a.first_name, b.last_name||' '||b.first_name) > 0.6
ORDER BY score DESC;
*/

/*  --- 8d. Encrypt an SSN on write / decrypt on read (pgcrypto) ---
-- write:
UPDATE core.patients
   SET ssn_enc = pgp_sym_encrypt('123456789', 'YOUR_SECRET_KEY')
 WHERE patient_id = '...';
-- read:
SELECT pgp_sym_decrypt(ssn_enc, 'YOUR_SECRET_KEY') FROM core.patients WHERE patient_id = '...';
*/

-- ============================================================================
-- 9. CONVENIENCE VIEW — claim-ready line items (CMS-1500 shape)
-- ============================================================================
CREATE OR REPLACE VIEW billing.v_claim_lines AS
SELECT
    cm.claim_id,
    cm.status                AS claim_status,
    p.last_name, p.first_name, p.dob,
    pr.npi                   AS rendering_npi,
    e.dos, e.place_of_service,
    ch.cpt, ch.modifier1, ch.modifier2, ch.units, ch.charge_amt,
    string_agg(d.icd10, ',' ORDER BY d.pointer) AS dx_codes,
    py.name                  AS payer_name,
    py.claim_md_payer_id
FROM billing.claims cm
JOIN billing.claim_lines clx ON clx.claim_id = cm.claim_id
JOIN billing.charges ch      ON ch.charge_id = clx.charge_id
JOIN core.encounters e       ON e.encounter_id = ch.encounter_id
JOIN core.patients p         ON p.patient_id = e.patient_id
LEFT JOIN ref.providers pr   ON pr.provider_id = e.provider_id
LEFT JOIN ref.payers py      ON py.payer_id = cm.payer_id
LEFT JOIN billing.charge_dx cdx ON cdx.charge_id = ch.charge_id
LEFT JOIN core.diagnoses d   ON d.dx_id = cdx.dx_id
GROUP BY cm.claim_id, cm.status, p.last_name, p.first_name, p.dob,
         pr.npi, e.dos, e.place_of_service, ch.cpt, ch.modifier1,
         ch.modifier2, ch.units, ch.charge_amt, py.name, py.claim_md_payer_id;

-- ============================================================================
-- End of schema.  Next steps:
--   1. Load CPT/ICD-10 reference data into ref.cpt_codes / ref.icd10_codes.
--   2. Import a Labcorp batch into stg.labcorp_invoice (DataGrip import wizard).
--   3. Run the section-8 SELECTs to inspect, then promote.
--   4. Enable macOS FileVault before entering real PHI; schedule pg_dump backups.
-- ============================================================================
