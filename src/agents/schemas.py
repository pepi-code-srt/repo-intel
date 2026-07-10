from pydantic import BaseModel, Field
from typing import Optional

class AgentFinding(BaseModel):
    agent: str = Field(description="The name of the agent (e.g., security, code_quality, architecture)")
    score: Optional[int] = Field(description="Score out of 10 for this specific category based on the rubric.")
    status: str = Field(description="Status word corresponding to the score (e.g., Excellent, Good, Weak, Critical)")
    strengths: list[str] = Field(description="List of positive findings or strengths.")
    weaknesses: list[str] = Field(description="List of weaknesses or negative findings.")
    critical_issues: list[dict] = Field(
        description="List of critical issues. Each dict should have 'name', 'severity', 'problem', and 'solution' keys."
    )
    recommendations: list[str] = Field(description="Actionable recommendations to improve the score.")

class DevOpsFinding(AgentFinding):
    missing_practices: list[str] = Field(description="List of missing DevOps practices (e.g., CI, CD, Docker Compose)")

class EngineeringFindings(BaseModel):
    code_quality: AgentFinding = Field(description="Findings for Code Quality and Architecture")
    security: AgentFinding = Field(description="Findings for Security")
    devops: DevOpsFinding = Field(description="Findings for DevOps and Production Readiness")
