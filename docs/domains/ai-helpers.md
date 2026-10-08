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
| sbm_draft | pasted PMK table to components, locations and DRAFT rates, record_type organization | sbm_ai |
| budget | plan budget lines, record_type plan | plan_budget_ai |
| trip_draft | visits and ticket legs, record_type assignment | trip_ai |

## SBM helper (sbm_ai)
- The owner pastes ONE annex table per draft. A code parser reads rows and amounts, a FIXED province map turns PMK spellings
  ("R I A U", "D.K.I. JAKARTA") into PROV-xx. AI only names columns (component code, name, calc_basis) and official groups (grade codes).
- Shapes tried in order: province (31, 30, 16), road (1), route (17), single national amount (3). Units OP, OH, Orang/Kali.
- Row numbers of 100+ have no dot. Page headers are ignored. Cut-off rows are skipped and listed. in_source marks amounts whose
  text exists in the source.
- Places match existing locations first (Kab. = Kabupaten, Kota/Kab. prefix kept). Unmatched places become CITY-<NAME>.
  A name matching several locations is skipped and reported.
- Accept creates missing components and locations and DRAFT rates (Finance submits, Board approves). Duplicates are skipped.
- Permissions: audit.costrate.create to generate and decide, audit.costrate.read for the model list.
- Not built: a parser shape for tables with one column per grade.

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