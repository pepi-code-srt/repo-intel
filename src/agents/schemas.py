"""
RepoIntel — Structured Output Schemas
All Pydantic models used for Gemini structured output.

CRITICAL: No dict fields, no extra="forbid", no Mapping types.
These generate 'additionalProperties' which the Gemini Developer API rejects.
Use explicit models with typed fields instead.
"""
from pydantic import BaseModel, Field
from typing import Optional


# === Evidence Citation ===

class EvidenceCitation(BaseModel):
    """A reference to specific evidence in the repository."""
    file_path: str = Field(description="Path to the file in the repository")
    excerpt: str = Field(default="", description="Relevant code excerpt or content snippet")
    reason: str = Field(default="", description="Why this evidence is relevant to the finding")


# === Critical Issue ===

class CriticalIssue(BaseModel):
    """A critical issue found in the repository. Uses explicit fields instead of dict."""
    name: str = Field(description="Short name of the issue")
    severity: str = Field(description="Severity level: Critical, High, Medium, or Low")
    problem: str = Field(description="Description of the problem")
    solution: str = Field(description="Recommended solution")


# === Agent Finding (per category) ===

class AgentFinding(BaseModel):
    """Structured finding for one analysis category."""
    agent: str = Field(description="Category name (e.g., code_quality, security, devops)")
    score: Optional[int] = Field(default=None, description="Score out of 10, or null if not scored")
    status: str = Field(description="Verdict: Excellent, Good, Adequate, Weak, Critical, or Not scored")
    strengths: list[str] = Field(default_factory=list, description="List of positive findings")
    weaknesses: list[str] = Field(default_factory=list, description="List of weaknesses found")
    critical_issues: list[CriticalIssue] = Field(default_factory=list, description="List of critical issues")
    recommendations: list[str] = Field(default_factory=list, description="Actionable recommendations")


class DevOpsFinding(AgentFinding):
    """DevOps-specific finding with missing practices."""
    missing_practices: list[str] = Field(default_factory=list, description="Missing DevOps practices")


# === Full Engineering Findings (sent to Gemini as response_schema) ===

class EngineeringFindings(BaseModel):
    """Complete engineering analysis response. This is the schema sent to Gemini."""
    code_quality: AgentFinding = Field(description="Code Quality and Architecture analysis")
    security: AgentFinding = Field(description="Security analysis")
    devops: DevOpsFinding = Field(description="DevOps and Production Readiness analysis")


# === Fast Helper Response (optional lightweight classification) ===

class FastHelperResponse(BaseModel):
    """Small structured response from the fast helper model."""
    repository_type: str = Field(description="Type of repository: web_app, library, cli_tool, api_service, data_pipeline, mobile_app, other")
    primary_language: str = Field(description="Primary programming language")
    likely_entrypoints: list[str] = Field(default_factory=list, description="Likely application entry point files")
    priority_review_areas: list[str] = Field(default_factory=list, description="Areas that need closest review")
    high_risk_indicators: list[str] = Field(default_factory=list, description="Indicators of high-risk code")
