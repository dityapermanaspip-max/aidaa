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
- NEW (2026-10-24): resolving a finding (responded -> open) is BLOCKED until the berita acara penyampaian notisi
  (`aidaa_core.finding_bap`, one per finding) records the auditee's stance (`stance_result`). See Korespondensi.
- A finding closes when all its rekomend are closed. Rekomend stays open until resolved and is monitored after the audit.
- Findings carry no unit column, so a PIC sees all findings of the assignment.

## Korespondensi (2026-10-24, DDL patch 06 written but NOT yet run by the owner)
- `aidaa_core.assignment_doc_req` (A): per audited unit, `requested -> submitted (PIC) -> verified (auditor)`.
  PIC submits a document URL + description (AIDAA stores links, not files). Writes (create/update/verify/
  submit) stop once the assignment leaves workable status. Manage = assignment_update (team), submit = PIC,
  verified by the team.
- `aidaa_core.assignment_interview` (C): per audited unit, `planned -> held -> done`, planned/held -> cancelled
  with a reason. Editable only while planned. start/end times are display strings. Team manages via the
  logistics permission; the PIC sees its own units' rows.
- `aidaa_core.finding_bap` (D): one per finding, created manually at/after communicate (never automatic).
  Records the formal session (bap_no, kepada, presented_date, deadline, document_url) and the auditee's
  stance (stance_result agree/partially_agree/disagree + optional response_id link). BAP writes skip the
  workable check (post-audit correspondence). The resolve gate in findings refuses to resolve without a
  recorded stance_result; the patch backfills a BAP skeleton for findings already communicated+.
- Routes live in `app/api/v1/aidaa/correspondence.py` (tag "Korespondensi"); reads all run the same
  authorize_view (`audit.finding.read`), PIC lists filtered to their unit orgs.

## Report and expertise
- The report cannot be submitted or finalized while a communicated finding is past due with no response.
- total_open_materiality is filled by code on submit and finalize. Finalize finishes the assignment and writes expertise credit.
- Expertise starts pending and counts only after HR verifies, an auditor cannot verify their own. A finished audit adds a
  system_credit row equal to days served.
- Cross-assignment monitoring: `GET /monitoring/temuan` (Monev Temuan, 2026-10-24) - findings and rekomendasi
  across every assignment the caller may see, with `no_response`/`overdue`/`under_review` flags and unit names,
  scoped by the surat tugas visibility rule (global mapping = all rows; org-mapped = own records or, after issue,
  their audited units' orgs, so PICs OUTSIDE the internal audit org can use it). Read-only; the `monitor_rekomend`
  timestamp remains the only write.
- Not built: manual finding close, overdue-rekomend REPORTS (the Monev listing exists; scheduled/print reports or
  reminder notices do not), and the KUESIONER (questionnaires): designed with the owner 2026-10-24 as a
  procedure sub-branch (docs/DECISIONS.md), one per procedure, several respondents with a control-group identity
  block; nothing written yet - needs the owner's "go code" + DDL patch 07.