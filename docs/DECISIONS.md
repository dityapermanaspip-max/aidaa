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
- 2026-10: AIDAA owns a generic PDF extractor, `app/api/v1/aidaa/doc_extract.py`
  (`POST /api/v1/aidaa/documents/extract`), mirroring GrIMIS `app/routers/doc_extract.py` instead of reusing
  IAM's org-import OCR. Reason: IAM's endpoint is gated by the global IAM permission `iam.org.import` (grant
  drift for AIDAA users) and couples AIDAA to IAM's URL; the "one generic extractor per app" pattern reads a
  PDF and returns plain text that fills the `source_text` of its own AI helpers (SBM AI, library AI drafts).
  No file storage, no schema change, no new permission: the endpoint touches no audit data, so authentication
  alone is enough, and each helper keeps its own write permission. OCR constants live in `app/core/config.py`
  (`TESSERACT_CMD` only needed if tesseract is not on PATH).
- 2026-10-23: The WEB_API cloud branch of `app/services/ai_engine.py` now calls any OpenAI-compatible chat API
  (`POST {WEB_API_BASE_URL}/chat/completions`, Bearer auth, `response_format: json_object`) instead of Gemini
  REST. Default base `https://api.deepseek.com`, model `deepseek-flash`, DeepSeek thinking disabled by default
  (`WEB_API_THINKING` env). New env keys `WEB_API_KEY` / `WEB_API_BASE_URL` / `WEB_API_MODEL` / `WEB_API_THINKING`;
  `GEMINI_*` stays in config but is unused by the engine. Reason: `generativelanguage.googleapis.com` is not
  reachable from the Tencent Cloud deployment, and the OpenAI-compatible shape keeps any future provider a pure
  `.env` switch. The retry 429/503 + real-error-text pattern and `_clean_json` fence stripping are unchanged.
- 2026-10-24: `audit_setting.base_location_id` (patch 01 column, until now only read by the trip helper) is set through
  `PUT /master/audit-setting`: both `iau_org_id` and `base_location_id` are optional, at least one is required, an
  explicit null clears the base location. `set_base_location` refuses until the setting row exists (409, IAU first)
  and validates the location is active inside the active root (`ref_location.root_org_id` is NOT NULL since patch 03).
  The IAU upsert does not touch `base_location_id`. Reason: one settings screen per root; the trip origin rule stays
  unchanged (auditor home first, the base location second, per docs/domains/trip.md).
- 2026-10-24: Auditor grades are suggested from data, not a master table: `GET /master/cost-rates/grade-codes` returns
  the distinct grade codes of the root's approved rates (`audit.costrate.read`). Reason: no grade master exists and
  `auditor.grade` is free text whose typo means "no rate"; approved-only because budgets price with approved rates only.
- 2026-10-24: The plan budget AI modal fixes its `no_rate`/`manual` lines through
  `GET /master/cost-rates/candidates` (approved + active + valid on the plan start, filtered and ordered with the same
  `location_fits` ordering as `_pick_rate`: exact place, origin match, fitting listed grade, cheapest). Reason: whatever
  the human picks must survive `_apply`'s `resolve_price` re-price, so the FE may offer only server-approved fits;
  hand-typed amounts are never trusted, same decision as the trip AI modal. Read-only, same permission as the rate
  list, no schema change.
- 2026-10-24: Monev Temuan is read-only and reuses the surat tugas VISIBILITY RULE instead of introducing a new
  permission (`GET /monitoring/temuan`, `audit.finding.read`; global mapping = all rows, else owner-org match or
  unit-org match for non-draft assignments). Reason: the owner wants the view usable by people outside the
  internal audit org (auditee PICs), and PIC access is already defined at the assignment level; a separate
  monitoring permission could not be seeded (sql/ is off-limits) while reusing this rule keeps one definition of
  "which assignments may I see". Rows are deliberately slim - no description/criteria - because the audience is
  wider than the finding edit screens.

## 2026-10-24 (continued): Korespondensi (doc requests, interviews, berita acara penyampaian notisi)

- DDL is `sql/aidaa_patch_06_korespondensi.sql`, NOT patch 04. Reason: the owner asked for "sql fix batch 4"
  but patches 04 (`org_scope2`) and 05 (`realisation`) already exist, so the next free number is 06. It is
  safe to rerun and backfills a BAP skeleton (`BAP-<finding_no>`, non-conflicting INSERT ... ON CONFLICT
  DO NOTHING) for every finding already communicated or further along. `bap_no` is NOT unique on purpose -
  numbers repeat across assignments (BAP-F-001 is valid in two surat tugas); `finding_id` carries the
  uniqueness (one BAP per finding).
- Interview `start_time`/`end_time` are varchar(8) display strings, not TIME columns. Reason: they are shown
  verbatim (typed "09:00"), and a TIME column would force cast/adapter handling in the write helpers whose
  only purpose would be that display.
- Permission reuse, no new codes (IAM seeding is off-limits from here): doc-req manage = `audit.assignment.update`
  with the team member/leader role while the assignment is workable (writes stop when the audit ends, which also
  stops PIC submissions); PIC submit = `audit.finding.respond` via authorize_pic with an extra row-level check
  that the doc request belongs to a unit whose org the caller is auditee PIC of (an assignment can audit two
  units of DIFFERENT orgs; authorize_pic alone would let a PIC of one org submit for the other's unit);
  interviews = the logistics wrapper (either `audit.assignment.update` or `audit.assignment.logistics`) plus the
  team role; BAP create/result = `audit.finding.communicate` with the leader/supervisor role; every read =
  authorize_view on `audit.finding.read`, and PIC lists are filtered to their audited unit orgs in SQL.
- BAP writes deliberately SKIP the assignment-workable check. Reason: the berita acara is post-audit
  correspondence - results may need recording after fieldwork ends (assignment finished/cancelled), unlike doc
  requests and interviews which belong to the audit itself.
- THE RESOLVE GATE: `resolve_finding` (responded -> open) now 409s unless `finding_bap.stance_result` is set.
  Reason: the owner's rule - the temuan is finalized only after the auditee expressed agreement (or not) within
  the given days, formally recorded in the berita acara. The backfill means existing communicated+ findings
  already HAVE a skeleton; each team must still record the stance result. Findings in 'closed' are unaffected.
- BAP is created manually at/after communicate (never auto-inserted by `communicate`), and the BAP list ships
  one flat row per communicated+ finding with nullable BAP fields so the UI can show which temuan still lack
  their berita acara.

## 2026-10-24 (continued): Kuesioner design (owner decisions, NOT built - awaiting "go code" + DDL patch 07)

- The questionnaire is a SUB-BRANCH of a PKA procedure: exactly ONE questionnaire per procedure
  (UNIQUE procedure_id). Want more questionnaires in an assignment? The owner forks more procedures
  (the PKA already supports adding procedures) - no questionnaire tree, no assignment-level ad-hoc surveys.
- Four question kinds only (v1): single choice (up to 5 options), multi select (up to 5 options),
  free text, and a numeric scale of 6 points (1-6). Choices live on the question; single answers store the
  chosen option index, multi answers store indexes, scale stores 1..6, text stores the text.
- SEVERAL respondents fill one questionnaire. Respondent identity is NOT the login identity: every response
  opens with the mandatory CONTROL GROUP at the start - name, position (jabatan), age, last degree, and
  male/female - owned by each response row (columns, rendered as the first section of the entry form).
  The AIDAA user who enters/submits the set is still logged separately (submitted_by).
- Evidence first: results aggregate for the team (counts/percentages per option, scale averages, raw text)
  and stay documentation - they NEVER auto-create findings or working papers.
- AI is deferred twice over: an AI questionnaire creator (draft questions from procedure title/objective)
  and AI help turning answers into a working paper are LATER batches; the working-paper loop needs real
  questionnaire samples from the owner (same pattern as SBM/Lampiran parsing).
- Nothing exists yet: no DDL, no endpoints, no UI. Planned DDL patch 07 (assignment_questionnaire,
  questionnaire_question, questionnaire_response, questionnaire_answer); submission reuses the PIC
  gate (audit.finding.respond + authorize_pic + own-unit row check) like doc requests.
- 2026-10-24 REFINEMENT (owner, supersedes parts above where they conflict): the scale is a per-question
  choice of 4, 5 or 6 points (not a fixed 1-6; answers validated against the chosen scale_max). A
  questionnaire carries AT MOST 5 questions (hard cap - a procedure should not need more; fork procedures
  for more). `needs_questionnaire` is a flag on the per-assignment procedure copy; the team toggles it and
  the team leader is accountable that every procedure marked as needing a questionnaire has its questions.
  Issuing to the PIC is a BATCH: one action issues every ready questionnaire at once and the backend
  refuses (422) while any marked-needed procedure still lacks questions - the leader's "ensure" step made
  mechanical. The leader sets `respondents_needed` per questionnaire (default 1); the PIC spreads the
  questionnaire as a PUBLIC LINK (token-based, no login) and both sides watch a counter of finished
  responses vs target; the PIC can also fill a set in-app. The public link is planned as AIDAA's FIRST
  unauthenticated route: a token GET + POST in a new public router mounted WITHOUT auth/root dependencies;
  the public surface answers only progress counts, aggregated results stay behind the logged-in API.
  Public entries keep submitted_by NULL; identity comes solely from the control-group block.
  Default (following the doc-request rule, flag for confirmation): the link stops accepting once the
  assignment leaves workable status; the team can also close the link manually.
- 2026-10-24 FINAL refinement (owner): the public token EXPIRES 40 hours after generation (a module
  constant, tweakable in one place); a regeneration (team or the PIC of the unit) issues a fresh token
  and restarts the 40-hour window - the old token dies instantly because the questionnaire stores ONE
  live token, no token history. Regenerating is allowed while the questionnaire is issued and the
  assignment is still workable. Responses are accepted without a target cap; the counter shows the raw
  pair (e.g. "12/5" with a target-reached marker). Owner confirmed the 5-question cap ("easier for the
  AI too" - the later AI questionnaire creator also works within it). The workable-end stop stands as
  the default. Design is COMPLETE; still awaiting the owner's "go code" before any DDL/code is written.
- 2026-10-24 Batch 07 implemented (after the owner's "go code"): `sql/aidaa_patch_07_kuesioner.sql`
  (idempotent ALTER + 4 new tables), `app/services/execution/questionnaires.py`, router
  `app/api/v1/aidaa/questionnaires.py` (mounted ROOT_SCOPED) and the first unauthenticated router
  `app/api/v1/aidaa/public.py` mounted WITHOUT ROOT_SCOPED (verified `resolve_root` depends on
  `get_current_user`, so the public router declares only `get_db`). The public surface returns only
  questionnaire text/questions + progress counts; anonymous submissions never write log_audit and
  keep submitted_by NULL. The needs_questionnaire toggle reuses the procedure-edit gate family
  (procedure not skipped, status planned/in_progress); the batch issue is ROLES_LEAD. The FE public
  page `/q/[token]` lives OUTSIDE the `(app)` auth group and talks through a new no-auth BFF
  forwarder `src/app/api/aidaa-public/[...path]` (the existing aidaa proxy 401s without a dh_token
  cookie), noted in the FE docs/security.md.
- 2026-10-25: The guessed ROLE_ACTIONS/BOUND matrix in `services/roles.py` is deleted.
  `get_my_access` (`GET /me/assignments/{id}/role`) now returns only `assignment_role`,
  `is_auditee_pic` and `global_roles`, keeping the existing scope probe (403 when the caller holds no
  `audit.*` permission on the owner org or their PIC unit orgs). Reason: no consumer existed — every FE
  assignment card gates on `assignment_role`, `is_auditee_pic` and context permissions — and several
  listed codes were never enforced by any router while the actually enforced ones were not all listed;
  a second copy of the routers' gate matrix could only drift. The same sweep verified there is no route
  clash around `/assignment/{id}/funding` (budgeting is mounted at the bare API prefix and no other
  `/assignment`-prefixed router defines funding routes) and that the library_ai duplicate
  `GET /library/ai/drafts` no longer exists.
- 2026-10-25: The last two unwired seeded approval steps went live. `budget` ('finance_verify',
  AIDAA.FINANCE): the leader submits the assignment budget for verification while the assignment is
  issued/ongoing; budget lines keep editing, verification is a recorded checkpoint (comment), and
  resubmission after edits is always possible (no hard lock) - the LATEST task doubles as the
  verification state, nothing else is stored. `assignment_change` ('supervisor_approve' as
  assignment_role): patch 08 (`assignment_change` table, payload jsonb) stages post-issue edits and
  ONLY an approved task applies them through the same body as the draft PATCH
  (`_apply_assignment_edit`), so date/unit/conflict guards and the edit-log trail are shared; the
  requester can never decide their own request (engine rule; the requester is excluded when the
  reviewer is resolved); ONE pending request per assignment; rejected and returned both end the
  request (file a new one); cancelling is the requester's, while still pending. Filing is
  leader-only; extra units re-run unit and conflict checks exactly like drafts.

## 2026-10-25 (continued): AI helpers batch - SBM grade mode, team, library_improvement, expertise_extract

- SBM one-column-per-grade tables are parsed by a SECOND MODE of the same helper, not a new endpoint:
  `SbmNaming`/`SbmDraft` gained `column_kind` ('component' | 'grade') and `grade_columns` (heading -> grade code,
  UPPER_SNAKE_CASE). In grade mode the AI names exactly ONE component and one grade code per amount column; each
  rate carries a single-element grade list and accept still writes only DRAFT rates (Finance submits, Board
  approves). Reason: such annexes are one cost priced per grade column; a mode keeps one review surface and the
  component mode untouched. `sbm_ai.py` was split under the 300-line cap (`sbm_ai_parse.py`, `sbm_ai_apply.py`).
- The team helper is VIEW-ONLY by design: it ranks candidates from the real roster (active auditors of the root
  holding the AIDAA.AUDITOR IAM role through iam.active_user_roles, current team members excluded, with verified
  skills and open-audit counts in the period), validates every suggested id against that roster (an invented person
  is a 502) and only records the decision on accept. Reason: team composition stays the leader's judgement call;
  the roster carries the verified-skills and workload facts the suggestion needs.
- Expertise extraction is OWNER-ONLY (the auditor extracts their own credentials, `_assert_owner` +
  `expertise_create`, same rule as the manual create) and routes verification through the SEEDED step record_type
  'expertise' step 1 'hr_verify' (AIDAA.HR global role): accept inserts the pending rows with source
  'ai_suggestion' + ai_suggestion_id and opens ONE task for the whole batch; the registered handler verifies or
  rejects every still-pending row of that batch, so HR sees one row, not ten. Reason: verification stays in the
  generic approval inbox and the requester-cannot-decide rule holds; AI dates are kept only when they match
  YYYY-MM-DD (sloppy dates are dropped, not rejected).
- Library improvement REPLACES the head row on accept: a NEW library_pka takes the next `<type>-NNN` code with the
  improved procedures, the old head is deactivated (its procedures stay attached - same as the manual deactivate)
  and both heads are logged. Reason: procedure history and code stability; root scoping goes through
  ref_audit_type because library_pka has no root_org_id.
- Hard guards keep the queues small: ONE pending improvement per library PKA and ONE pending extraction task per
  auditor (both 409).
- New DDL patch 09 (`sql/aidaa_patch_09_expertise_ai.sql`, idempotent): `expertise.ai_suggestion_id` +
  'ai_suggestion' added to the source CHECK. The feature CHECK already knew all the new feature names (patch 02),
  so no other DDL was needed. The acceptance of a suggestion whose batch spans rows is logged per row
  (log_status) and the HR decision per batch as a comment.

## 2026-10-25 (continued): Global location tier in ref_location (BPS national master)

- ref_location stays ONE table with two tiers: `root_org_id IS NULL` = shared national master (BPS provinces
  and kab/kota; read-only in the app, updated by rerunning the seed) and `root_org_id = <root>` = the
  organisation's own rows, untouched. Reason: one table keeps every FK valid (rates, visits, trip legs,
  units, auditor home, base location) while org rows keep today's behavior. Supersedes part of the 2026-09
  entry "Master data is scoped per root org": locations now read the org's rows FIRST and fall back to the
  shared national tier.
- Patch 10 only relaxes `root_org_id` to NULL and replaces `uq_ref_location_root_code` with two partial
  unique indexes: org tier `(root_org_id, location_code) WHERE root_org_id IS NOT NULL` and global tier
  `(location_code) WHERE root_org_id IS NULL`. A code may exist in BOTH tiers; resolution reads the org row
  first, so that is safe. Warning: do NOT rerun patch 03 after patch 10 — its backfill would claim the
  global rows. The two SBM seeds got the matching `WHERE root_org_id IS NOT NULL` predicate in their
  `ON CONFLICT` so they keep working after the index swap.
- Global rows are app-read-only WITHOUT a new IAM permission: update/deactivate pre-check the row tier and
  answer 403; the owner updates the master by rerunning `sql/sql_seed/seed_locations_indonesia.sql`
  (source: emsifa/api-wilayah-indonesia v2, Kepmendagri 2025 ed.). No yearly refresh — append-style, the
  seed is rerun only when a province or kab/kota appears (the 2022 Papua provinces are already included).
- Codes: provinces reuse the exact seed_sbm_2026 list (PROV- + ISO 3166-2 suffix, name "Provinsi X");
  kab/kota codes are KAB-/KOTA- + uppercase name (KOTA-BANDUNG); location_name keeps the official
  "Kabupaten/Kota Administrasi X" spelling and city holds the bare name.
- SBM place resolution became two-pass (org rows first, then national) instead of one pass over a merged
  list: one pass makes an org CITY- row and the global KAB- row of the same place ambiguous for no reason.
  When one tier still matches several rows, the row whose name is spelled EXACTLY as in the table wins.
- Owner decision (2026-10-25): a bare name ("Bandung") that matches BOTH the Kabupaten and the Kota row of
  the national master resolves to the KOTA- row instead of being skipped — a bare name means the city
  proper, and SBM rates are per province so the pick only names the place. Matching compares the
  normalized code/name/city by equality (never a substring), so "Kab. X"/"Kota X" spellings keep hitting
  their exact row, and org rows keep winning first (an org CITY- row means the national tier is never
  consulted for that place).

## 2026-10-25 (continued): province column spells the province NAME

- Verified by the post-seed sweep: the national seed had written the kab/kota rows' `province` column as the
  PARENT CODE (`'PROV-JB'`) - the SELECT picked `v.prov` while the province name sat unused in `v.prov2` -
  while PROV rows (both tiers) and org rows carry the name. `budget_core.location_fits` compares this column
  as text, so a destination resolved to a GLOBAL kab/kota row fitted NO provincial rate (breaks the budget AI
  picker, list_candidates, resolve_price) and the SBM province narrowing never narrowed.
- Fix (owner picked "both"): the seed selects `v.prov2` and gained a rerunnable healing UPDATE that recomposes
  `province` from `parent_location_id` for the global kab/kota rows; the provinces block got the missing
  `ON CONFLICT` so the seed is truly rerunnable. Go rule: the `province` column of every `ref_location` row
  carries the province NAME; belt-and-braces, `location_fits` resolves a stale `'PROV-...'` code through the
  global province row before comparing. Verified after applying: fitting True everywhere, the rate picker
  returns 4 candidates for a global Kota destination (0 before), resolution matrix 11/11, 552/514/0 counts.
- Runner note (same sweep): `scripts/apply_schema.py` now executes the file through the DBAPI cursor with no
  bind arguments (psql semantics) - SQLAlchemy's always-present empty mapping made psycopg2 treat a literal
  `%` anywhere in a file (LIKE 'PROV-%', even in comments) as a placeholder and fail.

## 2026-10-25 (continued): SQL runner through the app's database settings (scripts/apply_schema.py)

- Port of HILDA's runner: `scripts/apply_schema.py` loads the repo `.env` through `app.core.config`, prints
  only `user@host/database`, and applies ONE `--file` in one transaction; `--dry-run` executes and rolls
  back; `--yes` skips the confirmation prompt. Difference versus HILDA: `--file` is REQUIRED here because
  AIDAA has no single schema file — base files, numbered patches and seeds with a strict order
  (docs/02_DATABASE.md), never patch 03 after patch 10.
- Reason: a repeatable runner without duplicated connection settings or hand-reading `.env`; the API engine
  is the single source of truth. The agent still writes nothing: the owner applies the files.

## 2026-10-25 (continued): the plan budget AI modal is the one door above the SBM reference (to-do 4)

- Built: a budget line whose typed unit_rate exceeds the approved rate it was priced from (the SBM ceiling)
  is flagged `over_ref` and needs a reason. The flag lives on the AI draft line (`PlanBudgetLine` gains
  `over_ref`, `reason`, `ref_amount`); generate fills `ref_amount` from the rate, and decide's
  `_annotate_above_ref` RE-computes the flag server-side from the rate table - a client-sent flag is never
  trusted.
- Accept with a missing reason -> 422 listing the offenders ("COMPONENT - user: unit_rate X above reference
  Y"). Accept with a reason -> resolve_price still prices from the approved rate, then `_apply` overrides the
  typed unit_rate in and stores the reason in `budget_line.notes` (no DDL needed). Every other path keeps
  refusing typed unit_rates for SBM components (resolve_price), so the plan budget AI modal is the ONE
  sanctioned door above the ceiling.
- Verified by service-layer smoke inside rolled-back savepoints: a clean line is unflagged with `ref_amount`
  set; above without reason -> 422; above with reason -> allowed, and the overridden insert carries the typed
  unit_rate plus notes=reason. The end-to-end accept flow still waits for a real plan in the local DB
  (0 plans/assignments today); service-layer, not token, probes are the established pattern.
- 2026-10-28: require_any_permission validates the org_id parameter the same way require_permission does (UUID check, 400 on garbage) instead of letting CAST(:org_id AS uuid) fail as a 500. Behaviour is otherwise unchanged.

## 2026-10-28 (continued): approval_task duplicate check made race-safe with an advisory lock (audit #8)

- Two concurrent submissions of the same record/step could both pass the check-then-insert dup check and
  create two pending tasks for the same step. The proper fix is a unique partial index on
  `approval_task(record_type, record_id, step_id) WHERE status = 'pending'`, but `sql/` is frozen - so the
  fix is in code: `create_task` takes a transaction-level advisory lock
  (`pg_advisory_xact_lock(hashtext('aidaa.approval_task'), hashtext(rt:rid:sid))`) BEFORE the dup check.
  The second caller queues, then sees the dup and answers 409. The lock releases at commit; the hash key
  only serializes, it never blocks unrelated records for long (HTTP transactions are short).
- If a DDL batch is ever opened for this repo, adding the partial unique index is still the belt-and-braces
  end state; the advisory lock alone is correct and needs no migration.

## 2026-10-28 (continued): the questionnaire link stops at respondents_needed (audit #9)

- Until now an issued link kept accepting responses for its whole 40h life, however many came in. Now
  `submit_response` answers 409 once `responses_count >= respondents_needed`. The knob is deliberate: the
  LEADER raises `respondents_needed` on the questionnaire and the link reopens - so "closed" is never
  permanent and no walk-in respondent is turned away by accident when the unit quotes a low target.
- Applies to the anonymous public link AND the in-app PIC path (a response is a response). Two truly
  simultaneous submissions can overshoot the cap by one (the check is before the insert and no unique
  index can express "at most N rows" here); that residual race is accepted - the cap is a sanity gate,
  not an accounting control.

## 2026-10-29: AI and OCR leave the request thread (job table, not Redis)

- The audit found one AI call could hold a request thread and a pooled connection for 906 s (3 x 300 s
  attempts plus the sleeps) while the BFF gave up at 180 s. AI generation and PDF/OCR now insert an
  `aidaa_core.job` row and answer 202; `python -m app.worker` runs them.
- PostgreSQL is the queue (`FOR UPDATE SKIP LOCKED`, `locked_at` reclaim after `JOB_STALE_MINUTES`)
  because the volume is a few dozen jobs a day and the database already owns the suggestion rows. A
  broker would add an operational component for no gain at this size.
- The API change is absorbed in one place: the frontend `aFetch` detects `{job_id}` and polls
  `GET /jobs/{id}` with backoff, returning `job.result`, so no screen changed.
- The worker replays the audit entry stored in the job payload (action, target, metadata) with the same
  engine/model the service wrote, so `iam.audit_log` is identical to the synchronous flow. A failed job
  keeps its error on the row; there is no automatic retry - the user presses again.
- `AI_DEADLINE` (120 s) bounds the whole retry loop, not one attempt. A slow provider now answers 504
  and frees the thread instead of outliving the request.
- The upload is spooled to `SPOOL_DIR` and deleted by the worker in a `finally`. The spool is scratch
  space (not storage), but the API and the worker must share the directory: same host, or a shared volume.
