# AIDAA - AI Driven Audit Assistant (backend)

Sits on Darkhive IAM. Do NOT modify IAM. Same PostgreSQL database as IAM.
Stack: Python, FastAPI, SQLAlchemy raw SQL via text(), psycopg2, python-jose. Port 8002.
Auth: use the IAM token (same JWT_SECRET_KEY/JWT_ALGORITHM), check iam.revoked_tokens.
Permissions: code format modul.aksi, lowercase, dotted (example: audit.plan.read).
Only references to IAM: org_id and user_id. No other foreign keys out of iam.

## Reference folder (read-only)
Files in reference/ are read-only examples, never edit them.
- 01_iam.sql: exact IAM table and column names.
- dependencies.py, security, database (from grimis-bev2): copy these patterns for
  require_permission, check_org_permission, log_audit, JWT and DB connection.
- READMEs: IAM and GrIMIS logic.
Never read or create .env files.

## Schemas
- aidaa_core: ref_auditable_unit, ref_audit_type, ref_cost_standard, auditor, expertise,
  expertise_document, library_pka, library_procedure, audit_plan, assignment,
  assignment_member, budget_line, pka, exe_procedure, working_paper, finding, rekomend,
  audit_report, approval_step, approval_task
- aidaa_log (append-only, never update/delete): team_log, approval_log, edit_log,
  comment_log, status_log (has by_ai flag)

## Rules
- audit_plan status: planned, approved, ai_planned, ai_approved, finished.
- Approval chain: team leader drafts -> finance verifies budget -> supervisor reviews -> head approves.
- Nobody approves their own work.
- One person = one role per assignment (unique person per assignment).
  The same person may hold different roles in different audits.
- Conflict of interest (hard block): an auditor cannot be assigned to an audit if the
  auditor's own org is the audited unit or a child unit of it (an audit of a unit covers
  its child units). Walk the IAM org tree. Log blocked attempts in team_log.
- expertise starts pending; only counts after HR sets verified.
- Auditee PIC sees only the assignment of their own unit.
- Rekomend stays open until resolved; monitored beyond the audit end.

## Roles
administrator, head audit unit, audit supervisor, audit team leader, audit team member,
auditee person in charge, audit unit HR, audit unit Finance, audit unit General Affairs.

## Working style
One small task at a time. Show the plan first. Never touch files outside this folder.
When editing a file, change only the lines needed, never replace the whole file.