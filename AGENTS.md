# AIDAA - AI Driven Audit Assistant (backend)

Sits on Darkhive IAM. Do NOT modify IAM. Same PostgreSQL database as IAM (darkhivecore).
Stack: Python, FastAPI, SQLAlchemy raw SQL via text(), psycopg2, python-jose. Port 8002.
All primary keys are uuid (gen_random_uuid()), same as IAM and GrIMIS.
Auth: use the IAM token (same JWT_SECRET_KEY/JWT_ALGORITHM), check iam.revoked_tokens.
Permissions: code format audit.modul.aksi style, lowercase, dotted (example: audit.plan.read).
Only foreign keys out of iam: org_id and user_id. No other references into iam.

## Reference folder (read-only)
Files in reference/ are read-only examples, never edit them.
- 01_iam.sql: exact IAM table and column names.
- dependencies.py, security, database (from grimis-bev2): copy these patterns for
  require_permission, check_org_permission, log_audit, JWT and DB connection.
- READMEs: IAM and GrIMIS logic.
Never read or create .env files.

## Database state (DONE, never edit these files unless asked)
sql/aidaa_iam_permission.sql  - app AIDAA, 8 IAM roles, audit.* permissions, role matrix
sql/aidaa_core_master.sql     - master data (10 tables)
sql/aidaa_core_planning.sql   - planning, budget, funding, schedule (13 tables)
sql/aidaa_log_approval.sql    - aidaa_log (5 append-only tables) + approval_step, approval_task
sql/aidaa_ai.sql              - aidaa_ai.ai_suggestion
NOT created yet: pka, exe_procedure, working_paper, finding, rekomend, audit_report, deviation view.

## Why the tables are grouped this way
- aidaa_core master: data that rarely changes (locations, audit types, units, cost components
  and rates, auditors, expertise, PKA and procedure library).
- aidaa_core planning: plan, plan versions, assignment (surat tugas), team, visits, trip legs,
  budget lines, funding, auditor schedule.
- aidaa_log: append-only history (team, approval, edit, comment, status). Triggers reject
  UPDATE and DELETE. Never write code that updates or deletes log rows.
- aidaa_ai: every AI proposal is stored first, a human accepts, edits or rejects it.

## Design reasons (follow these, do not simplify them away)
- audit_plan_version freezes what the Board approved (snapshot jsonb). The live plan row is
  editable only until approval. Deviation is CALCULATED (plan version vs assignment), never
  stored by hand. Only the reason and approver are logged.
- assignment.plan_id is nullable: empty means unplanned audit, flag it.
- assignment_member keeps start_date, end_date, end_reason. Never overwrite a team member:
  end-date the old row and insert a new one (leader resigns case). One active row per person
  per assignment.
- budget_line belongs to a plan OR an assignment, never both (CHECK). amount is generated
  (quantity x unit_rate), never insert it. unit_rate is copied from ref_cost_rate at creation
  so later rate changes never alter old budgets. When an assignment is issued, plan lines
  are copied (copied_from_line_id). Totals sum only one side, no double counting.
- Trip leg estimates create/update their own at_cost budget_line while not closed.
  actual_cost replaces the estimate after closing.
- budget_mode lumpsum or detailed: once detailed lines exist the total is the sum of lines,
  not typed by hand. Each version is consistent, the gap between versions is the deviation.
- ref_cost_component rows (not columns) define cost types with calc_basis: per_day_worked,
  per_travel_day, per_night, at_cost, fixed. New cost type = new row. Transit days get the
  transit stipend only, no manday. Rates are proposed by Finance and approved by Board
  (ref_cost_rate.approval_status). Budgets may only use approved rates.
- auditor_schedule has an exclusion constraint: one auditor cannot have overlapping confirmed
  rows. Plans may overlap, confirmed visits and trip legs may not. Write a schedule row when
  a visit or leg is confirmed, mark it cancelled when cancelled.
- assignment_funding splits one assignment across several ref_funding_source rows. Funding
  amounts must equal the approved budget total when the surat tugas is issued.
- Library copy: creating an assignment COPIES library PKA and procedures into pka and
  exe_procedure with source ids. Auditors may edit, add, or skip (is_skipped, skip_reason),
  never delete. Only Head manages the library.
- AI: any row created from AI has source = ai_suggestion and ai_suggestion_id. Never write AI
  output straight into real tables, always go through aidaa_ai.ai_suggestion and human
  accept. Record engine (ollama or cloud) and model_name.

## Roles
IAM global roles (set per person): AIDAA.ADMIN, AIDAA.BOARD, AIDAA.HEAD_AUDIT, AIDAA.AUDITOR,
AIDAA.HR, AIDAA.FINANCE, AIDAA.GENERAL_AFFAIRS, AIDAA.AUDITEE_PIC.
Assignment roles (per audit, only in assignment_member / audit_plan_member, never in IAM):
supervisor, leader, member. Only people with AIDAA.AUDITOR can hold them.
AIDAA.AUDITOR carries the union of leader/member/supervisor permission codes, so IAM alone
cannot tell them apart.

## Access rules (enforce in code)
- Two layers. Layer 1: require_permission("audit.xxx.yyy") from IAM. Layer 2: one shared
  helper that reads assignment_member and returns the caller's role in that assignment today.
  Every endpoint touching assignment data MUST call the helper after layer 1.
- Nobody approves their own work. Use approval_step / approval_task. Steps with
  approver_kind assignment_role are resolved from assignment_member.
- Plan approval: Finance verifies budget, then Board approves. Changes inside the approved
  plan: that audit's supervisor approves, Head can override. Cost rates: Board. Expertise: HR.
- One person = one role per assignment. Same person may hold different roles in different audits.
- Conflict of interest (hard block): an auditor cannot be assigned if the auditor's own org
  (auditor.home_org_id) is the audited unit's org or a child of it. Walk the IAM org tree.
  Log blocked attempts in aidaa_log.team_log with action blocked_conflict.
- expertise starts pending, only counts after HR sets verified. A finished audit adds a
  system_credit expertise row equal to days served.
- Auditee PIC sees only the assignment of their own unit.
- Rekomend stays open until resolved, monitored beyond the audit end.
- Every write action logs to the matching aidaa_log table. Login is IAM only, no own login.

## Working style
One small task at a time. Show the plan first. Never touch files outside this folder.
When editing a file, change only the lines needed, never replace the whole file.
Never edit sql/ files or reference/ unless asked. Ask before creating new tables.

## Next tasks (in order)
1. core/ and api/dependencies.py copied from reference, adapted to port 8002.
2. Shared helper: my_assignment_role(db, user_id, assignment_id).
3. Master data endpoints (locations, audit types, units, cost components, rates, auditors).
4. Plan endpoints with versions and approval tasks.
5. Assignment, team, visits, trip legs, budget lines, auditor_schedule writes.
6. Execution tables (pka, exe_procedure, working_paper, finding, rekomend), then reporting.
7. AI features last.