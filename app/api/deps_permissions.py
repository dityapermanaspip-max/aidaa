"""One named wrapper per permission code, grouped by domain. Routers import these names."""
from app.api.deps_auth import require_permission, require_any_permission

# --- Master data (no owner org) ---
location_read = require_permission("audit.location.read")
location_create = require_permission("audit.location.create")
location_update = require_permission("audit.location.update")
location_delete = require_permission("audit.location.delete")

unit_read = require_permission("audit.unit.read")  # audit types and auditable units
unit_create = require_permission("audit.unit.create")
unit_update = require_permission("audit.unit.update")
unit_delete = require_permission("audit.unit.delete")

auditor_read = require_permission("audit.auditor.read")
auditor_create = require_permission("audit.auditor.create")
auditor_update = require_permission("audit.auditor.update")
auditor_delete = require_permission("audit.auditor.delete")
expertise_read = require_permission("audit.expertise.read")
expertise_create = require_permission("audit.expertise.create")
expertise_verify = require_permission("audit.expertise.verify")

library_read = require_permission("audit.library.read")
library_manage = require_permission("audit.library.manage")

coststd_read = require_permission("audit.coststd.read")  # cost components and funding sources
coststd_create = require_permission("audit.coststd.create")
coststd_update = require_permission("audit.coststd.update")
coststd_delete = require_permission("audit.coststd.delete")
costrate_read = require_permission("audit.costrate.read")
costrate_create = require_permission("audit.costrate.create")
costrate_update = require_permission("audit.costrate.update")
costrate_delete = require_permission("audit.costrate.delete")
costrate_approve = require_permission("audit.costrate.approve")

setting_read = require_permission("audit.setting.read")
setting_update = require_permission("audit.setting.update")

# --- Approval engine: own to-do list (decide rights are checked inside the service) ---
task_read = require_permission("audit.task.read")

# --- Plan core (the org of the record is checked in the router) ---
plan_read = require_permission("audit.plan.read")
plan_create = require_permission("audit.plan.create")
plan_update = require_permission("audit.plan.update")
team_manage = require_permission("audit.team.manage")

# --- Assignment, team, visits, trip legs ---
assignment_read = require_permission("audit.assignment.read")
assignment_create = require_permission("audit.assignment.create")
assignment_update = require_permission("audit.assignment.update")
team_read = require_permission("audit.team.read")
logistics_write = require_any_permission("audit.assignment.update", "audit.assignment.logistics")

# --- Budget lines (layer 2 = plan drafter or assignment leader, checked in the budget services) ---
budget_read = require_permission("audit.budget.read")
budget_draft = require_permission("audit.budget.draft")

# --- Execution: pka, procedures, papers, findings, recommendations, report ---
pka_read = require_permission("audit.pka.read")
pka_create = require_permission("audit.pka.create")
pka_update = require_permission("audit.pka.update")
paper_read = require_permission("audit.paper.read")
paper_create = require_permission("audit.paper.create")
paper_update = require_permission("audit.paper.update")
paper_review = require_permission("audit.paper.review")
finding_read = require_permission("audit.finding.read")
finding_create = require_permission("audit.finding.create")
finding_update = require_permission("audit.finding.update")
finding_approve = require_permission("audit.finding.approve")
finding_communicate = require_permission("audit.finding.communicate")
finding_respond = require_permission("audit.finding.respond")
rekomend_read = require_permission("audit.rekomend.read")
rekomend_create = require_permission("audit.rekomend.create")
rekomend_update = require_permission("audit.rekomend.update")
rekomend_close = require_permission("audit.rekomend.close")
rekomend_followup = require_permission("audit.rekomend.followup")
report_read = require_permission("audit.report.read")
report_create = require_permission("audit.report.create")
report_update = require_permission("audit.report.update")
report_approve = require_permission("audit.report.approve")
deviation_read = require_permission("audit.deviation.read")