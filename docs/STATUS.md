# Status

Last updated: 2026-10. Update this file whenever work changes it.

## Verified by the owner in the frontend
Master pages, auditor and IAU setting, org scope, units on plans and assignments, Tarif Biaya list (paging, grade filter,
2026 trial rates visible), rate approval flow screens.

## Written, NOT yet exercised
- SBM AI end to end: parser against real Lampiran 1, 16, 17, 30, 31 text, route rates, Web API (Gemini was busy).
- Plan budget AI, plan detailed budget tab, rate date rule in budgeting, rate overlap 409, library AI drafts.
- Trip AI (schema and service only, see Known gaps), origin_location_id and location_fits change.
- Seeds: seed_trip_components loaded (6 components). 2026 trial rates loaded.

## Done recently
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
5. Frontend batch 5e: PKA/procedures/papers, findings, recommendations and reports are written in the FE; plan deviation is not (no endpoint yet).
6. AI helpers: library_improvement, team, expertise. Parser shape for one-column-per-grade tables.
7. Wire seeded approval steps (budget verification, assignment_change).

## Known gaps
- Auditors and expertise are not root-scoped (home_org_id). unit_code is unique across the whole database.
- Findings have no unit column.
- A user whose AIDAA roles span more than one root gets 409 on root-dependent endpoints.
- No file storage, documents are url or path metadata only. AI has no PDF upload and no looping above 30000 chars.
- Real daily allowance and lodging spending is not recorded.
- ROLE_ACTIONS in services/roles.py is a guess.
- Each root needs an active at_cost component coded TRANSPORT, or a component chosen on every leg.
- Auditors without a grade match only rates with an empty grade list.
- The library_ai router may still have a duplicate GET /library/ai/drafts (delete the second function).
- Verify that budgeting's /assignment/{id}/funding does not clash with the assignment router.
- **Trip AI has no router**: `app/services/trip_ai.py` and `app/schemas/trip_ai.py` exist, but
  `app/api/v1/aidaa/trip_ai.py` is missing and `app/main.py` does not mount it. The frontend has no trip AI code either
  ("Usulan AI" exists only in the plan budget). Until the router is added and mounted, this feature is not runnable.
- **Plan deviation has no endpoint**: `aidaa_core.v_plan_deviation` and permission `audit.deviation.read` exist,
  but nothing reads the view and the nav link `/dashboard/aidaa/deviation` 404s.
- `GET /pka/{id}` is mounted but the frontend never calls it (the assignment list is enough).
  `PATCH /pka/{id}`, `PATCH /procedures/{id}` (text) and `PATCH /papers/{id}` are now used by the frontend.