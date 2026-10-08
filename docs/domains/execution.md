# Domain: execution, findings, reports

## Review rules
- Procedure: leader_review (mandatory), then supervisor_review (can_skip, a skip needs a reason). Finding: leader_review then
  supervisor_approve. Report: supervisor_review then head_approve. PKA: supervisor_approve. Working papers are reviewed through
  their procedure. The reviewer is never the preparer. Rejected items return to the preparer.
- Notes go to comment_log, decisions to approval_log. Skipped reviews can be reopened. The report shows reviewed vs skipped counts.

## Library and PKA
- The Head copies library PKA and procedures into an assignment (copy-library). Auditors may edit, add or skip, never delete.
- Hours are CALCULATED: PKA hours = sum of active procedure hours. Step numbers are automatic (blank = next).

## Findings
- Flow: draft, leader_reviewed, approved, communicated, responded, open or closed.
- Communicating needs a future response_due_date. Extending it logs old and new date with a reason.
- The auditee PIC replies in finding_response. A disagreement never deletes the finding, the supervisor resolves it (open).
- A finding closes when all its rekomend are closed. Rekomend stays open until resolved and is monitored after the audit.
- Findings carry no unit column, so a PIC sees all findings of the assignment.

## Report and expertise
- The report cannot be submitted or finalized while a communicated finding is past due with no response.
- total_open_materiality is filled by code on submit and finalize. Finalize finishes the assignment and writes expertise credit.
- Expertise starts pending and counts only after HR verifies, an auditor cannot verify their own. A finished audit adds a
  system_credit row equal to days served.
- Not built: manual finding close, overdue-rekomend reports.