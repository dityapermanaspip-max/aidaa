# AIDAA backend security backlog (aidaa, port 8002)

Opened 2026-10-28 by the backend audit pass (after IAM `90039b1`). Cross-app JWT trust review first;
the deep repo audit is next. Statuses: todo -> in progress -> done -> verified.

## Cross-app JWT trust review (pattern across all three consumers)
- Decode is pinned (`algorithms=[JWT_ALGORITHM]`) everywhere; no algorithm-confusion surface. Verified.
- `jti` revocation, user-active check, `tv == users.token_version`, org-subtree permission SQL: verified
  at IAM parity — AIDAA's `deps_auth.py` is the reference consumer, no changes needed there.

| # | Finding | Severity | Effort | Disruption | Status |
|---|---|---|---|---|---|
| 1 | `require_any_permission` did not UUID-validate `org_id` — garbage answered a 500 via `CAST` failure while its sibling `require_permission` answers 400 | info | XS | none | done 2026-10-28 |

## Deep audit recon (read-only, 2026-10-28)

Gate passed: `python -c "import app.main; print('ok')"`. Verified clean, no action:

- Trust spine: decode pinned to `JWT_ALGORITHM`, `jti` revocation, user-active, `token_version` check;
  org-subtree permission SQL; org UUID guards; `_ORG_RESOURCES` / `SCOPED` table whitelists (table names
  never from input); `resolve_root` pins the active root; `public` is mounted without root scope,
  self-authenticates/token-gates, and only ever returns questionnaire text + bare counters.
- Route sweep: every endpoint carries a permission dep; layer-2 assignment-role checks on the write
  paths that need them; AI suggestion surfaces are team-only.
- SQL: all f-string SQL interpolates constants or whitelist maps; `_patch` (46 call sites) builds SET
  lists from Pydantic field names only. No eval/subprocess/pickle; no CSV export; one upload endpoint.
- AI: both provider hosts pinned (no SSRF); all 9 `generate_json` sites reviewed; request schemas cap
  `source_text` 30000 / `instruction` 1000; money is re-priced server-side (typed amounts never
  trusted, over-ceiling needs a server-checked reason); SBM apply writes DRAFT rates only; questionnaire
  token lifecycle clean (`gen_random_uuid`, regeneration invalidates instantly, 40h TTL).
- Approval engine: conditional-UPDATE claim (`AND status = 'pending'`) + self-decision block in place.
- Logs: every write path logs to `aidaa_log` (append-only) + `iam.audit_log`; anonymous submissions
  write no actor (`submitted_by` NULL) by design.

## Deep audit findings

| # | Finding | Severity | Effort | Disruption | Status |
|---|---|---|---|---|---|
| 2 | `doc_extract.extract_document` awaits `file.read()` — the whole upload hits memory before any size check (`MAX_BYTES` is defined but unchecked on this path); GRiMIS #6 twin. Fix: `read(MAX_BYTES + 1)` then reject | low | XS | none | done 2026-10-28 |
| 3 | `ai_suggestions.generate_pka` / `generate_report` interpolate DB-resident titles/finding lines bare into prompts — the other six AI builders fence data as "data only"; add the same qualifier (additive) | low | XS | none | done 2026-10-28 |
| 4 | `QuestionnaireAnswerIn.text_value` is uncapped free text on the ANONYMOUS public write — cap ~2000 chars | low | XS | none | done 2026-10-28 |
| 5 | Generic decide path 500s on features it doesn't route: `_AUTH[s["feature"]]` (ai.py) and `_MODELS`/`_APPLY[s["feature"]]` (ai_suggestions.decide) raise KeyError for e.g. an sbm/trip suggestion id; `.get` + clean 400/409 | info | XS | none | todo |
| 6 | AI/edited-output list fields unbounded: `SbmNaming.components`, `LibraryDraft.pkas`, `PkaSuggestion.pkas`, `TripNaming.visits`/`legs`, `PlanBudgetDraft.lines` — accept loops insert unbounded rows; add `max_length` caps | info | XS | none | todo |
| 7 | `model: Optional[str] = None` uncapped across AI request schemas (forwarded to the provider) — cap ~100 chars (can fold into #6) | info | XS | none | todo |
| 8 | `approval.create_task` duplicate check races: no unique index on pending `(record_type, record_id, step_id)`; `sql/` is frozen — owner-run patch or accept | info | S | none | todo |
| 9 | Public questionnaire accepts responses beyond `respondents_needed` while the link is valid (40h) — likely by design (walk-in paper replacement); propose accept | info | — | — | propose accept |

### Notes (no action)
- CORS allows `http://localhost:3000` with credentials — correct behind the BFF; the VPS origin is a
  deployment concern, not code.
- `public_token` is a UUID (unguessable); single-use in the regeneration sense.

## Notes
- `reference/` is a frozen historical copy of the IAM-era pattern (no `app/` import found; AGENTS forbids
  editing it). Not live code; left untouched.
- Deep-audit scope for next: public kuesioner surface (anonymous allowlist, submitted_by NULL), AI helper
  endpoints, plan-budget/trip rate ceilings, list pagination caps.

## Batch record (2026-10-28)
- `app/api/deps_auth.py`: `require_any_permission` gained the same org_id UUID guard as
  `require_permission` (`400 Invalid org_id`).
- Gate: `python -c "import app.main; print('ok')"` passed.
- Owner-side pending: browser pass, then the commit-push word.
