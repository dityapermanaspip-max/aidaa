from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.aidaa import master, masters_auditor, masters_library, masters_costing, masters_options, library_ai, sbm_ai, approval, plan, plan_flow, plan_budget_ai, funding, me, assignment, team, trip, budgeting, exec_pka, exec_finding, exec_report, ai

app = FastAPI(
    title="AIDAA - AI Driven Audit Assistant",
    description="Core API for audit planning, execution, and reporting.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_PREFIX = "/api/v1/aidaa"  # routers get registered here in later tasks
app.include_router(master.router, prefix=f"{API_PREFIX}/master", tags=["Master Data"])
app.include_router(masters_auditor.router, prefix=f"{API_PREFIX}/master", tags=["Master - Auditor"])
app.include_router(masters_library.router, prefix=f"{API_PREFIX}/master", tags=["Master - Library"])
app.include_router(sbm_ai.router, prefix=f"{API_PREFIX}/master", tags=["Master - SBM AI"])
app.include_router(library_ai.router, prefix=f"{API_PREFIX}/master", tags=["Master - Library AI"])
app.include_router(masters_costing.router, prefix=f"{API_PREFIX}/master", tags=["Master - Costing"])
app.include_router(masters_options.router, prefix=f"{API_PREFIX}/master", tags=["Master - Options"])
app.include_router(approval.router, prefix=f"{API_PREFIX}/approval", tags=["Approval"])
app.include_router(plan.router, prefix=f"{API_PREFIX}/plan", tags=["Plan"])
app.include_router(plan_flow.router, prefix=f"{API_PREFIX}/plan", tags=["Plan Flow"])
app.include_router(funding.router, prefix=f"{API_PREFIX}/funding", tags=["Funding"])
app.include_router(me.router, prefix=f"{API_PREFIX}/me", tags=["Me"])
app.include_router(assignment.router, prefix=f"{API_PREFIX}/assignment", tags=["Assignment"])
app.include_router(team.router, prefix=f"{API_PREFIX}/assignment", tags=["Team"])
app.include_router(trip.router, prefix=f"{API_PREFIX}/assignment", tags=["Visits and Legs"])
app.include_router(budgeting.router, prefix=API_PREFIX, tags=["Budget and Funding"])
app.include_router(exec_pka.router, prefix=API_PREFIX, tags=["Execution - PKA"])
app.include_router(exec_finding.router, prefix=API_PREFIX, tags=["Execution - Findings"])
app.include_router(exec_report.router, prefix=API_PREFIX, tags=["Execution - Report"])
app.include_router(ai.router, prefix=API_PREFIX, tags=["AI"])
app.include_router(plan_budget_ai.router, prefix=f"{API_PREFIX}/plan", tags=["Plan Budget AI"])


@app.get("/", tags=["Health Check"])
def root_check():
    return {"status": "online", "system": "AIDAA Core API", "version": "1.0.0"}