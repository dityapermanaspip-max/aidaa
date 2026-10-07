# 2. Rules, working style and skeleton

## WORKFLOW: Sandwich Stacking Method (HIGH PRIORITY)
Bottom-up workflow for complex, interconnected or high-risk features. No layer is written or assumed working until the layer it
depends on has passed its check.
1. Schema: read the SQL to understand the data contract, then write the Pydantic schemas.
2. Service: business logic in app/services/<domain>.py with raw SQL (text()).
3. Dependency: security wrappers for the NEW resource in app/api/deps_permissions.py (table-to-org whitelist entry in
   deps_org.py, role helpers in services/roles.py).
4. Router: app/api/v1/aidaa/<domain>.py using the wrappers and services, registered in app/main.py.
5. Integration check, both must pass: (a) run.ps1 starts without errors (quick form: python -c "import app.main; print('ok')");
   (b) /docs lists the new endpoints and one call with a real IAM token works.
GATE RULE: do not start the next layer until the current one passes its check. If a layer fails, fix only that layer. Show the
plan and the result of each check before moving on. Small single-table CRUD may combine steps but keeps this order.
Check (b): the owner now tests through the FE instead of /docs, and wants no token-testing steps in chat. Do not add manual
test lists unless asked. Layers written but not exercised yet are listed in 3_DESIGN (Status).

## Working style
- One small task at a time. Show the plan first. Never touch files outside the project folder.
- Do NOT write code until the owner says "go code". Never edit sql/ or reference/ unless asked. Ask before creating new tables.
- Ask the owner to paste the target file before replacing or editing it. Never guess file contents, ask for references when unsure.
  Several files share names across folders (funding.py, masters_costing.py, library_ai.py exist as router, schema and service).
- Code is typed in chat for the owner to copy. For any file touched in more than one place give a FULL REPLACEMENT of the file,
  never scattered edits (pasted chunks left old code behind more than once). Small single edits may be a chunk or a function.
  New folders and files come with a one-line PowerShell command. pgAdmin and psql commands are one-liners. Keep answers short.
- PowerShell: Select-String has no -Recurse. To search the code use: Get-ChildItem app -Recurse -Filter *.py | Select-String "text".
- Rule: split schemas, services and routers per sub-domain once a file gets long. Keep a thin re-export file when splitting
  (budgets.py, trip.py, dependencies.py, schemas/aidaa.py). Unused stubs were deleted, do not recreate them.
- reference/ is read-only (IAM schema, GrIMIS patterns, main.py pattern, READMEs). Never edit it.
- Seeds name the root by org code. Many roots exist.

## Skeleton (folder layout)
app/main.py                    routers registered under /api/v1/aidaa, no cleanup loop
app/core/                      config.py, database.py, security.py (decode only)
app/api/dependencies.py        compatibility shim re-exporting the files below plus log_audit
app/api/deps_auth.py           layer 1: get_current_user, require_permission, require_any_permission
app/api/deps_org.py            layer 1 for records: _ORG_RESOURCES whitelist (plan, assignment), get_user_accessible_org_ids,
                               get_resource_org_id, check_org_permission, check_org_any_permission, assert_org_access
app/api/deps_assignment.py     layer 2: ROLES_*, authorize_assignment, authorize_view, authorize_pic
app/api/deps_permissions.py    one named wrapper per permission code, grouped by domain
app/api/v1/aidaa/              master, masters_auditor, masters_library, library_ai, sbm_ai, masters_costing, masters_options,
                               funding, approval, plan, plan_flow, plan_budget_ai, me, assignment, team, trip, budgeting,
                               exec_pka, exec_finding, exec_report, ai
app/services/                  one service per router, plus: roles, conflict, logs (incl. log_audit), approval, ai_engine,
                               ai_suggestions (assignment AI), audit_setting, org_options, scope, unit_links, assignment_funding
  ai_engine.py                 generate_json(prompt, engine, model) for OLLAMA and WEB_API, retries 429 and 503 up to 3 times,
                               returns Google's error text, strips code fences, list_ollama_models()
  sbm_ai.py                    SBM helper: fixed province map (PROV-xx), table parser, AI naming, apply to DRAFT rates
  plan_budget_ai.py            plan budget helper: AI gives on-site days, code picks rates and builds lines
  scope.py                     organisation scope: root_of_org, assert_in_root, scoped_get, get_root (re-export)
  unit_links.py                units of a plan or assignment
  budget_core/_plan/_assignment/_edit/_trip/_totals.py   budgets split by job, budgets.py re-exports them
  trip_common.py, visits.py, trip_leg.py                 trip split by job, trip.py re-exports them
  funding.py                   master funding sources and documents ONLY (allocation is assignment_funding.py)
  execution/                   package: helpers, pka, procedures, findings, recommendations, reports
app/schemas/                   aidaa.py re-exports masters_auditor, masters_library, masters_costing; also plan_flow, funding,
                               me, assignment, team, trip, budget, execution, ai, library_ai, sbm_ai, plan_budget_ai, org_options
sql/                           see 1_OVERVIEW (database state). docs/ holds these three files.

Router mounts (main.py): master, masters_auditor, masters_library, library_ai, sbm_ai, masters_costing and masters_options
under /master. funding under /funding, approval under /approval, plan, plan_flow and plan_budget_ai under /plan, me under /me,
assignment, team and trip under /assignment. budgeting, exec_pka, exec_finding, exec_report and ai sit on the bare prefix.
Static paths under a router that also has /{id} must be declared before the /{id} route.

Service signature convention: functions that read master data take `user_id` after `db`. Write functions take user_id last.