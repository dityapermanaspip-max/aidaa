# 1. Overview

## Description
AIDAA (AI Driven Audit Assistant) is the audit application of the Darkhive platform: audit planning, assignments (surat tugas),
team and budget, execution (PKA, procedures, working papers), findings, recommendations and reports, with AI suggestions that
a human always decides. It sits on Darkhive IAM and shares its PostgreSQL database. Do NOT modify IAM.
The frontend is a separate repository (Next.js, see its README and docs/).

## System requirements
- Python 3.10 or newer (the code uses `X | None` types), runs on Windows with PowerShell 7.
- PostgreSQL with the `btree_gist` extension (auditor schedule exclusion constraint) and `gen_random_uuid()`.
- The IAM backend and its tables in the same database (darkhivecore), same JWT secret and algorithm.
- Port 8002. Run with run.ps1 (uvicorn app.main:app --reload --port 8002). API prefix: /api/v1/aidaa.
- Optional AI: a local Ollama server (engine OLLAMA) or a Gemini API key (engine WEB_API).
- Frontend (separate repo): Node 20 or newer, port 3000, proxies /api/aidaa to this backend.

## Dependencies (Python)
FastAPI, uvicorn, SQLAlchemy 2 (raw SQL through text(), no ORM models), psycopg2, Pydantic v2 (model_dump is used),
python-jose (JWT decode), python-dotenv. AI calls use urllib from the standard library (services/ai_engine.py).
Exact versions are in requirements.txt (not reviewed). Settings come from .env, which AI helpers must never read or create.
New settings are announced in chat and added by the owner. The AIDAA .env is its OWN file, keys set in the IAM or GRIMIS .env
do not reach AIDAA.
Keys in use: DH_DB_HOST/PORT/NAME/USER/PASSWORD, APP_PORT, JWT_SECRET_KEY, JWT_ALGORITHM, JWT_EXPIRE_MINUTES, OLLAMA_URL,
GEMINI_API_KEY, GEMINI_MODEL (default gemini-flash-latest), AI_ENGINE (OLLAMA or WEB_API, default OLLAMA; CLOUD and GEMINI
are read as WEB_API), AI_TIMEOUT (seconds, default 300), OLLAMA_MODEL (default gemma4:e4b). core/config.py reads them.

## Conventions
All primary keys are uuid. Permission codes are `audit.<resource>.<action>`, lowercase and dotted (example audit.plan.approve).
Auth is the IAM token: the token's jti must not be in iam.revoked_tokens and its "tv" must equal iam.users.token_version.
Only foreign keys out of iam: org_id and user_id. AIDAA never writes to iam tables except iam.audit_log through log_audit.
There is no cleanup loop (IAM does that). Login is IAM only.
Engine names: the API and the FE use OLLAMA and WEB_API, the ai_suggestion.engine column stores ollama and cloud.
ref_cost_rate.grade is jsonb: a JSON array of grade codes, NULL or empty means every grade. Auditor grade stays free text.

## Database state (all done, never edit these files unless asked)
sql/aidaa_iam_permission.sql   app AIDAA, 8 IAM roles, audit.* permissions, role matrix
sql/aidaa_core_master.sql      master data (10 tables)
sql/aidaa_core_planning.sql    planning, budget, funding, schedule (13 tables)
sql/aidaa_log_approval.sql     aidaa_log (5 append-only tables) + approval_step, approval_task
sql/aidaa_ai.sql               aidaa_ai.ai_suggestion
sql/aidaa_execution.sql        pka, exe_procedure, working_paper, finding, finding_response, rekomend, audit_report,
                               v_plan_deviation, can_skip, skipped status
sql/aidaa_patch_01_audit_universe.sql  location address, audit_setting (IAU), one tag per org, audit_plan_unit and
                               assignment_unit link tables, audit.setting.* permissions
sql/aidaa_patch_02_library_ai.sql      feature 'library_draft' in the ai_suggestion CHECK, library_pka.ai_suggestion_id
sql/aidaa_patch_03_org_scope.sql       root_org_id on ref_location, ref_audit_type, ref_cost_component, ref_funding_source,
                               library_pka; codes unique per root; backfilled to the audit_setting root.
sql/aidaa_patch_04_rate_grade_jsonb.sql  ref_cost_rate.grade varchar to jsonb array (old text becomes a one-item list),
                               CHECK ck_rate_grade_array. Applied as a one-liner in psql.
sql/aidaa_patch_05_sbm_draft.sql       feature 'sbm_draft' in the ai_suggestion CHECK. Applied as a one-liner in psql.
                               Later changes go in aidaa_patch_06_..., never edit the files above.
(Save the two one-liners of patch 04 and 05 into those files so the repository matches the database.)
sql/seed_sbm_2027.sql          TEMPLATE for the yearly SBM seed for ONE root organisation. A seed is data, not a patch.
sql/seed_sbm_2026.sql          TRIAL seed (lodging, Lampiran I No. 30, 38 provinces x 4 grades = 152 rates, root org code
                               PDGRPT, rates 2026-01-01 to 2026-12-31, status approved). Amounts NOT checked against the PMK.
                               It ran once: 1 component, 38 locations, 152 rates. Real data comes through the SBM AI helper.
Notes: audit_plan.owner_org_id and assignment.owner_org_id were added after the planning file (NOT NULL).
There is no audit.funding.* permission, funding reuses audit.coststd.*. library_pka.default_hours is LEGACY (unused).
ref_location.parent_location_id and is_branch_office are LEGACY (unused).

## Glossary and org model (English terms are canonical, UI labels may stay Indonesian)
- Root org: the owner of the audit universe. There are MANY root orgs. Every AIDAA role is bound to an org under one root.
- Organisation scope: master data (locations, audit types, cost components, funding sources, PKA library) and the cost rates
  under a component belong to ONE root org (root_org_id), codes are unique per root. A caller sees only their root, taken
  from get_root(db, user_id). Another root's record answers 404. Seeds must name their root by org code, never read
  audit_setting (it has one row per root).
- Audit universe: all active orgs under the root that can be audited.
- Auditable unit (ref_auditable_unit): an IAM org tagged as an audit object, ONE location, one tag per org.
- Internal Audit Unit (IAU): the org designated in aidaa_core.audit_setting (one row per root, set by AIDAA.ADMIN only).
  Its subtree is the POOL auditors come from and it cannot be tagged as auditable units.
- Audit team: the auditors picked from the IAU for ONE assignment (assignment_member rows).
- Owner org: owner_org_id of a plan or an unplanned assignment, an active org inside the IAU subtree.
- Location (ref_location): an address (country, province, city). SBM rates sit on province-level locations (city NULL),
  coded PROV-<ISO suffix>, and cover every place in that province.
- SBM: Standar Biaya Masukan, the yearly Kemenkeu regulation of unit costs. Amounts are ceilings for budgeting. AIDAA treats
  them as reference: lines above them are flagged with a reason, never blocked.
- Audit day: 8 work hours. Person-days = procedure hours / 8.
- PKA: Program Kerja Audit (audit work program). Procedure: one step of a PKA. Surat tugas: the assignment document.
- Assignment roles (per audit, only in assignment_member / audit_plan_member, never in IAM): supervisor, leader, member.
- IAM global roles: AIDAA.ADMIN, BOARD, HEAD_AUDIT, AUDITOR, HR, FINANCE, GENERAL_AFFAIRS, AUDITEE_PIC.