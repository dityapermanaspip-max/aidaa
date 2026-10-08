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