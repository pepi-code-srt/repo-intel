"""
RepoIntel — Graph State
Clean TypedDict state for the deterministic workflow graph.
No langchain_core dependency for messages.
"""
from typing import TypedDict, Optional


class RepoIntelState(TypedDict):
    # Input
    repo_url: str

    # Scanner output
    repo_path: str
    repo_structure: dict
    repo_metadata: dict
    readme_content: str
    dependencies: list
    source_samples: dict
    repo_statistics: dict
    repo_health: dict
    analyzed_commit_sha: Optional[str]

    # Evidence selection
    evidence: dict  # Output from evidence_selector
    evidence_metadata: dict  # Stats about what was included/omitted

    # AI analysis
    agent_findings: dict  # Structured findings from engineering analyzer
    analysis_mode: str  # "ai_enhanced", "ai_enhanced_fallback", "structural"
    ai_model_used: Optional[str]  # Which model actually produced the analysis
    ai_requests_log: list  # List of AIRequestLog entries (sanitized)

    # Fast helper
    fast_helper_result: Optional[dict]  # Output from optional fast helper
    fast_helper_model: Optional[str]  # Which model ran the helper

    # Report
    final_report: str
    report_metadata: dict

    # Error handling
    fallback_reason: Optional[str]
    error_message: Optional[str]  # User-facing error
    fix_instructions: Optional[str]  # How to fix the error

    # Workflow tracking
    progress_messages: list  # Messages sent to frontend via WebSocket
