# Domain: visits and trip legs

## Rules
- Visits and legs exist only on an assignment in status draft, issued or ongoing (trip_common.open_assignment).
- Attendees and leg auditors must be ACTIVE team members.
- The auditor schedule locks only on CONFIRM. Overlapping confirmed rows of one auditor are refused (409).
- A leg is ONE segment. Estimates create or update the leg's at_cost budget line through sync_leg_line.
  A cancelled leg deletes its line. actual_cost replaces the estimate after confirm. Mode is descriptive only.
- The leg component must be at_cost. Empty falls back to the active at_cost component coded TRANSPORT of the root.
- Confirming a leg needs depart_at and arrive_at.

## Trip helper
- AI answers only unit, start and end date, attendees and a reason. Dates are cut to the assignment period.
- Origin of each auditor: auditor.home_location_id, then audit_setting.base_location_id (no screen to fill it yet).
  With neither, no legs are made and a warning says so. Same place as the destination means no legs.
- Ticket rates: approved route rates of TIKET_PESAWAT_EKONOMI (default) and TIKET_PESAWAT_BISNIS, valid on the assignment
  start date. Business only when the auditor's grade is LISTED on a business rate.
- Round trip is split into two legs (outbound on the visit start, return on the visit end), each HALF of the PP rate.
- Place matching: exact name matches are priced. A name that matches by core only (Kupang vs Kota/Kab. Kupang) is status manual.
  No rate means estimate 0 and status no_rate.
- The review table has a searchable airport list (destinations that have ticket rates, same province first). The ticket city
  is never the visit's own city if that city has no airport.
- On accept the server prices each leg AGAIN with exact matches only. Typed amounts in the draft are never trusted.
- Not created here: daily allowance and lodging (budget lines from the plan or by hand) to avoid double cost.
- Permissions: audit.assignment.update or audit.assignment.logistics.

## Planned: realisation
Advance (uang muka), accountability, reimbursement, variance against the budget, and cross-subsidy between outbound and return
tickets. The design leaves room: legs have actual_cost and the budget line follows it after confirm. Nothing real is recorded
for daily allowance or lodging yet. Not designed in detail.