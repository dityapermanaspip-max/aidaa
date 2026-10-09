# Status

Last updated: 2026-10. Update this file whenever work changes it.

## Verified by the owner in the frontend
Master pages, auditor and IAU setting, org scope, units on plans and assignments, Tarif Biaya list (paging, grade filter,
2026 trial rates visible), rate approval flow screens.

## Written, NOT yet exercised
- SBM AI end to end: parser against real Lampiran 1, 16, 17, 30, 31 text, route rates, Web API (Gemini was busy).
- Plan budget AI, plan detailed budget tab, rate date rule in budgeting, rate overlap 409, library AI drafts.
- Trip AI (router and FE now exist, end-to-end not yet exercised), origin_location_id and location_fits change.
- Seeds: seed_trip_components loaded (6 components). 2026 trial rates loaded.

## Done recently
Trip AI is now runnable: `app/api/v1/aidaa/trip_ai.py` added and mounted in `main.py` under
`/api/v1/aidaa/assignment` (reads: `audit.assignment.read` + visibility; writes generate/decide:
`audit.assignment.update` or `audit.assignment.logistics`), plus the FE "Usulan AI" modal on the trips tab
(`darkhive-fev2 AssignmentTripAiModal`). Ride rules per `domains/trip.md`: AI answers only unit/start/end/
participants/reason; legs priced from approved ticket rates (estr./bisnis), round trip = two half legs;
on accept the server re-prices and only applies exact route matches.
Multi-root support and round-2 org scope (items 5 and 8 of the High gap list):
- A request picks its active AIDAA root once via `app/api/deps_root.py` (`resolve_root` mounted on every router
  in `main.py`). `root_id` (query) or `X-DH-Root` (header) is validated against the roots the user holds AIDAA
  roles in; a single root is derived automatically. `get_root` honors the pinned root, so all services behave as
  one-root without any call-site change. A multi-root user who sends no root still gets 409, now with an
  actionable message; the FE sends `root_id` derived from the active AIDAA context.
- `aidaa_core.auditor` and `aidaa_core.ref_auditable_unit` now carry `root_org_id`
  (`sql/aidaa_patch_04_org_scope2.sql`, run AFTER patch 03). Auditors are listed/created/updated/deactivated
  inside the active root; `home_org_id` must live inside the root (the IAU tags any user in its tree);
  expertise and documents are root-scoped through the auditor. `unit_code` is now unique PER root instead of
  across the whole database.

Plan deviation is now served: `GET /api/v1/aidaa/deviations` (`audit.deviation.read`, org scope through
`get_user_accessible_org_ids`) reads `aidaa_core.v_plan_deviation`, and the FE page `/dashboard/aidaa/deviation`
renders the plan-vs-actual comparison table (auditors, days, man-days, budget, leader change).
Frontend execution edits: PKA title/objective/planned hours/auditor (draft only), procedure text, working paper
(makes the PATCH endpoints reachable), plus the findings/recommendations/report tabs. FindingOut now carries
`under_review` (pending approval_task) so the UI can show "Menunggu review". Run and docs below.
Rate grade as jsonb, rate date rule (start date), overlap check, rate list filter and paging, ai_engine rewrite (retry, error text),
SBM AI (four table shapes), plan budget AI, trip AI service and schema (no router), route rates (origin_location_id),
base_location_id column.
Run and docs: git_part_2\dev.ps1 starts this backend on 8002 with IAM and GrIMIS; the FE docs entry point
darkhive-fev2\docs\shared.md was filled in (it was empty).

## To do (next)
1. Test SBM AI with real text, then load real 2027 data (lodging, daily allowance, tickets, road, terminal, in-city transport).
2. Screen to set audit_setting.base_location_id and to edit auditor grade and home location with codes that match rate grades.
3. Realisation feature: advance, accountability, reimbursement, variance, cross-subsidy (see domains/trip.md).
4. Flag budget lines above the SBM reference with a required reason.
5. AI helpers: library_improvement, team, expertise. Parser shape for one-column-per-grade tables.
6. Wire seeded approval steps (budget verification, assignment_change).

## Known gaps
- Findings have no unit column.
- No file storage, documents are url or path metadata only. AI has no PDF upload and no looping above 30000 chars.
- Real daily allowance and lodging spending is not recorded.
- ROLE_ACTIONS in services/roles.py is a guess.
- Each root needs an active at_cost component coded TRANSPORT, or a component chosen on every leg.
- Auditors without a grade match only rates with an empty grade list.
- The library_ai router may still have a duplicate GET /library/ai/drafts (delete the second function).
- Verify that budgeting's /assignment/{id}/funding does not clash with the assignment router.
- **Trip AI is runnable but end-to-end not exercised**: `app/api/v1/aidaa/trip_ai.py` is mounted (`/assignment/{id}/ai/trip/drafts`),
  the frontend modal exists ("Usulan AI" on the trips tab), but the flow was not run against a live AI engine yet (2026-10).
- `GET /pka/{id}` is mounted but the frontend never calls it (the assignment list is enough).
  `PATCH /pka/{id}`, `PATCH /procedures/{id}` (text) and `PATCH /papers/{id}` are now used by the frontend.
- `sql/aidaa_patch_04_org_scope2.sql` has been applied to the database (2026-10): `auditor` and
  `ref_auditable_unit` now carry `root_org_id`, `uq_ref_auditable_unit_root_code` replaced the global
  `unit_code` unique constraint.