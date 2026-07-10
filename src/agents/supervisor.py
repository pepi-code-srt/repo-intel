from typing import Literal
from pydantic import BaseModel, Field
from .state import RepoIntelState

MAX_ITERATIONS = 25  # Safety net to prevent infinite loops

class RouteDecision(BaseModel):
    next_agent: Literal["repo_scanner", "engineering_analyzer", "report_generator", "FINISH"] = Field(
        description="The next agent to route to, or FINISH if all tasks are complete."
    )

def supervisor_agent(state: RepoIntelState) -> dict:
    """The supervisor that routes tasks to the appropriate worker agent."""
    messages = state.get("messages", [])
    
    agent_findings = state.get("agent_findings", {})
    repo_structure = state.get("repo_structure", {})
    
    # Safety: count how many times we've been invoked by counting messages
    if len(messages) > MAX_ITERATIONS:
        return {"next_agent": "FINISH"}
    
    # Check what has been done
    done_scan = bool(repo_structure)
    scan_failed = "_error" in repo_structure if isinstance(repo_structure, dict) else False
    done_engineering = "code_quality" in agent_findings and "security" in agent_findings and "devops" in agent_findings
    done_report = bool(state.get("final_report"))
    
    # Hardcoded routing logic for a deterministic pipeline
    if not done_scan:
        return {"next_agent": "repo_scanner"}
    elif scan_failed and not done_report:
        # Scan failed — skip engineering analysis, go straight to report
        return {"next_agent": "report_generator"}
    elif not done_engineering:
        return {"next_agent": "engineering_analyzer"}
    elif not done_report:
        return {"next_agent": "report_generator"}
    else:
        return {"next_agent": "FINISH"}

