# Sally Health — Patient Records Database

Local **DataGrip / PostgreSQL** schema plus a **SQLite mirror** for monitoring and
converting Google Drive spreadsheets into SQL.

## Quick start (SQLite mirror)

```bash
python3 build_sqlite_db.py          # loads all_patients_merged.json → data/sally_health.db
python3 monitor_patients.py         # health report → reports/latest_monitor.json
```

Open `data/sally_health.db` in DataGrip as a SQLite data source, or load the
Postgres dump:

```bash
createdb sally_health
psql sally_health -f sally_health_schema.sql
psql sally_health -f sql/patients_seed_postgres.sql
```

## Google Drive sheets → SQL (via SQLite)

1. Export or sync sheets into `imports/` (`.xlsx` / `.csv` / `.tsv`), **or**
2. Place Drive API credentials at `secrets/google_credentials.json` and run:

```bash
python3 sheets_to_sqlite.py --drive --folder-id "$GOOGLE_DRIVE_FOLDER_ID" --promote
# local-only:
python3 sheets_to_sqlite.py --imports ./imports --promote
```

This stages rows into SQLite `stg_sheets` / `stg_bhi_ccm`, upserts patients when
`--promote` is set, and writes Postgres-ready `sql/stg_<batch>.sql` for DataGrip.

Optional dependency for Excel: `pip install openpyxl`  
Drive API: `pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib`

## Monitor (hourly automation)

```bash
python3 run_hourly.py                   # build → sheets → monitor
python3 run_hourly.py --drive           # also try Drive API sync
python3 monitor_patients.py --postgres  # needs DATABASE_URL or PG* env
```

Checks: patient counts by source, DOB/sex completeness, name+DOB duplicates,
import run failures, Drive/import readiness, and SQLite↔Postgres drift.

Fixture (sheets→SQL smoke test):

```bash
python3 sheets_to_sqlite.py \
  --file fixtures/BHI_SAMPLE_Billable_Summary_Report.csv \
  --batch-id fixture_bhi_sample --promote
```

## Layout

| Path | Role |
|------|------|
| `sally_health_schema.sql` | Postgres schema (DataGrip) |
| `sqlite_schema.sql` | SQLite mirror schema |
| `build_sqlite_db.py` | JSON → SQLite + SQL seed export |
| `sheets_to_sqlite.py` | Drive/local sheets → SQLite → SQL |
| `monitor_patients.py` | Patient DB health monitor |
| `imports/` | Drop Drive exports here |
| `sql/` | Generated Postgres seeds / staging SQL |
| `data/sally_health.db` | Local SQLite DB (gitignored) |
| `all_patients_merged.json` | Canonical 236-patient merge |

## DataGrip

1. Postgres data source → run `sally_health_schema.sql`
2. Optional SQLite data source → `data/sally_health.db`
3. After sheet conversion, execute `sql/stg_*.sql` then section **8e** promote queries
