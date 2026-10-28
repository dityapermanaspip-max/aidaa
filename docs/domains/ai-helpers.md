# Domain: AI helpers

## Common rules
- All engines go through services/ai_engine.py: generate_json(prompt, engine, model) returns (answer, engine, model_name).
  Engines OLLAMA and WEB_API (CLOUD and GEMINI read as WEB_API). Retries 429 and 503 up to 3 times, returns Google's error
  text, strips code fences. Ollama URL comes from .env only (anti SSRF). list_ollama_models() feeds the frontend dropdown.
- AI output is never written to real tables directly. It is stored in aidaa_ai.ai_suggestion, then a human accepts, edits
  or rejects (SuggestionDecision). Rows created from AI carry source = ai_suggestion and ai_suggestion_id.
- Pasted or source text is data, not instructions. AI never writes money amounts. Code computes, picks rates and builds lines.
- Each helper: schema, service, router, frontend modal or page. The final feature CHECK lives in patch 02.
- Gemini can answer 503 (busy). Retry helps. A lite model (for example gemini-2.5-flash-lite) is less busy.

## Built helpers
| Feature | Scope | Files |
|---|---|---|
| pka, report | assignment record_type | services/ai_suggestions.py, router ai.py |
| library_draft | pasted text to library PKA and procedures (max 30000 chars), code <type>-NNN per root | library_ai |
| sbm_draft | pasted PMK table to components, locations and DRAFT rates, record_type organization | sbm_ai (parse: sbm_ai_parse, accept: sbm_ai_apply) |
| budget | plan budget lines, record_type plan | plan_budget_ai |
| trip_draft | visits and ticket legs, record_type assignment | trip_ai |
| team | ranked roster shortlist for one assignment, VIEW-ONLY, record_type assignment | team_ai, stored via ai_suggestions |
| library_improvement | rewrite ONE library PKA (accept replaces the head row), record_type library_pka | library_ai_improvement |
| expertise_extract | pasted certificate text to pending expertise rows + one HR task, record_type auditor | expertise_ai |

## SBM helper (sbm_ai)
- The owner pastes ONE annex table per draft. A code parser reads rows and amounts, a FIXED province map turns PMK spellings
  ("R I A U", "D.K.I. JAKARTA") into PROV-xx. AI only names columns (component code, name, calc_basis) and official groups (grade codes).
- Shapes tried in order: province (31, 30, 16), road (1), route (17), single national amount (3). Units OP, OH, Orang/Kali.
- Row numbers of 100+ have no dot. Page headers are ignored. Cut-off rows are skipped and listed. in_source marks amounts whose
  text exists in the source.
- Places match existing locations first, then the shared national master (`ref_location.root_org_id IS NULL`,
  the BPS tier), then become CITY-<NAME> org rows (Kab. = Kabupaten, Kota/Kab. prefix kept). Matching
  compares the normalized code/name/city by equality; a name matching several rows of one tier is skipped
  and reported, except that an exact spelling wins, and a bare name that matches both the Kabupaten and the
  Kota row resolves to the Kota row (a bare name means the city proper; SBM rates are per province).
  Resolution is two-pass (org tier first) so org CITY- and national KAB- rows are never compared against each
  other for the same paste.
- Accept creates missing components and locations and DRAFT rates (Finance submits, Board approves). Duplicates are skipped.
- Permissions: audit.costrate.create to generate and decide, audit.costrate.read for the model list.
- Built (2026-10-25): a second table mode, `column_kind` 'grade'. ONE component; each amount column is one official
  grade (`grade_columns`: heading -> grade code, e.g. GOL_III); every rate carries a single-element grade list, one
  rate per grade column. The FE review page passes the whole output through on edit, so grade fields survive untouched.
- File split under the 300-line cap: `sbm_ai_parse.py` (code-only table reading + place matching) and `sbm_ai_apply.py`
  (the accept half, imported late in `decide_draft`); component-mode behavior is unchanged.

## Plan budget helper (plan_budget_ai)
- AI answers only on-site days per audited unit and a reason. Effort = library procedure hours / 8 per audit type.
- Per team member and per per_day_worked or per_night component, the rate is picked by the member's own grade and the unit's
  place on the plan start date. Constants in the service: TRAVEL_ALLOWANCE_DAYS = 1, TRAVEL_NIGHTS = 1.
  The practice is one daily allowance for travel days together. The owner doubts this is fair, change the constant if the rule changes.
- Members whose home location fits the unit get no travel lines. No fitting rate is status no_rate, several fit is manual.
  Both are skipped on accept. Tickets are never suggested here.
- Accept needs the plan's budget drafter (editable_plan) and writes lines into the draft version.
- Permissions: audit.budget.draft and audit.budget.read.

## Trip helper (trip_ai)
See docs/domains/trip.md.

## Team helper (team_ai)
- View-only by design (2026-10-25): the AI ranks candidates from the root's REAL auditor roster - active auditors of
  the root holding the IAM role AIDAA.AUDITOR (iam.active_user_roles), excluding the current team members, with
  verified skills and a count of open audits inside the assignment period. Every suggested id is validated against
  the same roster (an invented person is a 502); results are deduped and ordered by rank.
- Acceptance only records the decision (`ai_suggestions._APPLY["team"]` is a no-op) - the leader adds members through
  the normal team endpoints. Router: `POST /assignment/{id}/ai/team-suggestions` (audit.team.manage + leader role);
  list and decide reuse the generic routes (`feature=team`).

## Library improvement helper (library_ai_improvement)
- ONE pending improvement per library PKA (409 otherwise). The prompt receives the current head, its active
  procedures and the user instruction; the AI answers full procedure objects (procedure_text, expected_evidence,
  estimated_hours).
- Accept: a NEW library_pka head takes the next `<type>-NNN` code (same `_next_number` as drafts), the improved
  procedures are inserted on it and the OLD head is deactivated (its own procedures stay attached, mirroring the
  manual deactivate). Both heads are logged (log_status). Only an active head can be improved.
- Router (library_ai.py): `POST /library/pka/{id}/ai-improvement` + the GET list (`library_read`) and
  `POST /library/ai/improvements/{id}/decide` (`library_manage`). Root scope goes through `ref_audit_type`
  (library_pka has no root_org_id).

## Expertise extraction helper (expertise_ai)
- Owner-only: the auditor extracts their OWN credentials (`expertise_create` + `_assert_owner`, same rule as the
  manual create). The pasted text is certificate/decree/diklat text for one auditor; the AI answers up to 10 rows;
  sloppy dates are dropped (strict YYYY-MM-DD regex), never rejected wholesale.
- Accept: pending rows inserted with source 'ai_suggestion' + ai_suggestion_id (patch 09 adds the column and widens
  the source CHECK), then ONE approval task on the seeded step record_type 'expertise' step 1 'hr_verify'
  (global_role AIDAA.HR, no assigned user). Guard: the auditor must not already have a pending expertise task.
- The registered handler (`_on_expertise_task`) decides the WHOLE batch: every row sharing the ai_suggestion_id that
  is still pending becomes verified (approved) or rejected with the task note. `GET /expertise/{id}` feeds the
  approval-inbox link.

## Library draft part-loop (frontend, 2026-10-28)
- The library AI page feeds `createLibraryDraft` in PARTS for big PDFs: `darkhive-fev2/src/lib/aidaa/extractSlices.ts`
  splits the extracted text on the HALAMAN markers at the first of 8 pages / 300 non-blank lines / 28000 chars.
  The 30000-char `source_text` cap therefore describes ONE part, never the whole document; parts are separate
  suggestions accepted one by one, and the do-not-repeat prompt list (library titles) keeps parts from
  duplicating PKA. Nothing on the backend changed for this.

## Audit type description is the PRIMARY prompt directive (2026-10-28)
- Owner decision: instead of hardcoded per-kind prompt variants, the audit type's `description` drives the
  framing. Both draft prompts (`library_ai._draft_prompt`, `ai_suggestions._pka_prompt`) wrap it in a
  `=== AUDIT TYPE DEFINITION ===` block labelled PRIMARY (what the PKA must achieve, how procedures read,
  what the source text represents), the source text stays data-only, and the user's extra instruction is
  explicitly SECONDARY (the definition wins on conflict). A new audit kind (kebijakan, kepatuhan, kinerja,
  ...) is just a well-written description - zero deploys, zero DDL (`description` is a text column).
- Hygiene: `AuditTypeCreate/Update.description` caps at 4000 chars (it is injected into every prompt);
  the FE Jenis Audit form carries a briefing-style hint.