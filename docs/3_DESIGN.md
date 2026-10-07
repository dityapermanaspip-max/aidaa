# 3. Design, to do and known gaps

## Why the tables are grouped this way
aidaa_core master (rarely changing data), planning (plan, versions, assignment, team, visits, legs, budget, funding, schedule),
execution (pka, exe_procedure, working_paper, finding, finding_response, rekomend, audit_report). aidaa_log is append-only history
(triggers reject UPDATE and DELETE). aidaa_ai stores every AI proposal first.

## Design decisions (follow them, do not simplify them away)
- Single unit and no trips are the DEFAULT. Multi-unit and multi-trip are optional extras.
- Organisation scope: five master tables carry root_org_id, rates inherit it from their component, codes are unique per root.
  Plans, assignments, budget lines, trip legs, funding allocation and the PKA copy reject records of another root.
- Seeds are data files. Many roots exist, so a seed names its root by org code. Rates seed as 'approved' because the regulation
  is the approval. The AI helper creates rates as DRAFT instead.
- audit_plan_version freezes what the Board approved (snapshot jsonb). The live plan is editable only until approval and locked
  while a version is pending. Deviation is CALCULATED (view v_plan_deviation), never stored by hand.
- assignment.plan_id is nullable: empty means an unplanned audit, flagged is_unplanned.
- Units (services/unit_links.py): main table keeps the FIRST unit in unit_id, the link table holds ALL units.
- assignment_member: never overwrite a member, end-date the old row and insert a new one. One active row per person.
- budget_line belongs to a plan OR an assignment (CHECK). amount is generated, never insert it. unit_rate is copied from an
  approved, active ref_cost_rate; at_cost components take a typed unit_rate. Plan lines of a detailed plan use version_no = the
  NEXT version number. After a rejected submit, carry-over copies the last version's lines into the new draft.
- RATE DATE RULE: resolve_price checks the rate on the START DATE of the plan (period_start) or assignment (start_date), not
  today. A record crossing New Year uses the rate valid on its first day. A 2026 rate therefore never prices a 2027 record.
- RATE GRADE: ref_cost_rate.grade is a jsonb array. A rate fits an auditor when the array contains the auditor's grade text, an
  empty or NULL array fits every grade. No grade mapping lives in code. Submitting a rate is refused with 409 when another live
  (pending or approved) rate overlaps on component, place, grade and dates.
- Rate list endpoint supports grade, limit and offset (FE pages by asking limit+1). Grade filter keeps rates with NULL grade.
- Trip leg estimates create/update their own at_cost budget_line. The leg form picks the at_cost component, empty falls back to
  the active at_cost component coded TRANSPORT of the same root. A cancelled leg deletes its line.
- Cost components are rows with calc_basis per_day_worked, per_travel_day, per_night, at_cost, fixed. Rates: draft, pending,
  approved, rejected. Budgets use only approved rates.
- auditor_schedule has an exclusion constraint: no overlapping confirmed rows per auditor.
- assignment_funding must equal the budget total at issue; the source ceiling is enforced; funding changes only while draft.
- Library: the Head copies library PKA and procedures into an assignment. Hours are CALCULATED from procedures.
- AI (all engines through services/ai_engine.py): every row created from AI has source = ai_suggestion and ai_suggestion_id.
  Never write AI output into real tables directly: aidaa_ai.ai_suggestion first, then a human accepts, edits or rejects.
  Features built: pka, report, library_draft, sbm_draft, budget (plan budget).
  * Library draft: pasted text (max 30000 chars) becomes library_pka (code <type_code>-NNN per root) and procedures.
  * SBM draft (sbm_ai): the owner pastes ONE annex table. A code parser reads province rows and amounts (number line, province
    name, unit, Rp lines) through a FIXED province name map (PMK spellings such as "R I A U", "D.K.I. JAKARTA" map to PROV-xx).
    The AI only names the amount columns (component code, name, calc_basis) and the official groups (grade codes) from the
    headings. in_source marks amounts whose text exists in the pasted source. Accept creates missing components and province
    locations and DRAFT rates (Finance submits, Board approves). One draft per root, record_type organization.
    Parser fits tables with cost types as columns and grade groups as sub-headings (Lampiran 31). Tables with one column per
    grade (Lampiran 30) need a second shape.
  * Plan budget draft (plan_budget_ai): record_type plan, feature budget. The AI answers only on-site days per audited unit and
    a reason. Code builds the lines: effort = library procedure hours / 8 per audit type, per team member and per_day_worked /
    per_night component, rate picked by the member's own grade and the unit's place on the plan start date. Constants at the
    top of the service: TRAVEL_ALLOWANCE_DAYS = 1 (practice: travel days together earn ONE daily allowance, the owner doubts
    this is fair, change the constant if the rule changes) and TRAVEL_NIGHTS = 1. Members whose home location fits the unit
    get no travel lines. No fitting rate = status no_rate, several = manual, both skipped on accept. Tickets (at_cost) are never
    suggested. Accept needs the plan's budget drafter (editable_plan) and writes lines into the draft version.
  * Visits and trip legs get their OWN AI helper later (not built).
- SBM / deviation (decided): SBM is reference, not a block. Levels: (1) plan vs assignment budget (v_plan_deviation, exists);
  (2) each budget line's rate vs SBM flagged with a reason (to build with trips and legs); (3) estimate vs actual (trip legs only).

## Roles and access
- AIDAA.AUDITOR carries the union of leader, member and supervisor codes. services/roles.py ROLE_ACTIONS is a guess.
- Two layers. Layer 1: require_permission plus the org of the record. Layer 2: my_assignment_role reads assignment_member.
- Nobody approves their own work. Plan approval: Finance verifies, then the Board approves (task record_id = VERSION id).
- A user cannot decide their own cost rate (decide_rate rejects created_by).
- SBM AI uses audit.costrate.create to generate and decide, audit.costrate.read for the model list. Finance lacks
  audit.location.create, so the first accept that must create province locations may need an Admin.
- Plan budget AI uses audit.budget.draft and audit.budget.read, accept also requires being the plan's budget drafter.
- Conflict of interest, auditee PIC access, expertise and rekomend rules are unchanged from earlier versions of this file:
  IAU subtree cannot be tagged, auditor home org is checked against every unit org, PIC sees an assignment only after issue,
  expertise counts only after HR verification, every write logs to aidaa_log and iam.audit_log.

## Review and finding rules
- Procedure: leader_review then supervisor_review (can_skip, a skip needs a reason). Finding: leader_review then supervisor_approve.
  Report: supervisor_review then head_approve. PKA: supervisor_approve. The reviewer is never the preparer.
- Finding flow: draft, leader_reviewed, approved, communicated, responded, open or closed. The report cannot be submitted or
  finalized while a communicated finding is past due with no response. Finalize finishes the assignment and writes expertise credit.

## Status
Backend tasks 1 to 7 done. Done since last version: patch 04 (rate grade jsonb) and 05 (sbm_draft) applied; trial seed 2026 loaded
and visible in the FE; rate date rule (start date); rate overlap check; rate list filter and paging; ai_engine rewritten (names,
Google error text, retry on 429 and 503); SBM AI helper (schema, service, router, FE page); SBM model-list endpoint;
plan budget AI helper (schema, service, router, FE modal).
Verified by the owner in the FE: master pages, Step B (units on plans and assignments), org scope, rate list.
Written but NOT yet exercised: SBM AI end to end (parser against a real Lampiran text, Web API when Gemini is not busy),
plan budget AI, rate date rule in budgeting, rate overlap 409, library AI drafts.

## To do (next)
1. Test SBM AI with Lampiran 31 and 30 text, then load real 2027 data through it. Add the second parser shape for tables with
   one column per grade (Lampiran 30). Save patch 04 and 05 into sql/.
2. Visit and trip-leg AI helper (duration per location, cost sheet from approved rates), and the SBM flag on lines above the
   rate with a required reason, both with the trip and leg logic.
3. FE batches: 5e execution (PKA copy, procedures, papers, review), findings, reports; deviation page.
4. Second AI helper library_improvement; AI for team and expertise.
5. Wire the seeded approval steps (budget verification, assignment_change).

## Known gaps
- Auditors and expertise are not root-scoped (they hang on home_org_id); unit_code is still unique across the whole database.
- Findings have no unit column (a PIC sees every finding of a multi-unit assignment).
- A user whose AIDAA roles span more than one root gets 409 on root-dependent endpoints (single root per user assumed).
- No file storage: documents are url or path metadata only. AI has no PDF upload and no looping above 30000 chars.
- Real daily-allowance and lodging spending is not recorded, only trip leg actual cost.
- ROLE_ACTIONS in services/roles.py is a guess. Manual finding close and overdue-rekomend reports are not built.
- Create an active at_cost component coded TRANSPORT in each root, or choose a component on every trip leg.
- Auditor grade is free text and must equal the rate grade codes exactly, a typo gives "no rate". Auditors with no grade
  match only rates with an empty grade list.
- The library_ai router had a duplicate GET /library/ai/drafts (delete the second function if it is still there).
- Gemini can answer 503 (busy), the retry helps, a lite model (for example gemini-2.5-flash-lite) is less busy.
- Verify in /docs that budgeting's /assignment/{id}/funding does not clash with the assignment router.