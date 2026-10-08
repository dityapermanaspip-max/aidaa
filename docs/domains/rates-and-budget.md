# Domain: cost rates and budget

## Cost components and rates
- Components are rows with calc_basis: per_day_worked, per_travel_day, per_night, at_cost, fixed. Code unique per root.
- Rate lifecycle: draft, pending (submitted), approved or rejected (Board). Budgets use only approved rates.
- at_cost components may carry a reference MAXIMUM rate (tickets, transport). They are never priced through resolve_price.
  The trip helper reads them. Real cost is entered at realisation.
- Rate shapes: province (location only), road (origin capital to destination city), route (origin to destination city),
  single national amount (no location). Route rates use origin_location_id plus location_id (destination).
- RATE GRADE: grade is a jsonb array. A rate fits an auditor when the array contains the auditor's grade text.
  Empty or NULL fits every grade. No grade mapping lives in code. Auditor grade is free text and must equal the rate code
  exactly, a typo means "no rate".
- OVERLAP: submit_rate returns 409 when another live (pending or approved) rate overlaps on component, origin, place, grade
  and dates.
- List endpoint supports component_id, location_id, status, grade (jsonb contains, NULL grade kept), limit and offset.

## Rate date rule
resolve_price checks the rate on the START DATE of the plan (period_start) or assignment (start_date), not today.
A record that crosses New Year uses the rate valid on its first day. A 2026 rate never prices a 2027 record.

## Place matching (location_fits in budget_core.py)
A rate on a location without city covers its whole province. A city rate covers that city. When either side has no
province, city names must match exactly. Kota X and Kab. X are different locations: never guess, mark "pick manually".

## Budget lines
- A line belongs to a plan OR an assignment (CHECK). unit_rate is copied from an approved rate, at_cost lines take a typed rate.
- Plan lines of a detailed plan use version_no = NEXT version number. Carry-over copies the last version into a new draft.
- Only the plan's budget drafter changes plan lines. Assignment lines change only while draft, by the leader.
- At issue, plan lines are copied (copied_from_line_id). assignment_funding must equal the budget total at issue.
  The funding source ceiling is enforced. Funding changes only while draft.
- Deviation is CALCULATED (v_plan_deviation), never stored by hand.
- SBM is reference, not a block. Planned: flag lines above the SBM reference with a required reason (with trip logic).