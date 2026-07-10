import time
import json
import logging
from datetime import datetime
from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate
from .state import RepoIntelState
from ..config import MODEL_NAME
from ..prompts.report_prompt import REPORT_PROMPT
from ..utils.llm_manager import invoke_llm_with_retry

logger = logging.getLogger(__name__)


def _build_fallback_report(state: RepoIntelState) -> str:
    """Build a rich markdown report from structured data WITHOUT calling the LLM."""
    metadata = state.get("repo_metadata", {})
    agent_findings = state.get("agent_findings", {})
    metrics = state.get("repo_statistics", {})
    health = state.get("repo_health", {})
    
    repo_name = metadata.get("full_name", state.get("repo_url", "Unknown"))
    description = metadata.get("description", "No description provided")
    license_name = metadata.get("license", "Not specified")
    stars = metadata.get("stars", 0)
    forks = metadata.get("forks", 0)
    open_issues = metadata.get("open_issues", 0)
    
    languages = metadata.get("languages", {})
    lang_str = ", ".join([f"{lang} ({pct}%)" for lang, pct in languages.items()]) if languages else "Unknown"
    
    contributors = metadata.get("contributors", [])
    contrib_str = ", ".join([f"**{c['login']}** ({c['contributions']} commits)" for c in contributors]) if contributors else "Unknown"
    
    # --- Health badges ---
    def badge(val):
        return "✅" if val else "❌"
    
    # --- Build category sections ---
    def format_category(title: str, emoji: str, findings: dict) -> str:
        if not findings:
            return f"### {emoji} {title}\n\n> No data available.\n"
        
        score = findings.get("score")
        status = findings.get("status", "N/A")
        
        # Score bar
        if score is not None:
            filled = "█" * score + "░" * (10 - score)
            score_line = f"**Score: {score}/10** `[{filled}]` — *{status}*"
        else:
            score_line = f"**Score:** N/A — *{status}*"
        
        section = f"### {emoji} {title}\n\n{score_line}\n\n"
        
        strengths = findings.get("strengths", [])
        if strengths:
            section += "**Strengths:**\n"
            for s in strengths:
                section += f"- ✅ {s}\n"
            section += "\n"
        
        weaknesses = findings.get("weaknesses", [])
        if weaknesses:
            section += "**Weaknesses:**\n"
            for w in weaknesses:
                section += f"- ⚠️ {w}\n"
            section += "\n"
        
        critical = findings.get("critical_issues", [])
        if critical:
            section += "**🚨 Critical Issues:**\n\n"
            for issue in critical:
                if isinstance(issue, dict):
                    section += f"- **{issue.get('name', 'Issue')}** (Severity: {issue.get('severity', 'Unknown')})\n"
                    section += f"  - *Problem:* {issue.get('problem', 'N/A')}\n"
                    section += f"  - *Solution:* {issue.get('solution', 'N/A')}\n"
                else:
                    section += f"- {issue}\n"
            section += "\n"
        
        recs = findings.get("recommendations", [])
        if recs:
            section += "**Recommendations:**\n"
            for r in recs:
                section += f"1. {r}\n"
            section += "\n"
        
        missing = findings.get("missing_practices", [])
        if missing:
            section += "**Missing Practices:** " + ", ".join(f"`{m}`" for m in missing) + "\n\n"
        
        return section
    
    # --- Compute overall score ---
    scores = []
    for key in ["code_quality", "security", "devops"]:
        f = agent_findings.get(key, {})
        s = f.get("score")
        if s is not None:
            scores.append(s)
    overall = round(sum(scores) / len(scores), 1) if scores else "N/A"
    
    # --- Determine verdict ---
    if isinstance(overall, (int, float)):
        if overall >= 8:
            verdict = "Production-Ready"
        elif overall >= 5:
            verdict = "Needs Work"
        else:
            verdict = "High Risk"
    else:
        verdict = "Insufficient Data"
    
    # --- Collect missing things ---
    missing_items = []
    if not health.get("tests"):
        missing_items.append("No automated tests detected — critical logic is unverified")
    if not health.get("docker"):
        missing_items.append("No Docker configuration — not containerized for deployment")
    if not health.get("ci"):
        missing_items.append("No CI/CD pipeline — code changes aren't automatically validated")
    if not health.get("license"):
        missing_items.append("No LICENSE file — legal usage is undefined")
    if not health.get("readme"):
        missing_items.append("No README — project is undocumented")
    if metrics.get("tests_found", 0) == 0:
        missing_items.append("Zero test files found across entire codebase")
    
    # Collect all critical issues
    all_critical = []
    for key in ["code_quality", "security", "devops"]:
        f = agent_findings.get(key, {})
        for issue in f.get("critical_issues", []):
            if isinstance(issue, dict):
                all_critical.append(f"**{issue.get('name', 'Issue')}** — {issue.get('problem', 'N/A')}")
            else:
                all_critical.append(str(issue))
    
    # Collect all weaknesses as tech debt
    all_weaknesses = []
    for key in ["code_quality", "security", "devops"]:
        f = agent_findings.get(key, {})
        for w in f.get("weaknesses", []):
            all_weaknesses.append(w)
    
    # Collect all recommendations
    all_recs = []
    for key in ["code_quality", "security", "devops"]:
        f = agent_findings.get(key, {})
        for r in f.get("recommendations", []):
            all_recs.append(r)
    
    missing_section = "\n".join(f"- 🔴 {m}" for m in missing_items) if missing_items else "- ✅ All essential files present"
    critical_section = "\n".join(f"- {c}" for c in all_critical) if all_critical else "- None detected"
    debt_section = "\n".join(f"- ⚠️ {w}" for w in all_weaknesses) if all_weaknesses else "- None detected"
    
    # Split recommendations into phases
    immediate = all_recs[:3] if len(all_recs) >= 3 else all_recs
    short_term = all_recs[3:6] if len(all_recs) > 3 else []
    long_term = all_recs[6:] if len(all_recs) > 6 else []
    
    def numbered_list(items):
        return "\n".join(f"{i+1}. {item}" for i, item in enumerate(items)) if items else "- None"
    
    # --- Assemble report ---
    report = f"""# 🔍 Intelligence Report: {repo_name}

**Verdict: {verdict}** | **Overall Score: {overall}/10**

> *Generated {datetime.utcnow().strftime('%B %d, %Y at %H:%M UTC')} • Structured analysis (quota-optimized)*

---

## 📊 Scorecard

| Category | Score | Verdict |
|---|---|---|
| Code Quality & Architecture | {agent_findings.get('code_quality', {}).get('score', 'N/A')}/10 | {agent_findings.get('code_quality', {}).get('status', 'N/A')} |
| Security | {agent_findings.get('security', {}).get('score', 'N/A')}/10 | {agent_findings.get('security', {}).get('status', 'N/A')} |
| DevOps & Production Readiness | {agent_findings.get('devops', {}).get('score', 'N/A')}/10 | {agent_findings.get('devops', {}).get('status', 'N/A')} |

---

## 📈 Codebase Stats

| Metric | Value |
|---|---|
| Total Files | {metrics.get('total_files', 'N/A')} |
| Lines of Code | {metrics.get('lines_of_code', 'N/A'):,} |
| Test Files | {metrics.get('tests_found', 0)} |
| Docker Files | {metrics.get('docker_files', 0)} |
| CI Workflows | {metrics.get('github_actions', 0)} |
| Stars | ⭐ {stars} |
| Forks | 🍴 {forks} |

---

## 🚨 What's Missing (That Should Exist)

{missing_section}

---

## 🔴 Critical Risks

{critical_section}

---

## 🟡 Technical Debt

{debt_section}

---

## 🟢 What's Done Right

{chr(10).join(f'- ✅ {s}' for cat in ['code_quality', 'security', 'devops'] for s in agent_findings.get(cat, {}).get('strengths', [])[:2]) or '- No notable strengths detected'}

---

## 🗺️ Action Plan

### Immediate (This Week)
{numbered_list(immediate)}

### Short-Term (This Month)
{numbered_list(short_term)}

### Long-Term (This Quarter)
{numbered_list(long_term)}

---

> ⚠️ This report was generated by AI analysis agents. Verify findings before acting.
"""
    return report


def report_generator_agent(state: RepoIntelState) -> dict:
    repo_url = state.get("repo_url", "Unknown")
    repo_name = state.get("repo_metadata", {}).get("full_name", repo_url)
    
    # Check if repo scanning failed
    repo_structure = state.get("repo_structure", {})
    if isinstance(repo_structure, dict) and "_error" in repo_structure:
        error_msg = repo_structure["_error"]
        report = (
            f"# Repository Analysis Failed\n\n"
            f"**Repository:** {repo_name}\n\n"
            f"## Error\n\n"
            f"The repository could not be cloned or accessed.\n\n"
            f"**Details:** `{error_msg}`\n\n"
            f"### Possible causes:\n"
            f"- The repository URL is invalid or misspelled\n"
            f"- The repository is private and requires authentication\n"
            f"- The repository has been deleted or moved\n"
            f"- Network connectivity issues\n\n"
            f"Please verify the URL and try again."
        )
        return {
            "final_report": report,
            "report_metadata": {
                "repository": repo_name,
                "status": "failed",
                "error": error_msg,
            },
            "messages": [AIMessage(content=f"Report generated with scan failure for {repo_name}.")],
        }
    
    logger.info("Generating final structured report for %s", repo_name)
    
    # 1. Gather all structured findings
    agent_findings = state.get("agent_findings", {})
    agent_findings_str = json.dumps(agent_findings, indent=2)
    
    # 2. Gather metrics and health
    metrics = state.get("repo_statistics", {})
    health = state.get("repo_health", {})
    metrics_str = json.dumps(metrics, indent=2)
    health_str = json.dumps(health, indent=2)
    
    # 3. Build metadata section
    metadata = state.get("repo_metadata", {})
    description = metadata.get("description", "No description provided")
    license_name = metadata.get("license", "Not specified")
    
    languages = metadata.get("languages", {})
    lang_str = ", ".join([f"{lang} ({pct}%)" for lang, pct in languages.items()]) if languages else "Unknown"
    
    # 4. Use ChatPromptTemplate
    prompt = ChatPromptTemplate.from_template(REPORT_PROMPT)
    messages = prompt.format_messages(
        repo_name=repo_name,
        description=description,
        license=license_name,
        languages=lang_str,
        metrics_str=metrics_str,
        health_str=health_str,
        agent_findings_str=agent_findings_str
    )
    
    # Calculate execution metrics
    prompt_length = len(messages[0].content) if messages else 0
    message_count = len(state.get("messages", []))
    
    start_time = time.time()
    
    try:
        response = invoke_llm_with_retry(messages)
        report = getattr(response, "content", "")
        if not report:
            report = "Gemini returned an empty report."
            
        response_length = len(report)
    except Exception as exc:
        exc_str = str(exc)
        logger.error("Report generation failed: %s", exc_str)
        
        # Build a proper formatted report from structured data instead of raw JSON
        report = _build_fallback_report(state)
            
        return {
            "final_report": report,
            "messages": [
                AIMessage(content="Report generation failed due to API constraints. Partial results saved.")
            ],
        }
        
    elapsed = time.time() - start_time
    
    # Update report metadata with execution metrics
    report_metadata = {
        "repository": repo_name,
        "model": MODEL_NAME,
        "generated_at": datetime.utcnow().isoformat(),
        "generation_time_sec": round(elapsed, 2),
        "prompt_length": prompt_length,
        "response_length": response_length,
        "message_count": message_count,
        "agent_findings_count": len(agent_findings)
    }
    
    return {
        "final_report": report,
        "report_metadata": report_metadata,
        "messages": [
            AIMessage(content=f"Final report generated from structured findings in {elapsed:.2f}s.")
        ]
    }
