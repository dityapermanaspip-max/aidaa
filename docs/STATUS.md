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
- **Connection budget and CORS allow-list (2026-10-29, branch `upscale_readiness`)**: the engine
  pool is now `DB_POOL_SIZE=5` + `DB_MAX_OVERFLOW=10` (was 10 + 20), with `DB_POOL_TIMEOUT=10` so a
  saturated pool fails before the BFF's 180 s timeout and `DB_POOL_RECYCLE=1800` so proxies cannot
  hand out sockets they already closed. Five processes (IAM, AIDAA API, AIDAA worker, GRiMIS, HILDA)
  now ceiling at 75 of Postgres' 100 connections instead of 120. Same change in IAM, GRiMIS and
  HILDA, and the platform arithmetic + pgbouncer recipe live in
  `darkhive-bev2/docs/ops/connection-budget.md` (owner applies pgbouncer; no app change needed for
  the current single-worker setup). `allow_origins` comes from `CORS_ORIGINS` (comma-separated,
  default `http://localhost:3000`); `*` is not supported because credentials are enabled. Verified:
  defaults and an env override reflected in `engine.pool` and in the preflight response for this
  backend; AIDAA's 21 tests still pass.
- **Public questionnaire cap and an anonymous commit (2026-10-29, branch `upscale_readiness`)**:
  `POST /public/questionnaires/{token}` now commits. It used to return 201 and then lose the row when
  the request session closed, because the public router is the only write path without an audit
  entry and never called `db.commit()`; anonymous answers were never stored. The capacity check and
  the insert are now one statement guarded by a transaction-scoped advisory lock per questionnaire
  (`pg_advisory_xact_lock(hashtext(questionnaire_id))`), so two simultaneous submissions cannot pass
  `respondents_needed`: the second waits for the first commit, then inserts nothing and answers 409.
  The cheap pre-check after `get_questionnaire` stays as the fast path. The in-app PIC path uses the
  same service and therefore the same gate. Flood control stays at the edge:
  `docs/ops/nginx-rate-limit-public.md` has the `limit_req` recipe for `/api/aidaa-public/` and the
  backend public path (owner applies it on the VPS; the agent did not touch nginx). Four new tests in
  `tests/test_public_questionnaire.py` cover the cap, the SQL guard with a stale pre-check, the
  per-questionnaire lock and the router commit; the seeded chain stays inside the rollback
  transaction. NOT exercised in the browser or against nginx (2026-10-29).
- **Permission memoisation and authorisation tests (2026-10-29, branch `upscale_readiness`)**: the
  same IAM answers were recomputed five to nine times per request. `app/services/request_memo.py`
  caches them on the request's `Session` (`Session.info`), which `get_db` already scopes to one request
  and one user. Memoised: the callable orgs per permission (`deps_org`), the accessible roots
  (`audit_setting`), the caller's global roles and effective `audit.*` codes (`roles`). Assignment and
  team rows stay uncached because this app writes them inside requests. `resolve_root` no longer reads
  the roots unless a root is explicit; `get_root` derives the single root lazily. `pic_unit_orgs` is
  one recursive query for the whole unit list (a root-org PIC covers descendants), and
  `check_org_any_permission` resolves the record's org once instead of once per code.
  New suite `tests/` (`pytest.ini`, `conftest.py`, `test_auth_scope.py`, 17 tests) covers a global
  grant, an org grant with descendants, no grant, memo identity and request isolation, single-root /
  two-root 409 / pinned root, lazy and invalid `resolve_root`, multi-unit PIC in one query, and the
  any-of check; one test proves the PIC union in `get_my_access` does not write into the owner org's
  memoised set. Tests seed IAM rows and roll back; `python -m pytest -q` passes and leaves no rows
  (2026-10-29). NOT exercised in the browser.
- **List pagination (2026-10-29, branch `upscale_readiness`)**: every cross-record list takes `limit` and
  `offset` and ends its SQL with `LIMIT :lim OFFSET :off` through `app/services/paging.py`. Covered:
  assignments, plans, auditors, funding sources, library PKA, deviations, my tasks, auditor candidates,
  org options, the five AI draft/extract lists, cost components and cost rates. Reference lists
  (locations, audit types, units, org options, cost components) use a wide default of 1000 (cap 2000)
  because dropdowns read them whole; the rest default to 200 (= cap) until the frontend pager ships.
  The response stays a plain array, so no screen and no `aFetch` changed; another page exists while a
  page comes back full. List endpoints scoped to one parent (team, visits, legs, findings, PKA,
  procedures, reports, correspondence) stay unpaginated: the parent bounds them. Exercised locally
  against the real DB (every changed list called with `limit`/`offset`, truncation and offset verified;
  2026-10-29). NOT exercised in the browser.
- **Background job queue, patch 11 (2026-10-29, branch `upscale_readiness`)**: AI generation and PDF/OCR
  left the request thread. `sql/aidaa_patch_11_jobs.sql` adds `aidaa_core.job` and is **APPLIED locally**
  (2026-10-29); the VPS still needs it, and every AI/OCR endpoint fails there until it runs. The nine AI POSTs (pka/report/team
  suggestions, trip draft, library draft + improvement, expertise extract, plan budget, SBM draft) and
  `POST /documents/extract` now answer **202** `{job_id,status}`; `GET /jobs/{job_id}` (owner-scoped)
  carries the result, and the worker replays the same `iam.audit_log` row the router wrote. The worker is
  `python -m app.worker` (one per host; several processes are safe). New env key names only:
  `AI_DEADLINE` (default 120 s, caps the whole AI retry loop; raise it for a slow local Ollama),
  `SPOOL_DIR` (default `./spool`, API and
  worker must share it), `JOB_STALE_MINUTES` (30), `JOB_POLL_SECONDS` (1). The frontend `aFetch` follows
  the job, so no screen changed. Patch 11 is APPLIED on the local DB (2026-10-29; a real `doc.extract` job
  ran enqueue → claim → done → spool cleanup, and another user reads 404); the VPS still needs it.
- **Global location tier, patch 10 + national seed (2026-10-25)**: `ref_location` now holds TWO tiers in one
  table — `root_org_id IS NULL` = shared national master (BPS: 38 provinces + 514 kab/kota, read-only in the
  app) and `root_org_id = <root>` = the org's own rows, unchanged. DDL
  `sql/aidaa_patch_10_location_master.sql` (nullable root + two partial unique indexes; makes the two SBM
  seeds' `ON CONFLICT` targets partial-index aware — both seeds were updated for that). Read side: the
  locations list/get, auditor home, budget/realisation refs, base location and trip drafts accept global
  rows; SBM place matching is now two-pass (org rows first, then national, then a new org `CITY-` row; an
  exact name spelling wins over others, and a bare name that matches both the Kabupaten and the Kota row of
  the master resolves to the Kota row — owner decision 2026-10-25). WRITE side: editing/deactivating a
  global row answers 403; the owner reruns `sql/sql_seed/seed_locations_indonesia.sql` to update the master.
  FE: the locations page shows a Sumber badge (BPS/Organisasi) and locks Ubah/Nonaktifkan for BPS rows
  (MasterCrud gained the additive `editableRow`). Import check and `npx tsc --noEmit` pass; NOT exercised in
  the browser; place resolution verified against the real 552 rows (2026-10-25, see the known-gaps sweep
  note): bare names pick the Kota row, org rows win first, exact and "Kota Administrasi" spellings all
  resolve — 11/11. Patch 10 + the national seed are applied on the LOCAL DB (2026-10-25); the VPS still
  needs both.
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
  because patches 04/05 already exist) — applied on the LOCAL DB (verified 2026-10-25); the VPS still
  needs it before testing any of these endpoints there (it also backfills BAP
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
  Import check passes; NOT exercised in the browser yet; patch 06 applied locally (2026-10-25), VPS pending.
- **Kuesioner (2026-10-24)**: procedure-linked questionnaires. DDL = `sql/aidaa_patch_07_kuesioner.sql`
  (numbered 07; applied on the LOCAL DB 2026-10-25 — the VPS still needs it, after patch 06 there).
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
  Import check + `npx tsc --noEmit` pass; NOT exercised in the browser yet; patch 07 applied locally
  (2026-10-25), VPS pending.
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
  - **DDL `sql/aidaa_patch_09_expertise_ai.sql`** (adds `expertise.ai_suggestion_id` and widens the
    source CHECK) is applied on the LOCAL DB (2026-10-25); the VPS still needs it — generate and list
    work everywhere, but the ACCEPT step fails there with 500 until then.
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
- 2026-10-25 (go code, owner test pending): to-do 4 built — budget lines above the SBM reference are flagged
  and need a reason (rule in docs/domains/rates-and-budget.md): the plan budget AI modal carries a typed
  unit_rate with an "Di atas SBM" badge and a required Alasan textarea; accept re-checks server-side (422
  lists the offenders, otherwise the typed rate stands and the reason rides into budget_line.notes). Every
  other path keeps refusing typed unit_rates for SBM components. Service-layer smoke green
  (verify_over_ref.py): annotate + 422 + override-with-reason all pass.
- 2026-10-25 (fix batch): killed the province-code bug the sweep found (see known gaps) — seed column fix
  (`v.prov2`) + healing UPDATE + provinces ON CONFLICT, and a `'PROV-'`-tolerant `location_fits`; all
  applied and re-verified locally (fitting True everywhere, picker 4/4 candidates, 11/11 resolution).
- 2026-10-25 (go sql): patches 07 (kuesioner), 09 (expertise), 10 (location tiers) and
  `sql/sql_seed/seed_locations_indonesia.sql` applied to the LOCAL database through
  `scripts/apply_schema.py`, every file `--dry-run` first. Re-inspection verified:
  `ref_location.root_org_id` nullable, `uq_ref_location_org_code` + `uq_ref_location_global_code` present
  (old `uq_ref_location_root_code` gone), 552 global rows (38 provinces + 514 kab/kota, 514 parented), the
  org tier untouched (39 rows, 38 of them legacy PROV rows) and the 152 approved 2026 lodging rates intact.
  The VPS still has to run the same files.
- 2026-10-25 (same day): `scripts/apply_schema.py` ports HILDA's SQL runner to AIDAA —
  `python scripts/apply_schema.py --file sql/<file>.sql [--dry-run] [--yes]`: settings loaded through
  `app.core.config` (only `user@host/database` printed), one transaction, `--dry-run` rolls back, `--yes`
  skips the prompt, `--file` required because AIDAA has numbered patches and seeds instead of one schema
  file. The agent never runs it; the owner applies base files/patches/seeds with it (order in
  docs/02_DATABASE.md).
- 2026-10-25 (batch): the two remaining seeded approval steps are wired. `budget`/`finance_verify`:
  leader submits the issued/ongoing assignment's budget (`POST /assignment/{id}/budget-verification`,
  one pending at a time), `AIDAA.FINANCE` decides in the generic inbox, `GET` returns the latest
  task; approval/rejection are recorded as comments and lines may keep editing (no lock, resubmit
  allowed) - the latest task doubles as the verification state. `assignment_change`:
  `sql/aidaa_patch_08_change_requests.sql` (applied locally 2026-10-25; VPS pending) stages post-issue
  edits (dates, notes,
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
4. (Built 2026-10-25, owner test pending) Budget lines above the SBM reference are flagged and need a reason:
   the plan budget AI modal carries a typed unit_rate with an "Di atas SBM" badge and a required Alasan; accept
   re-checks server-side (422 lists the offenders, otherwise the typed rate stands and the reason rides into
   notes). Every other path keeps refusing typed unit_rates for SBM components.
5. (Built 2026-10-25, owner pass pending) AI helpers: library_improvement, team, expertise_extract + the
   one-column-per-grade SBM parser. Patch 09 is APPLIED locally (2026-10-25); still run it on the VPS, restart
   the backend there, then the browser pass over the four surfaces (details in "Written, NOT yet exercised").
6. (Built 2026-10-25, owner pass pending) Approval wiring (item 6 done): patch 08 is applied locally,
   still run `sql/aidaa_patch_08_change_requests.sql` on the VPS, restart, then the browser pass -
   leader files a change on an issued assignment -> supervisor decides in Kotak Persetujuan -> fields
   applied; budget verification submit -> Finance decides -> strip updates. IAM matrix: FINANCE role
   holders need nothing new (inbox is global-role driven); supervisors must be active team members.
7. (Built 2026-10-24, owner pass pending) Korespondensi: patch 06 is applied locally (tables verified
   2026-10-25); still run `sql/aidaa_patch_06_korespondensi.sql` on the VPS (endpoints error out there until
   then), restart, then the browser pass (doc-req lifecycle, interviews, BAP stance + the resolve-gate 409). Also confirm the IAM matrix gives auditee PIC
   roles `audit.finding.read` org-mapped (same mapping Monev needs).
8. Kuesioner (built 2026-10-24, owner test pending): patch 07 is APPLIED locally (2026-10-25); still run
   `sql/aidaa_patch_07_kuesioner.sql` on the VPS (after patch 06 there), restart, then the browser pass
   (flag a procedure,
   build ≤5 questions, leader batch issue, copy the public link, answer anonymously on /q/[token],
   PIC in-app entry, results, regenerate/close). AI helpers (creator + working-paper-from-answers)
   are deferred; see DECISIONS.md.
9. (Built 2026-10-25, owner pass pending) Global location tier: patch 10 + the national seed are APPLIED
   locally (2026-10-25; 552 global rows verified). Still run `sql/aidaa_patch_10_location_master.sql` then
   `sql/sql_seed/seed_locations_indonesia.sql` on the VPS (that order; do NOT rerun patch 03 afterwards —
   its backfill would claim the global rows), restart, then the browser pass: locations page badge, a
   global row refuses edit/deactivate (403), and an SBM paste that matches a national row.

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
- `sql/aidaa_patch_06_korespondensi.sql` is APPLIED locally (2026-10, tables verified 2026-10-25): the VPS
  still needs it — until then every Korespondensi endpoint 500s there, and `resolve_finding`
  would 409 there on every responded finding (the gate query would fail; run the patch BEFORE testing).
- `sql/aidaa_patch_07_kuesioner.sql` is APPLIED locally (2026-10-25): the VPS still needs it — until then
  every Kuesioner endpoint 500s there; the public `/q/[token]` page and the BFF
  `/api/aidaa-public/[...path]` forwarder depend on it too.
- `sql/aidaa_patch_08_change_requests.sql` is APPLIED locally (2026-10-25, `assignment_change` verified):
  the VPS still needs it — until then every change-request endpoint 500s there; the budget-verification
  flow does NOT need it.
- `sql/aidaa_patch_09_expertise_ai.sql` is APPLIED locally (2026-10-25): the VPS still needs it — until
  then the expertise extraction accept step (and the HR task handler) fails there with 500 on the missing
  `ai_suggestion_id` column; generate and list still work.
- `sql/aidaa_patch_10_location_master.sql` + `sql/sql_seed/seed_locations_indonesia.sql` are APPLIED locally
  (2026-10-25; `root_org_id` nullable, both partial unique indexes, 552 global rows verified): the VPS still
  needs BOTH in that order — never patch 03 after 10. The two SBM seeds now carry the partial-index ON
  CONFLICT predicate, live on patched DBs only.
- `sql/aidaa_patch_11_jobs.sql` is APPLIED locally (2026-10-29; 12 columns, `idx_job_queue` + `idx_job_user`
  verified, and a real `doc.extract` job ran end to end: enqueue → claim → text-layer extraction → `done`
  result → spool file deleted → another user reads 404). The VPS still needs it, **and** every API host
  needs `python -m app.worker` running — until then every AI/OCR endpoint answers 500 on the missing table.
- `app/services/trip_ai.py` is 373 lines (cap 300) — pre-existing; split it before its next feature change.
- **Province-code bug from the 2026-10-25 sweep — FIXED the same day (owner picked "both fixes")**: the seed
  now selects the province NAME (`v.prov2`, was the parent code `v.prov`) and carries a rerunnable healing
  UPDATE (recomposes `province` from `parent_location_id` for the 514 global kab/kota rows) plus the missing
  provinces-block ON CONFLICT, so rerunning the seed is truly idempotent. `budget_core.location_fits`
  resolves a stale `'PROV-...'` code through the global province row before comparing. Applied locally
  through the runner (dry-run first) and re-verified: fitting True for every tier pair, the rate picker
  returns 4 candidates for a GLOBAL Kota destination (0 before), resolution matrix 11/11, seed counts
  552/514/0, org tier 39 untouched. VPS needs no extra step: its first seed run fixes the data by
  construction. The runner also executes psql-style (no bind arguments) so a literal `%` no longer breaks it.
## 2026-10-28: security audit started (backlog: temp_security_backlog.md)
- Cross-app JWT trust review: the token spine was already at IAM parity (pinned decode, jti revocation, active user, token_version). The only finding: require_any_permission now validates org_id with the same UUID check as require_permission, so a garbage uuid answers 400 instead of a CAST 500.
- Deep audit done the same day, findings #2-#9 all fixed (see temp_security_backlog.md): upload read cap (#2), prompt data-only fences on pka/report (#3), anonymous answer text cap 2000 (#4), decide-path 409 for foreign features (#5), list-field caps in the AI schemas (#6), model-name cap (#7), approval_task dup-check advisory lock (#8), public link stops at respondents_needed (#9). Gate green after every number; the tracker rows carry the details.
