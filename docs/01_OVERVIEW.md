# 01 Overview

## What it is
AIDAA (AI Driven Audit Assistant): audit planning, assignments (surat tugas), team and budget, execution (PKA, procedures,
working papers), findings, recommendations and reports, with AI suggestions that a human always decides.
It sits on Darkhive IAM and shares its PostgreSQL database (darkhivecore). The frontend is a separate repository.

## Requirements and run
- Python 3.10+, Windows with PowerShell 7. PostgreSQL with btree_gist and gen_random_uuid().
- IAM backend and tables in the same database, same JWT secret and algorithm.
- Run: run.ps1 (uvicorn app.main:app --reload --port 8002). API prefix /api/v1/aidaa.
  Or git_part_2\dev.ps1 at the parent folder: four tabs, IAM 8000, GrIMIS 8001, AIDAA 8002, FE 3000.
- Optional AI: local Ollama (engine OLLAMA) or Gemini (engine WEB_API).
- Frontend: Node 20+, port 3000, proxies /api/aidaa to this backend.

## Dependencies
FastAPI, uvicorn, SQLAlchemy 2 (raw SQL, no ORM models), psycopg2, Pydantic v2 (model_dump), python-jose, python-dotenv.
AI calls use urllib from the standard library (services/ai_engine.py). Versions are in requirements.txt (not reviewed).

## Settings (.env key names only, the AIDAA .env is its OWN file)
DH_DB_HOST, DH_DB_PORT, DH_DB_NAME, DH_DB_USER, DH_DB_PASSWORD, APP_PORT, JWT_SECRET_KEY (32+ chars), JWT_ALGORITHM,
JWT_EXPIRE_MINUTES, OLLAMA_URL, OLLAMA_MODEL (default gemma4:e4b), GEMINI_API_KEY, GEMINI_MODEL (default gemini-flash-latest),
AI_ENGINE (OLLAMA or WEB_API, default OLLAMA), AI_TIMEOUT (seconds, default 300). core/config.py reads them.
Keys set in the IAM or GrIMIS .env do not reach AIDAA.

## Glossary
- Root org: owner of an audit universe. There are MANY roots. Every AIDAA role is bound to an org under one root.
- Audit universe: active orgs under the root that can be audited.
- Auditable unit (ref_auditable_unit): an IAM org tagged as audit object, ONE location, one tag per org.
- Internal Audit Unit (IAU): org set in aidaa_core.audit_setting (one row per root, set by AIDAA.ADMIN). Its subtree is the
  pool auditors come from, and it cannot be tagged as an auditable unit.
- Owner org: owner_org_id of a plan or an unplanned assignment, inside the IAU subtree.
- Audit team: auditors picked from the IAU for ONE assignment (assignment_member).
- Location (ref_location): country, province, city, address. Province rates sit on locations with city NULL, coded PROV-<ISO>.
  City rates use codes CITY-<NAME>.
- SBM: Standar Biaya Masukan, the yearly Kemenkeu unit-cost regulation. Amounts are ceilings, treated as reference, never a block.
- PKA: Program Kerja Audit (work program). Procedure: one step of a PKA. Surat tugas: the assignment document.
- Audit day: 8 work hours. Person-days = procedure hours / 8.
- Assignment roles (per audit, never in IAM): supervisor, leader, member.
- IAM roles: AIDAA.ADMIN, BOARD, HEAD_AUDIT, AUDITOR, HR, FINANCE, GENERAL_AFFAIRS, AUDITEE_PIC.