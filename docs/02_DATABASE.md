# 02 Database

All sql files are done and safe to rerun. Never edit them unless the owner asks. Run in this order.

## Files (sql/)
1. aidaa_iam_permission.sql      app AIDAA, 8 IAM roles, audit.* permissions, role matrix
2. aidaa_core_master.sql         master data (10 tables)
3. aidaa_core_planning.sql       planning, budget, funding, schedule (13 tables)
4. aidaa_log_approval.sql        aidaa_log (5 append-only tables), approval_step, approval_task
5. aidaa_ai.sql                  aidaa_ai.ai_suggestion
6. aidaa_execution.sql           pka, exe_procedure, working_paper, finding, finding_response, rekomend, audit_report,
                                 v_plan_deviation, can_skip, skipped status
7. aidaa_patch_01_audit_universe.sql
   location address, audit_setting (IAU), one tag per org, audit_plan_unit and assignment_unit, audit.setting.* permissions.
   Also holds (merged by the owner): ref_cost_rate.grade as jsonb array with CHECK ck_rate_grade_array,
   ref_cost_rate.origin_location_id, audit_setting.base_location_id.
8. aidaa_patch_02_library_ai.sql
   library_pka.ai_suggestion_id and the ai_suggestion feature CHECK. This file holds the FINAL feature list:
   plan, team, pka, budget, report, library_improvement, expertise_extract, library_draft, sbm_draft, trip_draft.
   Any new AI feature is added to this one CHECK. Keep it the last statement that redefines the constraint.
9. aidaa_patch_03_org_scope.sql  root_org_id on ref_location, ref_audit_type, ref_cost_component, ref_funding_source,
   library_pka; codes unique per root; backfill.
10. aidaa_patch_04_org_scope2.sql  root_org_id on auditor and ref_auditable_unit (same pattern); unit_code unique per
    root instead of the whole database. Run LAST of the patches.
11. aidaa_patch_05_realisation.sql  realisation_advance, realisation_cost, realisation_settlement (2026-10, applied).
    realisation_cost.amount is GENERATED (quantity x unit_rate), never insert it. realisation_settlement is reserved
    for the settlement approval batch (open/settled via approval_task for finance).
Note: patch 03 runs after patch 02. If 01 also redefines the feature CHECK, 02 must contain the complete list.

## Seeds (sql/sql_seed/, data not patches)
- seed_sbm_2027.sql: TEMPLATE for the yearly SBM seed of ONE root.
- seed_sbm_2026.sql: TRIAL lodging data (Lampiran 30, 38 provinces x 4 grades = 152 rates, root org code PDGRPT,
  2026-01-01 to 2026-12-31, approved). Amounts NOT checked against the PMK. Loaded once. Real data comes from the SBM AI helper.
- seed_trip_components.sql: six at_cost trip components (TRANSPORT, TIKET_PESAWAT_EKONOMI, TIKET_PESAWAT_BISNIS,
  TRANSPORT_DARAT_ANTAR_KOTA, TRANSPORT_TERMINAL, TRANSPORT_KEGIATAN_DALAM_KOTA), no amounts. Loaded for PDGRPT.
A seed names its root by ORG CODE in step 0 (many roots exist). Never read audit_setting in a seed.

## Conventions
- All primary keys are uuid. Permission codes are audit.<resource>.<action>, lowercase dotted.
- Only foreign keys out of iam: org_id and user_id. AIDAA writes to iam only through iam.audit_log (log_audit).
- No cleanup loop (IAM does that). Login is IAM only. Auth: token jti not in iam.revoked_tokens and tv equals users.token_version.
- Engine names: API and frontend use OLLAMA and WEB_API. The ai_suggestion.engine column stores ollama and cloud.
- budget_line.amount is GENERATED (quantity x unit_rate). Never insert it.
- realisation_cost.amount is GENERATED (quantity x unit_rate). Never insert it.
- Balance and variance amounts of realisation are computed in the report SQL (advance - realised,
  planned - realised), never stored.
- ref_cost_rate.grade is jsonb (array of codes, NULL or empty means every grade). auditor.grade stays free text.
- LEGACY, unused: library_pka.default_hours, ref_location.parent_location_id, ref_location.is_branch_office.
- There is no audit.funding.* permission, funding reuses audit.coststd.*.
- audit_plan.owner_org_id and assignment.owner_org_id were added after the planning file (NOT NULL).

## Org scope
Seven master tables carry root_org_id (locations, audit types, cost components, funding sources, PKA library,
auditors, auditable units). Cost rates inherit the root of their component. Codes are unique per root. A caller
sees only their root (get_root, resolved once per request). Another root's record answers 404.
Plans, assignments, budget lines, trip legs, funding allocation and the PKA copy reject records of another root.
The Internal Audit Unit is a child org of the root; it audits the whole tree, tags any user as auditor and sets any
child org as an auditable unit (both tags need the org to be inside the root).