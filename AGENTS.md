\# AIDAA - AI Driven Audit Assistant (backend)



Sits on Darkhive IAM. Do NOT modify IAM. Same PostgreSQL database as IAM.

Stack: Python, FastAPI, SQLAlchemy raw SQL via text(), psycopg2, python-jose. Port 8002.

Auth: use the IAM token (same JWT\_SECRET\_KEY/JWT\_ALGORITHM), check iam.revoked\_tokens.

Permissions: code format modul.aksi, lowercase, dotted (example: audit.plan.read).

Use require\_permission / check\_org\_permission / log\_audit like grimis-bev2 (see docs folder).

Only references to IAM: org\_id and user\_id. No other foreign keys out of iam.



\## Schemas

\- aidaa\_core: ref\_auditable\_unit, ref\_audit\_type, ref\_cost\_standard, auditor, expertise,

&#x20; expertise\_document, library\_pka, library\_procedure, audit\_plan, assignment,

&#x20; assignment\_member, budget\_line, pka, exe\_procedure, working\_paper, finding, rekomend,

&#x20; audit\_report, approval\_step, approval\_task

\- aidaa\_log (append-only, never update/delete): team\_log, approval\_log, edit\_log,

&#x20; comment\_log, status\_log (has by\_ai flag)



\## Rules

\- audit\_plan status: planned, approved, ai\_planned, ai\_approved, finished.

\- Approval chain: team leader drafts -> finance verifies budget -> supervisor reviews -> head approves.

\- Nobody approves their own work.

\- One person = one role per assignment (unique person per assignment).

&#x20; The same person may hold different roles in different audits.

\- Conflict of interest (hard block): an auditor can never be on the audit of their own

&#x20; unit or its child units (walk the IAM org tree). Log blocked attempts in team\_log.

\- expertise starts pending; only counts after HR sets verified.

\- Auditee PIC sees only the assignment of their own unit.

\- Rekomend stays open until resolved; monitored beyond the audit end.



\## Roles

administrator, head audit unit, audit supervisor, audit team leader, audit team member,

auditee person in charge, audit unit HR, audit unit Finance, audit unit General Affairs.



\## Working style

One small task at a time. Show the plan first. Never touch files outside this folder.

