# 00 Rules and working style

## Language
All agent-facing docs and code comments are English. UI labels in the frontend stay Indonesian.

## Owner rules (hard)
- "go code" gate: plan first, write code only after the owner writes "go code". A question or a pasted file is not "go code".
- One small task at a time. Show the plan before the code.
- Never read or create .env. New settings are announced in chat and added by the owner.
- Ask for the target file before replacing or editing it. Several files share names across folders
  (funding.py, masters_costing.py, library_ai.py exist as router, schema and service). Confirm which one.
- Code is typed in chat for copying. Any file touched in more than one place is given as a FULL REPLACEMENT.
  Scattered chunks left old code behind more than once. A single small edit may be a chunk or one function.
- New files come with a one-line PowerShell command. Database changes are one-liners for psql.
- Keep answers short. Do not ask for manual test steps: the owner tests in the frontend and does not want token tests in chat.
- Never edit sql/ or reference/ unless asked. Ask before creating new tables. Do not modify IAM.
- Do not invent amounts or rates. Money comes from approved master data or from a code parser, never from AI text.

## Sandwich stacking workflow (bottom-up)
1. Schema: read the SQL, then write the Pydantic schemas.
2. Service: logic in app/services/<domain>.py with raw SQL through text().
3. Dependency: permission wrappers in app/api/deps_permissions.py, org whitelist in deps_org.py, role helpers in services/roles.py.
4. Router: app/api/v1/aidaa/<domain>.py, registered in app/main.py.
5. Check: `python -c "import app.main; print('ok')"`, then the owner tests through the frontend.
Gate: do not start the next layer before the current one passes. If a layer fails, fix only that layer.
Small single-table CRUD may combine steps but keeps the order.

## Code conventions
- Raw SQL only. Cast ids with CAST(:x AS uuid). Table names never come from input (use whitelists).
- Split schemas, services and routers per sub-domain once a file gets long. Keep a thin re-export file when splitting
  (budgets.py, trip.py, dependencies.py, schemas/aidaa.py). Do not recreate deleted stubs.
- Service signature: read functions of master data take user_id after db. Write functions take user_id last.
- Static routes must be declared before /{id} routes in the same router.
- Every write logs to aidaa_log through services/logs.py and to iam.audit_log through log_audit.
- aidaa_log tables are append only. Never write code that updates or deletes log rows.
- PowerShell: Select-String has no -Recurse. Use: Get-ChildItem app -Recurse -Filter *.py | Select-String "text".
- reference/ is read-only (IAM schema, GrIMIS patterns, READMEs).