"""
RepoIntel — Evidence Selector
Deterministic evidence ranking and selection for AI analysis.
Selects the most important files and content to send to Gemini.
"""
import os
import logging
from ..config import MAX_EVIDENCE_FILES, MAX_CHARS_PER_FILE, MAX_TOTAL_EVIDENCE_CHARS
from ..utils.repo_tools import read_file_content
from ..utils.text_utils import minify_content

logger = logging.getLogger(__name__)

# File importance categories
HIGH_PRIORITY_PATTERNS = [
    "main", "app", "index", "server", "routes", "api", "auth",
    "login", "middleware", "database", "db", "models", "schema",
    "security", "crypto", "secret", "config", "settings",
    "subprocess", "exec", "command", "process",
]

MEDIUM_PRIORITY_PATTERNS = [
    "utils", "helpers", "services", "controllers", "views",
    "handlers", "manager", "factory", "client", "connection",
    "test", "spec", "dockerfile", "docker-compose",
    "requirements", "package", "pyproject", "setup",
]

# File types to include
SOURCE_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".go", ".rs",
    ".rb", ".php", ".cs", ".cpp", ".c", ".h", ".swift", ".kt",
}

CONFIG_EXTENSIONS = {
    ".yml", ".yaml", ".json", ".toml", ".ini", ".cfg", ".env.example",
}

SKIP_DIRS = {
    '.git', 'node_modules', 'venv', '.venv', '__pycache__', 'dist',
    'build', 'coverage', 'vendor', '.tox', '.mypy_cache', '.pytest_cache',
    'public', 'assets', 'static',
}

SKIP_FILES = {
    'package-lock.json', 'yarn.lock', 'pnpm-lock.yaml', 'poetry.lock',
    'Pipfile.lock', 'composer.lock', 'Gemfile.lock',
}


def select_evidence(repo_path: str, source_samples: dict = None) -> dict:
    """
    Select and rank the most important files for AI analysis.

    Returns:
        {
            "selected_files": {rel_path: content, ...},
            "total_chars": int,
            "included_count": int,
            "omitted_count": int,
            "omitted_reasons": [{"file": path, "reason": reason}, ...],
        }
    """
    if source_samples is None:
        source_samples = {}

    all_candidates = []

    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith('.')]

        for filename in files:
            if filename in SKIP_FILES:
                continue

            _, ext = os.path.splitext(filename)
            ext_lower = ext.lower()
            filename_lower = filename.lower()
            name_no_ext = os.path.splitext(filename_lower)[0]

            # Only include source code and config files
            is_source = ext_lower in SOURCE_EXTENSIONS
            is_config = ext_lower in CONFIG_EXTENSIONS or filename_lower in (
                "dockerfile", "makefile", "procfile", ".env.example",
            )

            if not is_source and not is_config:
                continue

            filepath = os.path.join(root, filename)
            rel_path = os.path.relpath(filepath, repo_path).replace("\\", "/")

            # Score the file
            score = _score_file(name_no_ext, filename_lower, rel_path, is_source, is_config)
            all_candidates.append((score, filepath, rel_path))

    # Sort by score descending
    all_candidates.sort(key=lambda x: x[0], reverse=True)

    # Select within budget
    selected = {}
    total_chars = 0
    omitted = []

    for score, filepath, rel_path in all_candidates:
        if len(selected) >= MAX_EVIDENCE_FILES:
            omitted.append({"file": rel_path, "reason": "max_files_reached"})
            continue

        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read(MAX_CHARS_PER_FILE)

            if not content.strip():
                omitted.append({"file": rel_path, "reason": "empty_file"})
                continue

            if len(content) == MAX_CHARS_PER_FILE:
                content += "\n...(truncated)"

            # Check total budget
            if total_chars + len(content) > MAX_TOTAL_EVIDENCE_CHARS and len(selected) > 0:
                omitted.append({"file": rel_path, "reason": "total_chars_budget"})
                continue

            selected[rel_path] = minify_content(content)
            total_chars += len(content)

        except Exception:
            omitted.append({"file": rel_path, "reason": "read_error"})
            continue

    logger.info(
        "Evidence selected: %d files (%d chars), %d omitted",
        len(selected), total_chars, len(omitted),
    )

    return {
        "selected_files": selected,
        "total_chars": total_chars,
        "included_count": len(selected),
        "omitted_count": len(omitted),
        "omitted_reasons": omitted[:20],  # Cap omitted list
    }


def _score_file(name_no_ext: str, filename_lower: str, rel_path: str,
                is_source: bool, is_config: bool) -> int:
    """Score a file by importance for security/architecture review."""
    score = 0

    # High priority patterns
    for pattern in HIGH_PRIORITY_PATTERNS:
        if pattern == name_no_ext:
            score += 60
            break
        elif pattern in name_no_ext:
            score += 30
            break

    # Medium priority patterns
    if score == 0:
        for pattern in MEDIUM_PRIORITY_PATTERNS:
            if pattern == name_no_ext:
                score += 20
                break
            elif pattern in name_no_ext:
                score += 10
                break

    # Dockerfile/docker-compose always important
    if filename_lower in ("dockerfile", "docker-compose.yml", "docker-compose.yaml"):
        score += 40

    # Source code more important than config for deeper analysis
    if is_source:
        score += 5

    # Test files are useful but lower priority
    is_test = (name_no_ext.startswith("test_") or name_no_ext.endswith("_test") or
               "spec" in name_no_ext)
    if is_test:
        score -= 10

    # Penalize deep nesting
    depth = rel_path.count("/")
    score -= (depth * 3)

    return score


def format_evidence_for_prompt(evidence: dict, repo_metadata: dict = None) -> str:
    """Format selected evidence into a prompt-friendly string."""
    selected = evidence.get("selected_files", {})
    parts = []

    if repo_metadata:
        parts.append("## Repository Identity")
        parts.append(f"Name: {repo_metadata.get('full_name', 'Unknown')}")
        parts.append(f"Description: {repo_metadata.get('description', 'No description')}")
        parts.append(f"Primary Language: {repo_metadata.get('language', 'Unknown')}")
        parts.append("")

    parts.append(f"## Source Evidence ({len(selected)} files, {evidence.get('total_chars', 0)} chars)")
    parts.append("")

    for rel_path, content in selected.items():
        parts.append(f"--- {rel_path} ---")
        parts.append(content)
        parts.append("")

    return "\n".join(parts)
