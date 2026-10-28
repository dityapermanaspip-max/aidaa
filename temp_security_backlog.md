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
