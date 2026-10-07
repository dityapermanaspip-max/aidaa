from app.services.approval import register_handler

from app.services.execution.pka import (
    get_pka, list_pka, copy_library, create_pka, update_pka, set_pka_skip,
    submit_pka, complete_pka, _on_pka_task,
)
from app.services.execution.procedures import (
    get_procedure, list_procedures, create_procedure, update_procedure, set_procedure_skip,
    submit_procedure, skip_review, reopen_review, _on_procedure_task,
    get_paper, list_papers, create_paper, update_paper,
)
from app.services.execution.findings import (
    get_finding, list_findings, create_finding, update_finding, submit_finding,
    communicate_finding, extend_due, respond_finding, resolve_finding, list_responses,
    _on_finding_task,
)
from app.services.execution.recommendations import (
    get_rekomend, list_rekomend, create_rekomend, update_rekomend, followup_rekomend,
    close_rekomend, monitor_rekomend,
)
from app.services.execution.reports import (
    get_report, list_reports, get_report_detail, create_report, update_report,
    submit_report, finalize_report, _on_report_task,
)

register_handler("pka", _on_pka_task)
register_handler("procedure", _on_procedure_task)
register_handler("finding", _on_finding_task)
register_handler("report", _on_report_task)