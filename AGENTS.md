# AIDAA backend: agent entry point

AIDAA is the audit application of the Darkhive platform (FastAPI, PostgreSQL, port 8002). Read in this order:

1. docs/00_RULES.md          how to work with the owner (HARD RULES, read first)
2. docs/01_OVERVIEW.md       what it is, how to run it, env key names, glossary
3. docs/02_DATABASE.md       sql files, conventions, org scope
4. docs/03_ARCHITECTURE.md   folders, layers, access rules
5. docs/STATUS.md            done, written but untested, to-do, known gaps
6. docs/DECISIONS.md         why things are the way they are (append only)
Load a domain file only when the task touches it: docs/domains/rates-and-budget.md, ai-helpers.md, trip.md, execution.md.

Hard rules (details in 00_RULES):
- Never read or create .env files. Never put secrets in chat or docs.
- Do not write code until the owner writes "go code".
- Ask the owner to paste a file before editing it. Never guess file contents.
- Do NOT modify IAM tables. Never edit sql/ or reference/ unless asked.
- Update docs/STATUS.md and docs/DECISIONS.md when work changes them.