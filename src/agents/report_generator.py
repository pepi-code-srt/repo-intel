"""
RepoIntel — Report Generator
Builds the final markdown report from structured findings.
Pure Python — zero AI calls.
"""
import time
import logging
from datetime import datetime, timezone
from .state import RepoIntelState

logger = logging.getLogger(__name__)


def build_deterministic_report(state: RepoIntelState) -> str:
    """Build a rich markdown report from structured data."""
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
    contrib_str = ", ".join(
        [f"**{c['login']}** ({c['contributions']} commits)" for c in contributors]
    ) if contributors else "Unknown"

    # Analysis mode display
    mode = state.get("analysis_mode", "structural")
    ai_model = state.get("ai_model_used")
    fast_helper_model = state.get("fast_helper_model")

    if mode == "ai_enhanced":
        mode_display = "AI Enhanced"
        ai_status = f"Completed (model: {ai_model})"
    elif mode == "ai_enhanced_fallback":
        mode_display = "AI Enhanced (Fallback Model)"
        ai_status = f"Completed via fallback (model: {ai_model})"
    else:
        mode_display = "Structural Analysis"
        ai_status = "Not available"

    # Scores
    scores = []
    for key in ["code_quality", "security", "devops"]:
        f = agent_findings.get(key, {})
        s = f.get("score")
        if s is not None:
            scores.append(s)

    if scores:
        overall = round(sum(scores) / len(scores), 1)
        if overall >= 8:
            verdict = "Production-Ready"
        elif overall >= 5:
            verdict = "Needs Work"
        else:
            verdict = "High Risk"
    else:
        overall = "N/A"
        verdict = "Structural Analysis Only"

    # Format scores for display
    def format_score(findings, key):
        f = findings.get(key, {})
        score = f.get("score")
        status = f.get("status", "N/A")
        if score is not None:
            return f"{score}/10", status
        return "N/A", status

    cq_score, cq_status = format_score(agent_findings, "code_quality")
    sec_score, sec_status = format_score(agent_findings, "security")
    devops_score, devops_status = format_score(agent_findings, "devops")

    # Collect findings
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

    all_critical = []
    for key in ["code_quality", "security", "devops"]:
        f = agent_findings.get(key, {})
        for issue in f.get("critical_issues", []):
            if isinstance(issue, dict):
                name = issue.get("name", "Issue")
                problem = issue.get("problem", "N/A")
                all_critical.append(f"**{name}** — {problem}")
            else:
                all_critical.append(str(issue))

    all_weaknesses = []
    for key in ["code_quality", "security", "devops"]:
        f = agent_findings.get(key, {})
        for w in f.get("weaknesses", []):
            if w not in all_weaknesses:
                all_weaknesses.append(w)

    all_recs = []
    for key in ["code_quality", "security", "devops"]:
        f = agent_findings.get(key, {})
        for r in f.get("recommendations", []):
            all_recs.append(r)

    all_strengths = []
    for key in ["code_quality", "security", "devops"]:
        f = agent_findings.get(key, {})
        for s in f.get("strengths", [])[:3]:
            all_strengths.append(s)

    # Format sections
    missing_section = "\n".join(f"- 🔴 {m}" for m in missing_items) if missing_items else "- ✅ All essential files present"
    critical_section = "\n".join(f"- {c}" for c in all_critical) if all_critical else "- None detected"
    debt_section = "\n".join(f"- ⚠️ {w}" for w in all_weaknesses) if all_weaknesses else "- None detected"
    strengths_section = "\n".join(f"- ✅ {s}" for s in all_strengths) if all_strengths else "- No notable strengths detected"

    immediate = all_recs[:3]
    short_term = all_recs[3:6]
    long_term = all_recs[6:]

    def numbered_list(items):
        return "\n".join(f"{i+1}. {item}" for i, item in enumerate(items)) if items else "- None"

    # Evidence stats
    evidence_meta = state.get("evidence_metadata", {})
    evidence_included = evidence_meta.get("included", 0)
    evidence_chars = evidence_meta.get("total_chars", 0)

    # AI requests summary
    ai_logs = state.get("ai_requests_log", [])
    ai_calls_count = len([l for l in ai_logs if l.get("status") == "success"])

    # Error info for structural mode
    error_section = ""
    error_msg = state.get("error_message")
    fix_instr = state.get("fix_instructions")
    if error_msg and mode == "structural":
        error_section = f"""
---

## ⚠️ AI Analysis Unavailable

{error_msg}

**How to fix:**
```
{fix_instr}
```
"""

    now = datetime.now(timezone.utc).strftime('%B %d, %Y at %H:%M UTC')

    report = f"""# 🔍 Intelligence Report: {repo_name}

**Verdict: {verdict}** | **Overall Score: {overall}/10**

> *Generated {now}*

**Provenance:**
- **Analysis Mode**: {mode_display}
- **AI Model**: {ai_model or "None"}
- **Fast Helper**: {fast_helper_model or "Not used"}
- **Structural Scan**: Completed
- **AI Analysis**: {ai_status}
- **Evidence Files**: {evidence_included} files ({evidence_chars:,} chars)
- **AI Calls**: {ai_calls_count} successful

---

## 📊 Scorecard

| Category | Score | Verdict |
|---|---|---|
| Code Quality & Architecture | {cq_score} | {cq_status} |
| Security | {sec_score} | {sec_status} |
| DevOps & Production Readiness | {devops_score} | {devops_status} |

---

## 📈 Codebase Stats

| Metric | Value |
|---|---|
| Total Files | {metrics.get('total_files', 'N/A')} |
| Lines of Code | {metrics.get('lines_of_code', 0):,} |
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

{strengths_section}

---

## 🗺️ Action Plan

### Immediate (This Week)
{numbered_list(immediate)}

### Short-Term (This Month)
{numbered_list(short_term)}

### Long-Term (This Quarter)
{numbered_list(long_term)}
{error_section}
---

> ⚠️ This report was generated by AI analysis agents. Verify findings against your codebase before acting.
"""
    return report


def report_generator_agent(state: RepoIntelState) -> dict:
    """Generates the final markdown report. Zero AI calls."""
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
        }

    logger.info("Generating final report for %s", repo_name)

    start_time = time.time()
    report = build_deterministic_report(state)
    elapsed = time.time() - start_time

    report_metadata = {
        "repository": repo_name,
        "analysis_mode": state.get("analysis_mode", "structural"),
        "ai_model": state.get("ai_model_used"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generation_time_sec": round(elapsed, 2),
    }

    return {
        "final_report": report,
        "report_metadata": report_metadata,
    }
