"""
RepoIntel — Engineering Analyzer
2-call bounded AI pipeline with automatic model cascade.

Flow:
  1. Optional fast helper (classify repo, identify focus areas) — can fail safely
  2. Primary engineering review (deep analysis with evidence) — cascades through models
  3. If ALL models fail → structural fallback
"""
import json
import logging
from .state import RepoIntelState
from .schemas import EngineeringFindings, FastHelperResponse
from .evidence_selector import select_evidence, format_evidence_for_prompt
from ..config import GEMINI_API_KEY, ENABLE_FAST_HELPER, get_model_cascade, get_model_config
from ..providers.gemini_provider import GeminiProvider, ProviderError
from ..utils.text_utils import minify_content
from ..utils.repo_tools import read_file_content

logger = logging.getLogger(__name__)

# === System Instructions ===

PRIMARY_SYSTEM_INSTRUCTION = """You are a senior software engineer performing an evidence-based repository review.

STRICT RULES:
- Use ONLY the supplied repository evidence below.
- Never invent files, functions, dependencies, or vulnerabilities.
- Distinguish between: direct observation, reasonable inference, and insufficient evidence.
- README claims are NOT implementation proof. Verify against actual code.
- Every major finding must cite concrete supplied evidence.
- Prefer fewer strong findings over many generic findings.
- Return ONLY the requested structured JSON response.
- Do NOT include conversational text outside the JSON structure."""

FAST_HELPER_SYSTEM_INSTRUCTION = """You are a quick repository classifier.
Based on the file listing and metadata, identify the repository type, likely entrypoints, and areas needing review.
Be concise. Return ONLY the requested JSON structure."""


def engineering_analyzer_agent(state: RepoIntelState) -> dict:
    """
    Combined engineering analysis with model cascade.
    Tries smart model first, falls through to next on failure.
    If ALL AI fails, produces structural fallback.
    """
    repo_url = state.get("repo_url", "")
    repo_name = state.get("repo_metadata", {}).get("full_name", "Unknown")
    repo_path = state.get("repo_path", "")
    logger.info("Running Engineering Analyzer for %s", repo_name)

    # Initialize provider
    provider = GeminiProvider(api_key=GEMINI_API_KEY)
    model_cascade = get_model_cascade()

    # Step 1: Select evidence
    evidence = select_evidence(repo_path, state.get("source_samples", {}))

    # Step 2: Optional fast helper
    fast_helper_result = None
    fast_helper_model = None

    if ENABLE_FAST_HELPER:
        fast_helper_result, fast_helper_model = _run_fast_helper(
            provider, state, evidence, model_cascade
        )

    # Step 3: Primary engineering review with model cascade
    try:
        findings_dict, model_used = _run_primary_review(
            provider, state, evidence, fast_helper_result, model_cascade
        )

        # Determine if we used the primary model or a fallback
        primary_model = get_model_config()["primary"]
        if model_used == primary_model:
            analysis_mode = "ai_enhanced"
        else:
            analysis_mode = "ai_enhanced_fallback"

        logger.info(
            "AI analysis completed by model '%s' (mode: %s)",
            model_used, analysis_mode,
        )

        return {
            "agent_findings": findings_dict,
            "analysis_mode": analysis_mode,
            "ai_model_used": model_used,
            "ai_requests_log": [log.model_dump() for log in provider.request_logs],
            "evidence": evidence,
            "evidence_metadata": {
                "included": evidence.get("included_count", 0),
                "omitted": evidence.get("omitted_count", 0),
                "total_chars": evidence.get("total_chars", 0),
            },
            "fast_helper_result": fast_helper_result,
            "fast_helper_model": fast_helper_model,
            "fallback_reason": None,
            "error_message": None,
            "fix_instructions": None,
        }

    except ProviderError as e:
        logger.error(
            "ALL AI models failed for primary review: %s", e.category,
        )
        # Build structural fallback with clear error info for the user
        return _structural_fallback(
            state, evidence, provider,
            error_category=e.category,
            user_message=e.user_message,
            fix_instructions=e.fix_instructions,
            fast_helper_result=fast_helper_result,
            fast_helper_model=fast_helper_model,
        )


def _run_fast_helper(provider, state, evidence, model_cascade):
    """
    Optional fast helper: classify the repo and identify focus areas.
    If it fails, we just skip it — the primary review still runs.
    """
    try:
        metadata = state.get("repo_metadata", {})
        structure_str = str(state.get("repo_structure", {}))[:2000]
        deps = state.get("dependencies", [])
        deps_str = "\n".join(deps[:20]) if deps else "None found"

        prompt = f"""Classify this repository and identify areas needing review.

Repository: {metadata.get('full_name', 'Unknown')}
Description: {metadata.get('description', 'No description')}
Language: {metadata.get('language', 'Unknown')}

File Structure:
{structure_str}

Dependencies:
{deps_str}

Respond with the requested JSON structure only."""

        # Use only the fast/fallback models for the helper (skip primary to save quota)
        config = get_model_config()
        helper_cascade = []
        seen = set()
        for role in ["fast", "fallback"]:
            m = config[role]
            if m not in seen:
                helper_cascade.append(m)
                seen.add(m)

        result, model_used = provider.generate_structured(
            prompt=prompt,
            schema=FastHelperResponse,
            model_cascade=helper_cascade,
            task_id="fast_helper",
            task_role="fast_helper",
            system_instruction=FAST_HELPER_SYSTEM_INSTRUCTION,
            temperature=0.1,
            max_output_tokens=1024,
        )

        logger.info(
            "Fast helper completed by '%s': type=%s, focus_areas=%d",
            model_used,
            result.get("repository_type", "?"),
            len(result.get("priority_review_areas", [])),
        )
        return result, model_used

    except Exception as e:
        logger.warning("Fast helper failed (non-critical, skipping): %s", str(e)[:200])
        return None, None


def _run_primary_review(provider, state, evidence, fast_helper_result, model_cascade):
    """
    Primary engineering review: deep analysis with full evidence.
    Uses model cascade — strongest model first, falls through on failure.
    """
    metadata = state.get("repo_metadata", {})
    metrics = state.get("repo_statistics", {})
    health = state.get("repo_health", {})

    # Build the evidence context
    evidence_text = format_evidence_for_prompt(evidence, metadata)

    # Include fast helper context if available
    helper_context = ""
    if fast_helper_result:
        helper_context = f"""
## AI Pre-Classification
Repository Type: {fast_helper_result.get('repository_type', 'Unknown')}
Priority Review Areas: {', '.join(fast_helper_result.get('priority_review_areas', []))}
High Risk Indicators: {', '.join(fast_helper_result.get('high_risk_indicators', []))}
"""

    metrics_str = json.dumps(metrics, indent=2)
    health_str = json.dumps(health, indent=2)

    prompt = f"""Perform a comprehensive engineering review of this repository.

## Repository Metrics & Health
Metrics: {metrics_str}
Health Checks: {health_str}
{helper_context}
{evidence_text}

Analyze and score these 3 categories based on the evidence. Do NOT guess. If evidence is missing, state so.

1. Code Quality & Architecture (Score 0-10)
   10: Excellent modularity, clear layers, consistent patterns.
   8: Good separation of concerns, minor issues.
   4: Monolithic, inconsistent, poor structure.
   2: Unmaintainable, no clear architecture.

2. Security (Score 0-10)
   10: No secrets exposed, input validation, secure defaults.
   8: Good security practices with minor gaps.
   4: Missing important security practices.
   2: Critical vulnerabilities found.

3. DevOps & Production Readiness (Score 0-10)
   10: CI/CD, Docker, testing, monitoring present.
   8: Good infrastructure with minor gaps.
   4: Missing Docker/CI/testing.
   2: Not deployable.

Ensure all 3 categories (code_quality, security, devops) are fully populated in the JSON response."""

    result, model_used = provider.generate_structured(
        prompt=prompt,
        schema=EngineeringFindings,
        model_cascade=model_cascade,
        task_id="primary_engineering_review",
        task_role="primary_engineering_review",
        system_instruction=PRIMARY_SYSTEM_INSTRUCTION,
        temperature=0.1,
        max_output_tokens=8192,
    )

    return result, model_used


def _structural_fallback(state, evidence, provider,
                         error_category, user_message, fix_instructions,
                         fast_helper_result, fast_helper_model):
    """
    Structural analysis fallback when ALL AI models fail.
    Provides factual findings based on deterministic scan data.
    Also reports the error and how to fix it.
    """
    metrics = state.get("repo_statistics", {})
    health = state.get("repo_health", {})

    def make_finding(category, observed, missing):
        return {
            "agent": f"{category} (Structural)",
            "score": None,
            "status": "Not scored (Structural Analysis)",
            "strengths": [f"Detected: {item}" for item in observed],
            "weaknesses": [f"Not detected: {item}" for item in missing],
            "critical_issues": [],
            "recommendations": [
                "AI analysis was unavailable. Run again when AI models are available for deeper analysis."
            ],
        }

    # Code Quality
    cq_observed = [
        f"{metrics.get('total_files', 0)} files",
        f"{metrics.get('lines_of_code', 0)} lines of code",
    ]
    cq_missing = []
    if not health.get("readme"):
        cq_missing.append("README")

    # Security
    sec_observed = []
    sec_missing = []

    # DevOps
    devops_observed = []
    devops_missing = []
    if health.get("docker"):
        devops_observed.append("Docker configuration")
    else:
        devops_missing.append("Docker configuration")
    if health.get("ci"):
        devops_observed.append("CI workflows")
    else:
        devops_missing.append("CI workflows")
    if health.get("tests"):
        devops_observed.append("Test files")
    else:
        devops_missing.append("Test files")

    agent_findings = {
        "code_quality": make_finding("Code Quality", cq_observed, cq_missing),
        "security": make_finding("Security", sec_observed, sec_missing),
        "devops": make_finding("DevOps", devops_observed, devops_missing),
    }
    agent_findings["devops"]["missing_practices"] = devops_missing

    logger.warning(
        "Structural fallback active. Error: %s. User message: %s",
        error_category, user_message,
    )

    return {
        "agent_findings": agent_findings,
        "analysis_mode": "structural",
        "ai_model_used": None,
        "ai_requests_log": [log.model_dump() for log in provider.request_logs],
        "evidence": evidence,
        "evidence_metadata": {
            "included": evidence.get("included_count", 0),
            "omitted": evidence.get("omitted_count", 0),
            "total_chars": evidence.get("total_chars", 0),
        },
        "fast_helper_result": fast_helper_result,
        "fast_helper_model": fast_helper_model,
        "fallback_reason": error_category,
        "error_message": user_message,
        "fix_instructions": fix_instructions,
    }
