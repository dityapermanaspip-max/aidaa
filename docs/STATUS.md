# Status

Last updated: 2026-10. Update this file whenever work changes it.

## demo-ai branch
Branch `demo-ai` is forked from `main` (same branch name in the other Darkhive repos). Built here: the PDF
extractor for SBM and library AI drafts (`app/api/v1/aidaa/doc_extract.py`, mirror of GrIMIS doc_extract).

## Verified by the owner in the frontend
Master pages, auditor and IAU setting, org scope, units on plans and assignments, Tarif Biaya list (paging, grade filter,
2026 trial rates visible), rate approval flow screens, PDF import (upload -> source text review) on the SBM AI and
 library AI pages (2026-10).

## Written, NOT yet exercised
- **Global location tier, patch 10 + national seed (2026-10-25)**: `ref_location` now holds TWO tiers in one
  table — `root_org_id IS NULL` = shared national master (BPS: 38 provinces + 514 kab/kota, read-only in the
  app) and `root_org_id = <root>` = the org's own rows, unchanged. DDL
  `sql/aidaa_patch_10_location_master.sql` (nullable root + two partial unique indexes; makes the two SBM
  seeds' `ON CONFLICT` targets partial-index aware — both seeds were updated for that). Read side: the
  locations list/get, auditor home, budget/realisation refs, base location and trip drafts accept global
  rows; SBM place matching is now two-pass (org rows first, then national, then a new org `CITY-` row; an
  exact name spelling beats a longer one when several places match). Write side: editing/deactivating a
  global row answers 403; the owner reruns `sql/sql_seed/seed_locations_indonesia.sql` to update the master.
  FE: the locations page shows a Sumber badge (BPS/Organisasi) and locks Ubah/Nonaktifkan for BPS rows
  (MasterCrud gained the additive `editableRow`). Import check and `npx tsc --noEmit` pass; NOT exercised in
  the browser, DDL and seed not yet run.
- **Home base and auditor grade screen (2026-10-24)**: `PUT/GET /master/audit-setting` now also carries
  `base_location_id` (both fields optional in `AuditSettingIn`, explicit null clears it; row must exist,
  so 409 until the IAU is set; location validated active + same root). FE: the settings page has a
  "Lokasi Dasar" block and the auditor form suggests grade codes from
  `GET /master/cost-rates/grade-codes` (distinct grades of the root's approved rates,
  `audit.costrate.read`). Not exercised in the browser yet.
- **Manual rate picker in the plan budget AI modal (2026-10-24)**: new read endpoint
  `GET /master/cost-rates/candidates` (component_id, location_id, on_date required; grade and
  origin_location_id optional) returns approved + active rates valid on that date, filtered/ordered by
  the same `location_fits` logic as the budget AI `_pick_rate` (exact place first, listed grade first,
  cheapest last). The modal offers these to its `no_rate`/`manual` lines; a pick sets rate_id + unit_rate
  + amount and flips the line to `ok`. Not exercised in the browser yet.
- **Monev Temuan (2026-10-24)**: `GET /monitoring/temuan` (`audit.finding.read`) returns cross-assignment
  findings + rekomendasi rows (slim: no description/criteria) with `no_response`/`overdue`/`under_review`
  flags and unit names. Scope = the same org rule as the surat tugas list: a global perm mapping sees all;
  an org-mapped caller sees its own records and, after issue, the audited units of its orgs — so people
  OUTSIDE the internal audit org (auditee PICs) can use it, provided the IAM matrix grants them
  `audit.finding.read` scope-mapped. FE page `/dashboard/aidaa/monev` (search + overdue-only + status
  filters, Temuan and Rekomendasi tables). Not exercised in the browser yet.
- **Korespondensi (2026-10-24)**: document requests (A), interview schedules (C) and the berita acara
  penyampaian notisi (D) per assignment. DDL = `sql/aidaa_patch_06_korespondensi.sql` (numbered 06
  because patches 04/05 already exist) — **written, NOT yet run by the owner; run locally, then on the
  VPS, before testing any of these endpoints** (tables do not exist until then; it also backfills BAP
  skeletons for findings already communicated+). New service `app/services/execution/correspondence.py`
  + router `app/api/v1/aidaa/correspondence.py`: doc-req `GET|POST /assignment/{id}/doc-req`,
  `PATCH /doc-req/{id}`, `POST /doc-req/{id}/submit` (PIC), `/verify`; interviews
  `GET|POST /assignment/{id}/interviews`, `PATCH /interview/{id}` (planned only),
  `/hold`, `/done`, `/cancel` (reason required); BAP `GET /assignment/{id}/baps` (flat list, every
  communicated+ finding with nullable BAP fields), `POST /findings/{id}/bap`, `PATCH /bap/{id}`,
  `POST /bap/{id}/result` (records the auditee's stance). NEW RULE: `resolve_finding` now refuses
  (409) to resolve a finding whose berita acara has no recorded `stance_result` — an existing responded
  finding can no longer be resolved until its BAP result is recorded. Permission reuse only (no new
  codes): doc-req manage `audit.assignment.update` (ROLES_WORK, workable), PIC submit
  `audit.finding.respond` + authorize_pic + the row must belong to the PIC's own audited unit,
  interviews the logistics wrapper, BAP writes `audit.finding.communicate` (lead/supervisor), all
  reads `authorize_view` with `audit.finding.read` and PIC lists org-filtered. FE:
  `/dashboard/aidaa/exec/korespondensi` (Penugasan menu, after "Tim Audit") with three cards.
  Import check passes; NOT exercised in the browser and DDL not yet run.
- **Kuesioner (2026-10-24)**: procedure-linked questionnaires. DDL = `sql/aidaa_patch_07_kuesioner.sql`
  (numbered 07; **written, NOT yet run by the owner — run locally then on the VPS, after patch 06**).
  It adds `needs_questionnaire` to `aidaa_core.exe_procedure` plus four tables: `assignment_questionnaire`
  (ONE per procedure via a UNIQUE `procedure_id`; status draft→issued→closed; `respondents_needed`;
  `public_token` uuid + `link_expires_at`), `questionnaire_question` (≤5 per questionnaire, kinds
  single_choice/multi_select/free_text/scale, `choices` jsonb 2–5, `scale_max` 4/5/6),
  `questionnaire_response` (identity block name/position/age/last_degree/gender + `submitted_via`
  public|pic, `submitted_by` NULL for anonymous), `questionnaire_answer` (one row per question per
  response). New service `app/services/execution/questionnaires.py`, router
  `app/api/v1/aidaa/questionnaires.py` (mounted with ROOT_SCOPED) and the first UNAUTHENTICATED
  router `app/api/v1/aidaa/public.py` (`GET|POST /public/questionnaires/{token}`, mounted WITHOUT
  ROOT_SCOPED). Team planning `GET /assignment/{id}/questionnaire-procedures` (every non-skipped
  procedure LEFT JOINed with its questionnaire), `PATCH /procedures/{id}/needs-questionnaire`
  (flag toggle, ROLES_WORK), questionnaire CRUD + questions CRUD (draft-only), batch
  `POST /assignment/{id}/questionnaires/issue` (LEADER; 422 listing flagged procedures that still
  lack questions), `close`, `regenerate` (fresh token + 40h window, old token dies instantly, team or
  PIC), `GET /questionnaire/{id}/results` (team-only evidence aggregates) and
  `POST /questionnaire/{id}/responses` (auditee PIC in-app). Public answering validates every
  question once, per-kind bounds, and accepts responses while issued + assignment workable; public
  submissions write no audit log. Permission reuse only (assignment.update + ROLES_WORK/ROLES_LEAD,
  finding.respond + authorize_pic for the PIC, finding.read + authorize_view for reads). FE:
  fourth card on `/dashboard/aidaa/exec/korespondensi` (`KorespondensiQuestionnaireCard`: coverage
  strip + per-procedure checkbox + builder + batch issue + results; PIC list + in-app entry) plus the
  no-auth public page `/q/[token]` and the no-auth BFF forwarder `/api/aidaa-public/[...path]`.
  Import check + `npx tsc --noEmit` pass; NOT exercised in the browser and DDL not yet run.
- **AI helpers batch (2026-10-25)**: the three remaining helpers plus the SBM grade mode are built end to end
  (backend + FE); import check and `npx tsc --noEmit` pass; NOT exercised in the browser yet.
  - SBM grade mode: one component per grade-column table, `grade_columns` maps heading -> grade code, rates carry a
    single grade, accept still writes DRAFT rates only (`sbm_ai` split into `sbm_ai_parse` + `sbm_ai_apply`).
  - team: view-only ranked shortlist, `POST /assignment/{id}/ai/team-suggestions` (leader-only); roster = active
    auditors of the root holding the AIDAA.AUDITOR IAM role, current members excluded; acceptance only records the
    decision; FE `TeamSuggestionPanel` on the assignment team card.
  - library_improvement: `POST /library/pka/{id}/ai-improvement` (`library_manage`), ONE pending per PKA, accept
    deactivates the old head and creates a new `<type>-NNN` head with the improved procedures; FE
    `LibraryImprovementSection` on the library detail page.
  - expertise_extract: the auditor extracts their OWN credentials (`POST /master/auditors/{id}/expertise/ai-suggestions`);
    accept inserts pending rows (source 'ai_suggestion') and opens ONE `expertise`/`hr_verify` task for AIDAA.HR; the
    approval handler decides the whole batch together; FE `ExpertiseAiCard` (owner-only) on the auditor page; the
    approval inbox links the auditor of the batch's first row.
  - **DDL `sql/aidaa_patch_09_expertise_ai.sql` must run first** (adds `expertise.ai_suggestion_id` and widens the
    source CHECK) - until then generate/list work but ACCEPT fails with 500.
- SBM AI end to end: parser against real Lampiran 1, 16, 17, 30, 31 text, route rates, Web API (Gemini was busy).
- Plan budget AI, plan detailed budget tab, rate date rule in budgeting, rate overlap 409, library AI drafts.
- PDF import for SBM and library AI drafts: `app/api/v1/aidaa/doc_extract.py` (`POST /api/v1/aidaa/documents/extract`,
  PyMuPDF text layer + per-page Tesseract fallback, 25 MB cap, 100 pages, no org scope — mirror of GrIMIS),
  FE upload buttons on `master/sbm-ai` and `master/library/ai`. Upload flow exercised by the owner in the browser
  (2026-10); the SBM parser shapes with real Lampiran text are still to exercise.
- **Realisation in the frontend**: the service layer passed a live-DB smoke test (transaction rolled back),
  settlement was smoke-tested (submit -> pending, approve -> settled, reject -> open -> resubmit), but the flow
  was not exercised in the frontend yet.
- Trip AI (router and FE now exist, end-to-end not yet exercised), origin_location_id and location_fits change.
- Seeds: seed_trip_components loaded (6 components). 2026 trial rates loaded.

## Done recently
- 2026-10-25 (batch): the two remaining seeded approval steps are wired. `budget`/`finance_verify`:
  leader submits the issued/ongoing assignment's budget (`POST /assignment/{id}/budget-verification`,
  one pending at a time), `AIDAA.FINANCE` decides in the generic inbox, `GET` returns the latest
  task; approval/rejection are recorded as comments and lines may keep editing (no lock, resubmit
  allowed) - the latest task doubles as the verification state. `assignment_change`:
  `sql/aidaa_patch_08_change_requests.sql` (NOT yet run) stages post-issue edits (dates, notes,
  document, extra units) in `assignment_change`; the leader files, the assignment's supervisor gets
  an assigned task (`_reviewer` path), and only an approved task applies the payload through the
  shared `_apply_assignment_edit` (same date/unit/conflict guards as the draft PATCH; the requester
  cannot decide; one pending request at a time; requesting is leader-only). FE: change-request card
  on the assignment page, verification strip on the budget tab, inbox rows link to the assignment.
- 2026-10-25: Hygiene batch. Verified NO route clash for `/assignment/{id}/funding`: budgeting is mounted
  at the bare API prefix, the assignment router has no 3-segment paths, and no other `/assignment`-prefixed
  router defines funding routes (the stale known-gaps bullets are gone). The library_ai duplicate GET
  `/library/ai/drafts` no longer exists. Dropped the unused guessed ROLE_ACTIONS layer and the `actions`
  field of `GET /me/assignments/{id}/role` (`AssignmentAccessOut` slimmed; FE `MyAccess` type updated).
- 2026-10-23: WEB_API cloud engine now calls any OpenAI-compatible provider (DeepSeek default, `deepseek-flash`,
  thinking disabled default) in `app/services/ai_engine.py`; new env keys `WEB_API_KEY` / `WEB_API_BASE_URL` /
  `WEB_API_MODEL` / `WEB_API_THINKING` (`GEMINI_API_KEY` no longer used by the engine). Ollama unchanged.
- AI_ENGINE default flipped to `WEB_API` in `app/core/config.py` (was `OLLAMA`); Ollama stays selectable via `AI_ENGINE` env.
- Approval inbox: `aidaa_core.approval_task` gained dedicated nullable FK columns `plan_id`, `finding_id`, `report_id`,
  `settlement_id` alongside `record_type`/`record_id`, so the inbox links directly to its record instead of a sliced ID.
  `create_task` accepts the new columns and auto-derives finding/report/settlement from record_type; plan callers pass
  `plan_id` explicitly (record_id is a version_id there). `TaskOut` schema carries the new columns.
  Schema change: `sql/item3_approval_record_columns.sql` (psql one-liner, applied to the live DB; presence of the
  four columns verified via information_schema, 2026-10).
Realisation settlement is now runnable: `app/services/settlement.py` + two routes in the realisation router
(`GET|POST /assignment/{id}/realisation/settlements`). Submitting an auditor's settlement upserts
`realisation_settlement` (open) and creates an approval_task (`settlement` step 1 = `finance_approve`,
`AIDAA.FINANCE`); the generic approval engine's decision runs `_on_settlement_task`, which settles the row
(approved) or keeps it open for resubmit (rejected). The step seed was appended to `aidaa_log_approval.sql`
(owner-approved) and applied. The service layer passed a live-DB smoke test covering submit -> pending +
balance snapshot, approve -> settled + 409 on re-submit, reject -> open -> resubmit -> approved.
Realisation feature (batch 1) is now runnable: `sql/aidaa_patch_05_realisation.sql` (applied to the database,
2026-10) adds `realisation_advance`, `realisation_cost` (amount is a GENERATED column = quantity x unit_rate) and
`realisation_settlement` (reserved for the settlement approval batch). Backend: `app/schemas/realisation.py`,
`app/services/realisation_{common,advance,cost,report}.py` and router `app/api/v1/aidaa/realisation.py` mounted
under `/api/v1/aidaa/assignment` (advances CRUD, cost CRUD, balance, variance; reads `audit.assignment.read` +
visibility, writes `audit.assignment.update` or `audit.assignment.logistics`). Limits: only active team members
(`assert_member`), only status issued/ongoing/finished (`assert_realisable`), components/locations root-scoped
(`assert_cost_ref`), balances and variance computed in SQL. Cross-subsidy reuses the trip leg `actual_cost`.
FE: `darkhive-fev2` types + `lib/api/aidaa/realisation.ts` + `AssignmentRealisationCard` with a "Realisasi" tab.
The service layer passed a live-DB smoke test (fixture inside a rolled-back transaction).
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
2. (Built 2026-10-24, owner test pending) Base location screen done (`/dashboard/aidaa/settings` "Lokasi Dasar"),
   auditor grade hints + home location already in the auditor form. Remaining: confirm the codes typed by the
   owner match the approved rate grades.
3. Exercise the whole realisation feature in the FE end to end (advances, costs, variance, settlement approval by Finance).
4. Flag budget lines above the SBM reference with a required reason.
5. (Built 2026-10-25, owner pass pending) AI helpers: library_improvement, team, expertise_extract + the
   one-column-per-grade SBM parser. Owner steps: run `sql/aidaa_patch_09_expertise_ai.sql` locally then on the VPS
   (after patches 06/07/08), restart the backend, then the browser pass over the four surfaces (details in
   "Written, NOT yet exercised").
6. (Built 2026-10-25, owner pass pending) Approval wiring (item 6 done): run
   `sql/aidaa_patch_08_change_requests.sql` locally then on the VPS, restart, then the browser pass -
   leader files a change on an issued assignment -> supervisor decides in Kotak Persetujuan -> fields
   applied; budget verification submit -> Finance decides -> strip updates. IAM matrix: FINANCE role
   holders need nothing new (inbox is global-role driven); supervisors must be active team members.
7. (Built 2026-10-24, owner pass pending) Korespondensi: run `sql/aidaa_patch_06_korespondensi.sql` locally,
   then on the VPS (endpoints error out until then), restart the backend, then the browser pass (doc-req
   lifecycle, interviews, BAP stance + the resolve-gate 409). Also confirm the IAM matrix gives auditee PIC
   roles `audit.finding.read` org-mapped (same mapping Monev needs).
8. Kuesioner (built 2026-10-24, owner test pending): run `sql/aidaa_patch_07_kuesioner.sql` locally
   then on the VPS (after patch 06), restart the backend, then the browser pass (flag a procedure,
   build ≤5 questions, leader batch issue, copy the public link, answer anonymously on /q/[token],
   PIC in-app entry, results, regenerate/close). AI helpers (creator + working-paper-from-answers)
   are deferred; see DECISIONS.md.
9. (Built 2026-10-25, owner pass pending) Global location tier: run `sql/aidaa_patch_10_location_master.sql`
   locally then on the VPS (after 09; do NOT rerun patch 03 afterwards — its backfill would claim the global
   rows), then `sql/sql_seed/seed_locations_indonesia.sql` (38 provinces + 514 kab/kota as global rows, safe
   to rerun), restart the backend, then the browser pass: locations page badge, a global row refuses
   edit/deactivate (403), and an SBM paste that matches a national row. Do NOT run the seed before patch 10
   (its global-tier INSERT needs the partial index).

## Known gaps
- Findings have no unit column.
- No file storage, documents are url or path metadata only. AI reads PDFs through `POST /documents/extract`
  (plain text fills `source_text`, nothing is stored); no looping above 30000 chars.
- Real daily allowance and lodging spending is not recorded.
- Each root needs an active at_cost component coded TRANSPORT, or a component chosen on every leg.
- The guessed ROLE_ACTIONS/BOUND/actions matrix in `services/roles.py` was removed (2026-10-25): no
  router enforced it and no consumer read `actions` (the FE gates buttons on assignment_role,
  is_auditee_pic and context permissions). Write gates live only in the routers;
  `GET /me/assignments/{id}/role` lost its `actions` field.
- Auditors without a grade match only rates with an empty grade list.
- **Trip AI is runnable but end-to-end not exercised**: `app/api/v1/aidaa/trip_ai.py` is mounted (`/assignment/{id}/ai/trip/drafts`),
  the frontend modal exists ("Usulan AI" on the trips tab), but the flow was not run against a live AI engine yet (2026-10).
- `GET /pka/{id}` is mounted but the frontend never calls it (the assignment list is enough).
  `PATCH /pka/{id}`, `PATCH /procedures/{id}` (text) and `PATCH /papers/{id}` are now used by the frontend.
- `sql/aidaa_patch_04_org_scope2.sql` has been applied to the database (2026-10): `auditor` and
  `ref_auditable_unit` now carry `root_org_id`, `uq_ref_auditable_unit_root_code` replaced the global
  `unit_code` unique constraint.
- `sql/aidaa_patch_05_realisation.sql` has been applied to the database (2026-10): the three realisation tables
  exist; `realisation_settlement` is filled by the settlement approval batch (submitted rows are open -> settled
  via an `AIDAA.FINANCE` approval task). The `settlement` approval step was added to the `approval_step` seed in
  `aidaa_log_approval.sql` and applied to the database.
- `sql/aidaa_patch_06_korespondensi.sql` is WRITTEN but NOT applied (2026-10): until the owner runs it
  (locally, then on the VPS) every Korespondensi endpoint 500s on missing tables, and `resolve_finding`
  would 409 on every responded finding (the gate query would fail; run the patch BEFORE testing).
- `sql/aidaa_patch_07_kuesioner.sql` is WRITTEN but NOT applied (2026-10): until the owner runs it
  (locally, then on the VPS, after patch 06) every Kuesioner endpoint 500s on missing tables; the
  public `/q/[token]` page and the BFF `/api/aidaa-public/[...path]` forwarder depend on it too.
- `sql/aidaa_patch_08_change_requests.sql` is WRITTEN but NOT applied (2026-10): until the owner runs it
  (locally, then on the VPS) every change-request endpoint 500s on the missing `assignment_change`
  table; the budget-verification flow does NOT need it.
- `sql/aidaa_patch_09_expertise_ai.sql` is WRITTEN but NOT applied (2026-10): until the owner runs it
  (locally, then on the VPS, after patches 06/07/08) the expertise extraction accept step (and the HR
  task handler) fails with 500 on the missing `ai_suggestion_id` column; generate and list still work.
- `sql/aidaa_patch_10_location_master.sql` is WRITTEN but NOT applied (2026-10-25): until the owner runs it
  `root_org_id` stays NOT NULL, so the national-tier seed and the read sweep do nothing useful. The seed
  `sql/sql_seed/seed_locations_indonesia.sql` (552 global rows) is WRITTEN but NOT run and must go AFTER
  the patch. Both SBM seeds now carry the partial-index ON CONFLICT predicate, safe on patched DBs only.
- `app/services/trip_ai.py` is 373 lines (cap 300) — pre-existing; split it before its next feature change.