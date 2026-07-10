from typing import Annotated, TypedDict
from langgraph.graph.message import add_messages

class RepoIntelState(TypedDict):
    messages: Annotated[list, add_messages]
    repo_url: str
    repo_path: str
    repo_structure: dict
    repo_metadata: dict        # stars, forks, languages, contributors, etc.
    readme_content: str        # raw README.md text
    dependencies: list         # parsed dependency list
    source_samples: dict       # {filepath: content} of key source files
    repo_statistics: dict
    repo_health: dict
    agent_findings: dict       # structured outputs from agents
    final_report: str
    report_metadata: dict
    next_agent: str
