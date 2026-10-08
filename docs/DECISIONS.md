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