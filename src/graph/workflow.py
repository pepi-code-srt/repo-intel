"""
RepoIntel — Deterministic Workflow Graph
Linear pipeline: scan → analyze → report
No supervisor loop. No LLM deciding workflow transitions.
"""
from langgraph.graph import StateGraph, END, START
from ..agents.state import RepoIntelState
from ..agents.repo_scanner import repo_scanner_agent
from ..agents.engineering_analyzer import engineering_analyzer_agent
from ..agents.report_generator import report_generator_agent


def _should_skip_analysis(state: RepoIntelState) -> str:
    """After scanning, decide whether to analyze or skip to report."""
    repo_structure = state.get("repo_structure", {})
    if isinstance(repo_structure, dict) and "_error" in repo_structure:
        # Scan failed — skip analysis, go straight to report
        return "report_generator"
    return "engineering_analyzer"


def build_graph():
    """
    Build the deterministic analysis pipeline.

    Flow:
        START → repo_scanner → [check scan result]
                                  ├─ scan OK → engineering_analyzer → report_generator → END
                                  └─ scan failed → report_generator → END
    """
    workflow = StateGraph(RepoIntelState)

    # Add nodes
    workflow.add_node("repo_scanner", repo_scanner_agent)
    workflow.add_node("engineering_analyzer", engineering_analyzer_agent)
    workflow.add_node("report_generator", report_generator_agent)

    # Linear flow with one conditional branch
    workflow.add_edge(START, "repo_scanner")

    workflow.add_conditional_edges(
        "repo_scanner",
        _should_skip_analysis,
        {
            "engineering_analyzer": "engineering_analyzer",
            "report_generator": "report_generator",
        }
    )

    workflow.add_edge("engineering_analyzer", "report_generator")
    workflow.add_edge("report_generator", END)

    return workflow.compile()
