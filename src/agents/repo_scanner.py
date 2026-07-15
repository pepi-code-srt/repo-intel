"""
RepoIntel — Repository Scanner
Deterministic scan: clone, metadata, structure, metrics, health.
Zero AI calls. All Python.
"""
import logging
from .state import RepoIntelState
from ..utils.repo_tools import (
    clone_repo, get_repo_structure, get_repo_metadata,
    read_file_content, read_source_samples,
    compute_repo_metrics, evaluate_basic_health, get_commit_sha,
)

logger = logging.getLogger(__name__)


def repo_scanner_agent(state: RepoIntelState) -> dict:
    """Clones and scans a repository. Zero AI calls."""
    repo_url = state["repo_url"]
    logger.info("Scanning repository: %s", repo_url)

    # Clone the repo
    repo_path = clone_repo(repo_url)

    if repo_path.startswith("Error"):
        logger.error("Clone failed: %s", repo_path)
        return {
            "repo_path": "",
            "repo_structure": {"_error": repo_path},
            "repo_metadata": {"error": repo_path, "full_name": repo_url},
            "readme_content": "",
            "dependencies": [],
            "source_samples": {},
            "repo_statistics": {},
            "repo_health": {},
            "analyzed_commit_sha": None,
        }

    # Get metadata (stars, forks, languages, contributors)
    metadata = get_repo_metadata(repo_url)

    # Handle GitHub API failures gracefully
    if "error" in metadata:
        metadata = {
            "full_name": repo_url.split("github.com/")[-1] if "github.com/" in repo_url else "Unknown Repository",
            "description": "Metadata fetch failed: " + metadata["error"],
            "stars": 0, "forks": 0, "open_issues": 0,
            "language": "Unknown", "languages": {},
            "contributors": [], "license": None,
        }

    # Get full directory structure
    structure = get_repo_structure(repo_path)

    # Read README
    readme = read_file_content(repo_path, "README.md", max_chars=4000)

    # Read dependency files
    dependencies = []

    # Python deps
    req_txt = read_file_content(repo_path, "requirements.txt", max_chars=2000)
    if req_txt:
        deps = [line.strip() for line in req_txt.split("\n")
                if line.strip() and not line.strip().startswith("#")]
        dependencies.extend([f"pip: {d}" for d in deps])

    # Node deps
    pkg_json = read_file_content(repo_path, "package.json", max_chars=2000)
    if pkg_json:
        import json
        try:
            pkg = json.loads(pkg_json)
            for dep_name in pkg.get("dependencies", {}):
                dependencies.append(f"npm: {dep_name}")
            for dep_name in pkg.get("devDependencies", {}):
                dependencies.append(f"npm-dev: {dep_name}")
        except json.JSONDecodeError:
            pass

    # Read sample source files
    source_samples = read_source_samples(repo_path)

    # Compute metrics
    metrics = compute_repo_metrics(repo_path)
    health = evaluate_basic_health(repo_path, metrics)

    # Get commit SHA
    commit_sha = get_commit_sha(repo_path)

    # Build summary
    primary_lang = metadata.get("language", "Unknown")
    languages = metadata.get("languages", {})
    lang_str = ", ".join([f"{lang} ({pct}%)" for lang, pct in languages.items()]) if languages else primary_lang

    logger.info(
        "Scan complete: %s — %d files, %d LOC, languages: %s",
        metadata.get("full_name", "?"),
        metrics.get("total_files", 0),
        metrics.get("lines_of_code", 0),
        lang_str,
    )

    return {
        "repo_path": repo_path,
        "repo_structure": structure,
        "repo_metadata": metadata,
        "readme_content": readme,
        "dependencies": dependencies,
        "source_samples": source_samples,
        "repo_statistics": metrics,
        "repo_health": health,
        "analyzed_commit_sha": commit_sha,
    }
