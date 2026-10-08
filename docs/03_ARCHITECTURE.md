# 03 Architecture and access

## Folder layout
```
app/main.py                  routers under /api/v1/aidaa, no cleanup loop
app/core/                    config.py, database.py, security.py (decode only)
app/api/dependencies.py      compatibility shim re-exporting the deps_* files plus log_audit
app/api/deps_auth.py         get_current_user, require_permission, require_any_permission
app/api/deps_org.py          _ORG_RESOURCES whitelist (plan, assignment), accessible orgs, check_org_permission, assert_org_access
app/api/deps_assignment.py   ROLES_*, authorize_assignment, authorize_view, authorize_pic
app/api/deps_permissions.py  one named wrapper per permission code
app/api/v1/aidaa/            master, masters_auditor, masters_library, library_ai, sbm_ai, masters_costing, masters_options,
                             funding, approval, plan, plan_flow, plan_budget_ai, me, assignment, team, trip, trip_ai,
                             budgeting, exec_pka, exec_finding, exec_report, ai
app/services/                one service per router, plus roles, conflict, logs, approval, ai_engine, ai_suggestions,
                             audit_setting, org_options, scope, unit_links, assignment_funding, sbm_ai, plan_budget_ai, trip_ai
  budget_core/_plan/_assignment/_edit/_trip/_totals.py   budgets split by job, budgets.py re-exports
  trip_common.py, visits.py, trip_leg.py                 trip split by job, trip.py re-exports
  execution/                 helpers, pka, procedures, findings, recommendations, reports
app/schemas/                 aidaa.py re-exports masters_auditor, masters_library, masters_costing; plus plan_flow, funding, me,
                             assignment, team, trip, budget, execution, ai, library_ai, sbm_ai, plan_budget_ai, trip_ai, org_options
sql/  docs/  reference/(read only)
```

## Router mounts
/master: master, masters_auditor, masters_library, library_ai, sbm_ai, masters_costing, masters_options.
/funding: funding. /approval: approval. /plan: plan, plan_flow, plan_budget_ai. /me: me.
/assignment: assignment, team, trip, trip_ai. Bare prefix: budgeting, exec_pka, exec_finding, exec_report, ai.

## Access
- Layer 1: require_permission (IAM) plus the org of the record (check_org_permission, org whitelist).
- Layer 2: my_assignment_role reads assignment_member. authorize_assignment (role-bound writes), authorize_view
  (returns 'team' or 'pic'). AUDITOR holds the union of leader, member and supervisor codes, so IAM cannot tell them apart.
- services/roles.py ROLE_ACTIONS is a GUESS, to confirm with the owner.
- Nobody approves their own work. Plan approval: Finance verifies, then Board approves (approval_task.record_id = version id).
- A user cannot decide their own cost rate.
- Approval engine: register_handler(record_type, fn). On the engine: plan, pka, procedure, finding, report.
  Own status columns: cost rates and expertise. Seeded but NOT wired: budget, assignment_change, cost_rate, expertise steps.
- Conflict of interest: auditor.home_org_id is checked against every unit org (hard block, logged blocked_conflict).
- Auditee PIC sees an assignment if their org is the org of ANY unit (or an ancestor), only after issue.
- Frontend only hides buttons. The backend is the security.