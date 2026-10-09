# Decisions (append only, newest last)

Format: date, decision, reason.

- 2026-09: Single unit and no trips are the default, extras are optional. Keeps one-unit records simple.
- 2026-09: Master data is scoped per root org, codes unique per root. Many organisations share one deployment.
- 2026-09: Seeds name the root by org code. Many roots exist, audit_setting has one row per root.
- 2026-09: AI output always goes to ai_suggestion first, a human decides. Accountability and no invented data.
- 2026-10: SBM is reference, not a block. Lines above it are flagged with a reason.
- 2026-10: Rate grade is a jsonb array, not text or a table. One row per PMK block, mapping visible in data, no deploy for a new grouping.
- 2026-10: Rate is checked on the START DATE of the plan or assignment. A 2026 rate must not price a 2027 record.
- 2026-10: SBM amounts are read by a code parser, AI only names columns. Amounts must not be invented.
- 2026-10: Tickets are at_cost components with a reference MAXIMUM rate. Budget uses the maximum, real cost at realisation.
- 2026-10: Round-trip ticket (PP) is split into two legs of half the rate. Cross-subsidy is handled at realisation.
- 2026-10: Ticket class defaults to Economy. Business only when the auditor's grade is listed on a Business rate.
- 2026-10: Travel days together earn ONE daily allowance (practice). Constants in plan_budget_ai, owner doubts fairness.
- 2026-10: Trip helper creates visits and ticket legs only. Allowance and lodging stay budget lines to avoid double cost.
- 2026-10: Origin of a trip is the auditor's home location, then the organisation's base location (per root). Regional plans are separate and reusable.
- 2026-10: Airport city is picked from a searchable list of ticket destinations. Names matching several places are never guessed.
- 2026-10: Docs are English and split small (rules, overview, database, architecture, domains, status, decisions).
- 2026-10: Files touched in more than one place are given as full replacements. Chunks left old code behind.
- 2026-10: One database, three backends, one frontend. Each app owns its schemas and its port (IAM 8000, GrIMIS 8001, AIDAA 8002);
  the browser only ever talks to the Next BFF proxies, never to a backend directly.
- 2026-10: The shared launcher git_part_2\dev.ps1 owns the run config for all four processes. Port or startup changes go there, not per repo.
- 2026-10: A submitted finding keeps status `draft`; "waiting for review" is exposed as a derived `under_review` flag on FindingOut
  (EXISTS a pending approval_task for the finding), not as a new status value. The status machine and its handlers stay unchanged.
- 2026-10: Findings link to a procedure by `procedure_id` (validated against the same assignment). Only create sets it; FindingUpdate
  cannot change it, so the editor never offers it.
- 2026-10: Plan deviation is read-only and scoped like the assignment list: `GET /deviations` filters by the caller's
  accessible orgs in the SQL, deviation numbers are computed by the view, never by hand or by the page.
- 2026-10: AIDAA's root is resolved once per REQUEST, not once per user. `resolve_root` (a dependency on every
  router) validates `root_id`/`X-DH-Root` against the roots the user holds AIDAA roles in and pins it on the db
  session; single-root users need nothing. The 409 for multi-root callers stays (with an actionable message) only
  when no root is sent. Reason: master data is shared inside one audit universe and plans/assignments are already
  org-scoped, so only master-data calls need a root choice.
- 2026-10: The Internal Audit Unit is a CHILD org reporting to the board; it audits the whole root tree. It may tag
  ANY user as auditor (`auditor.home_org_id` inside the root) and set ANY child org as auditable unit
  (`ref_auditable_unit.org_id` inside the root). Both tables got `root_org_id` (patch 04, same pattern as patch 03);
  `unit_code` is unique per root, not globally. Reason: many roots share one deployment, and the IAU belongs to a
  branch while the audited universe is the root.
- 2026-10: Trip AI drafts are exposed under `/assignment/{id}/ai/trip/drafts` and governed by the assignment's own
  permissions (read: `audit.assignment.read`; create/decide: `audit.assignment.update` or `audit.assignment.logistics`),
  not by a library/head-only permission. Reason: the helper edits the assignment's visits and legs, the same records the
  assignment team already manages; drafts are already submitted by an active auditor role.
- 2026-10: Editing a trip AI draft is limited to picking the leg destination from the server's airport list and dropping
  rows; the ticket class and half costs are not human-editable in the modal. Reason: on accept the server re-prices from
  approved rates anyway (`TripDraft(**out)` round-trip), so free-form money edits would be silently overwritten.
- 2026-10: Real costs are recorded PER AUDITOR (each advance and cost row names an active team member), not per
  assignment. Reason: advances are given and returned per person; the settlement is then per person too.
- 2026-10: Cross-subsidy is realised by reusing the trip leg `actual_cost` (outbound + return carry the real ticket
  shares, their sum is the real ticket price) and the variance report compares realised vs planned per component.
  Reason: no second, hidden ticket table that could diverge from the trip page.
- 2026-10: Realisation only on issued/ongoing/finished assignments (draft/cancelled are refused), costs and advances
  must belong to ACTIVE team members, components/locations are validated root-scoped, and balance/variance amounts
  are computed in the SQL (advance - realised; planned - realised), never stored. Amount on costs is GENERATED.
- 2026-10: `realisation_settlement` exists now (patch 05) but the workflow is a LATER batch: an approval task for
  finance transitions open -> settled after the batch that adds tables + per-auditor costs + cross-subsidy is pushed.
  Reason: the owner wants the granular + cross-subsidy base in main before adding the approval flow.
- 2026-10: Realisation reads use `audit.assignment.read` and writes `audit.assignment.update` or
  `audit.assignment.logistics`, same as trips. No new IAM permission. Reason: the people who run trips already
  manage the money spent on the same assignment.
- 2026-10: Settlement is approved per AUDITOR via the generic approval engine: submitting an auditor's settlement
  upserts `realisation_settlement` (status open, unique per assignment+auditor) and creates an approval_task
  (record_type `settlement`, step 1 `finance_approve`, approver `AIDAA.FINANCE`). Approve -> status settled +
  locked (re-submit refused with 409); reject/return -> stays open and can be resubmitted. The amount is never
  stored: the current balance (advance - realised) is read from the report at render time and snapshot in each
  `SettlementOut` response. Reason: no drift between the report and the approval; the settlement only locks the
  per-auditor balance.