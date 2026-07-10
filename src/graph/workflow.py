from langgraph.graph import StateGraph, END, START
from ..agents.state import RepoIntelState
from ..agents.supervisor import supervisor_agent
from ..agents.repo_scanner import repo_scanner_agent
from ..agents.engineering_analyzer import engineering_analyzer_agent
from ..agents.report_generator import report_generator_agent

def build_graph():
    workflow = StateGraph(RepoIntelState)
    
    # Add nodes
    workflow.add_node("supervisor", supervisor_agent)
    workflow.add_node("repo_scanner", repo_scanner_agent)
    workflow.add_node("engineering_analyzer", engineering_analyzer_agent)
    workflow.add_node("report_generator", report_generator_agent)
    
    # Add edges
    workflow.add_edge(START, "supervisor")
    
    # The supervisor decides where to route next
    workflow.add_conditional_edges(
        "supervisor",
        lambda state: state["next_agent"],
        {
            "repo_scanner": "repo_scanner",
            "engineering_analyzer": "engineering_analyzer",
            "report_generator": "report_generator",
            "FINISH": END
        }
    )
    
    # Workers always return to the supervisor
    workflow.add_edge("repo_scanner", "supervisor")
    workflow.add_edge("engineering_analyzer", "supervisor")
    workflow.add_edge("report_generator", "supervisor")
    
    return workflow.compile()
