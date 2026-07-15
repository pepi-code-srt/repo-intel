from langchain_core.messages import AIMessage
from .state import RepoIntelState
from .schemas import EngineeringFindings
from ..mcp_server.tools.github_tools import read_file_content
from ..utils.llm_manager import invoke_llm_with_retry
import json
import logging

logger = logging.getLogger(__name__)

def engineering_analyzer_agent(state: RepoIntelState) -> dict:
    repo_name = state.get("repo_metadata", {}).get("full_name", "Unknown")
    logger.info("Running combined Engineering Analyzer for %s", repo_name)

    repo_path = state.get("repo_path", "")

    from ..utils.text_utils import minify_content

    dockerfile = minify_content(read_file_content(repo_path, "Dockerfile", max_chars=1500)) if repo_path else ""
    docker_compose = minify_content(read_file_content(repo_path, "docker-compose.yml", max_chars=1500)) if repo_path else ""
    env_example = minify_content(read_file_content(repo_path, ".env.example", max_chars=1000)) if repo_path else ""
    gitignore = minify_content(read_file_content(repo_path, ".gitignore", max_chars=1000)) if repo_path else ""
    readme_snippet = minify_content((state.get('readme_content', '') or '')[:1000])

    deps = state.get('dependencies', [])
    deps_str = "\n".join(deps[:30]) if deps else "No dependencies found"

    structure_str = str(state.get('repo_structure', {}))[:1500]

    # Include source samples
    source_samples = state.get('source_samples', {})
    source_context = ""
    for filepath, content in list(source_samples.items())[:3]:
        minified_content = minify_content(content[:1500])
        source_context += f"\n--- {filepath} ---\n{minified_content}\n"

    metrics = state.get("repo_statistics", {})
    health = state.get("repo_health", {})

    metrics_str = json.dumps(metrics, indent=2)
    health_str = json.dumps(health, indent=2)

    prompt = f"""You are a Staff Engineering Committee evaluating a repository's Code Quality, Security, and DevOps Readiness.

## Repository Metrics & Health
Metrics: {metrics_str}
Health Checks: {health_str}

## Repository Structure
{structure_str}

## Critical Files
Dockerfile: {dockerfile if dockerfile else "None"}
docker-compose.yml: {docker_compose if docker_compose else "None"}
.env.example: {env_example if env_example else "None"}
.gitignore: {gitignore if gitignore else "None"}
README: {readme_snippet if readme_snippet else "None"}

## Dependencies
{deps_str}

## Source Code Samples
{source_context if source_context else "No source files available"}

Provide structured findings for the following 3 categories based on the evidence. Do NOT guess. If evidence is missing, state so.

1. Code Quality & Architecture (Score 0-10)
10: Excellent modularity, clear layers. 8: Good separation of concerns. 4: Monolithic. 2: Poor.

2. Security (Score 0-10)
10: Exceptional security, no secrets. 8: Good security. 4: Missing practices. 2: Critical vulnerabilities found!

3. DevOps & Production Readiness (Score 0-10)
10: CI/CD fully implemented, Docker present, testing. 8: Good infra. 4: Missing Docker/CI. 2: Completely local.

Fill out the JSON schema carefully. Ensure all 3 categories (code_quality, security, devops) are fully populated.
"""

    try:
        response: EngineeringFindings = invoke_llm_with_retry(prompt, structured_schema=EngineeringFindings)
        findings_dict = response.dict()

        agent_findings = state.get("agent_findings", {})
        # Map the sub-findings into the dictionary so report_generator sees them
        agent_findings["code_quality"] = findings_dict["code_quality"]
        agent_findings["security"] = findings_dict["security"]
        agent_findings["devops"] = findings_dict["devops"]

        msg = f"Engineering Analysis complete. Scores: CQ={findings_dict['code_quality']['score']}, Sec={findings_dict['security']['score']}, DevOps={findings_dict['devops']['score']}."

    except Exception as exc:
        exc_str = str(exc)
        logger.error("Engineering Analysis failed: %s", exc_str)
        agent_findings = state.get("agent_findings", {})

        # Log raw diagnostic details internally, do not expose API keys or payloads to user
        logger.error("Engineering Analysis API Exception: %s", exc_str)

        status_str = "QuotaExceeded" if "RESOURCE_EXHAUSTED" in exc_str else "Error"
        user_msg = "AI analysis unavailable; deterministic structural analysis used."

        # Provide neutral fallback findings so supervisor does not infinitely loop
        fallback = {
            "agent": "Engineering Analyzer", "score": None, "status": status_str,
            "strengths": [], "weaknesses": [user_msg],
            "critical_issues": [], "recommendations": []
        }

        agent_findings["code_quality"] = fallback
        agent_findings["security"] = fallback
        agent_findings["devops"] = fallback

        msg = f"Analysis fallback activated: {user_msg}"

    return {
        "agent_findings": agent_findings,
        "messages": [AIMessage(content=msg)]
    }
