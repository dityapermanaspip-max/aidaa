# VPS update, 2026-11-17: what to pull and what to run

Branch for every repo: `demo-ai`. Nothing here changes `main`. The commands below are written for the
VPS; paths and the way you restart services are yours, so adjust them. Nothing was run on the VPS from here.

## 1. Pull

```
git -C <repo> fetch origin
git -C <repo> checkout demo-ai
git -C <repo> pull --ff-only origin demo-ai
```

Repos with new commits in this update: `aidaa`, `airchivist-bev3`, `darkhive-fev2`.
The other four (`darkhive-bev2`, `grimis-bev2`, `hilda-be1`, `invitro-be1`) have nothing new.

## 2. AIDAA (`aidaa`): location fix + demo seed

### 2a. Fix: a unit or a cost rate could not use a national (BPS) location
Code only, no SQL. Restart the AIDAA backend after the pull. Then try: Master > Unit > add a unit and pick a
national city (for example Kota Bandung) as its location. It used to answer "Location not found".

### 2b. Demo data for "Instansi Demo" (`sql/sql_seed/seed_demo_instansi.sql`)
Needs the base files, patches 01 to 13 and `seed_locations_indonesia.sql` already applied (they are on the VPS if
AIDAA works there). It finds the organisation by its official name, `Instansi Demo`, and stops with an error if
there is not exactly one active root organisation with that name. If yours is named differently, change the name in
step 0 of the file before running.

Run from the `aidaa` folder, with the same database settings as the API (the script prints `user@host/database`,
check it is the VPS database):

```
python scripts/apply_schema.py --file sql/sql_seed/seed_demo_instansi.sql --dry-run --yes
python scripts/apply_schema.py --file sql/sql_seed/seed_demo_instansi.sql --yes
```

First run adds: 4 audit types, 8 cost components, 8 approved demo rates (placeholder amounts, not from a PMK),
3 funding sources, 5 library PKA with 15 procedures. It also adds one auditor per user who already holds
`AIDAA.AUDITOR` under the organisation.

**Units come in a second run.** A unit needs an Internal Audit Unit (IAU) to exist, and only the app sets that:

1. In AIDAA open Pengaturan Audit and designate the IAU (an organisation of the audit team).
2. Run the same file again. It adds one unit per active organisation outside the IAU, and nothing else
   (a rerun never duplicates).

The script prints no notices, so a skipped part is silent. Check what exists:

```sql
SELECT (SELECT count(*) FROM aidaa_core.ref_audit_type    WHERE root_org_id = r.org_id) AS types,
       (SELECT count(*) FROM aidaa_core.ref_cost_component WHERE root_org_id = r.org_id) AS components,
       (SELECT count(*) FROM aidaa_core.library_pka        WHERE root_org_id = r.org_id) AS pka,
       (SELECT count(*) FROM aidaa_core.auditor            WHERE root_org_id = r.org_id) AS auditors,
       (SELECT count(*) FROM aidaa_core.ref_auditable_unit WHERE root_org_id = r.org_id) AS units
FROM iam.organizations r WHERE r.org_code = '<root org code of Instansi Demo>';
```
Expected after both runs: 4, 8, 5, one per AUDITOR holder, one per non-IAU organisation.

Good to know:
- Auditor grades rotate over `ESELON_II`, `ESELON_III_GOL_IV`, `ESELON_IV_GOL_III_II_I`. The home location of auditors
  and units is the national Jakarta Pusat row. Edit both in Master > Auditor and Master > Unit.
- The demo rates are one national amount per grade, valid 2026 and 2027. Real SBM rates for this organisation
  overlap them until the demo rates are deactivated.
- If the seed fails halfway nothing is kept (one transaction). Fix the message and run it again.

## 3. AIRCHIVIST (`airchivist-bev3` + `darkhive-fev2`): upload, review, AI settings
Only if AIRCHIVIST runs on that server. No SQL is needed: the tables already exist.

Backend:
1. `pip install -r requirements.txt` (new: `pymupdf`, `pytesseract`, `Pillow`).
2. Install the Tesseract program with the Indonesian and English language data (`ind`, `eng`).
3. New settings are listed, names only, in `.env.example` (and `.env.demo.example` for a demo server). The ones to
   decide on: `OLLAMA_URL` and `OLLAMA_MODEL` (needs `ollama serve` with the model pulled), `WEB_API_KEY` (leave blank
   to keep every call local; fill it yourself only if the demo may use the cloud for biasa text), `OCR_*`, `AI_*`,
   `MAX_UPLOAD_MB`. A demo server also sets `AIRCHIVIST_DEMO_MODE` (biasa documents only; the app refuses to start if the
   database already holds anything above biasa).
4. Restart the API, and start the new worker as its own process: `python -m app.worker` (same `.env` as the API).
   Without the worker, uploads stay in the queue.
5. In the app: Pengaturan > choose the archive folder (the API and the worker must be able to write to it).

Frontend: rebuild and restart as usual (`darkhive-fev2`). New pages under AIRCHIVIST: Unggah, Reviu, and AI settings
on Pengaturan; the demo banner shows when the backend is in demo mode.

Not verified on a real model: the checks used a stand-in model server. Upload one dummy PDF at Biasa and follow it
through (queue, review, approve, search) before showing it to anyone.
