from langchain_core.messages import AIMessage
from .state import RepoIntelState
from ..mcp_server.tools.github_tools import (
    clone_repo, get_repo_structure, get_repo_metadata,
    read_file_content, read_source_samples,
    compute_repo_metrics, evaluate_basic_health
)

def repo_scanner_agent(state: RepoIntelState) -> dict:
    repo_url = state["repo_url"]
    
    # Clone the repo
    repo_path = clone_repo(repo_url)
    
    if repo_path.startswith("Error"):
        return {
            "messages": [AIMessage(content=f"Failed to clone: {repo_path}")],
            "repo_structure": {"_error": repo_path},
            "repo_metadata": {"error": repo_path, "full_name": repo_url},
            "repo_statistics": {},
            "repo_health": {},
        }
        
    # Get metadata (stars, forks, languages, contributors)
    metadata = get_repo_metadata(repo_url)
    
    # Handle GitHub API failures (e.g. rate limit, 404, invalid link) gracefully
    if "error" in metadata:
        metadata = {
            "full_name": repo_url.split("github.com/")[-1] if "github.com/" in repo_url else "Unknown Repository",
            "description": "Metadata fetch failed: " + metadata["error"],
            "stars": 0, "forks": 0, "open_issues": 0,
            "language": "Unknown", "languages": {},
            "contributors": [], "license": None
        }
    
    # Get full directory structure
    structure = get_repo_structure(repo_path)
    
    # Read README.md
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
    
    # Read sample source files for downstream agents
    source_samples = read_source_samples(repo_path, max_files=4, max_chars_per_file=2000)
    
    # Build a rich deterministic summary (0 LLM tokens used)
    primary_lang = metadata.get("language", "Unknown")
    languages = metadata.get("languages", {})
    lang_str = ", ".join([f"{lang} ({pct}%)" for lang, pct in languages.items()]) if languages else primary_lang
    
    contributors = metadata.get("contributors", [])
    contrib_str = ", ".join([f"{c['login']} ({c['contributions']} commits)" for c in contributors]) if contributors else "Unknown"
    
    frameworks = []
    if "package.json" in structure:
        frameworks.append("Node.js/NPM")
    if "requirements.txt" in structure or "pyproject.toml" in structure:
        frameworks.append("Python")
    if "Dockerfile" in structure:
        frameworks.append("Docker")
    if "docker-compose.yml" in structure or "docker-compose.yaml" in structure:
        frameworks.append("Docker Compose")
    if ".github" in structure:
        frameworks.append("GitHub Actions")
    
    findings = f"""Repo Scanner Findings:
- Name: {metadata.get('full_name', 'Unknown')}
- Description: {metadata.get('description', 'No description')}
- Languages: {lang_str}
- Frameworks: {', '.join(frameworks) if frameworks else 'None detected'}
- Stars: {metadata.get('stars', 0)} | Forks: {metadata.get('forks', 0)} | Open Issues: {metadata.get('open_issues', 0)}
- Contributors: {contrib_str}
- License: {metadata.get('license', 'None')}
- Dependencies: {len(dependencies)} packages found
- Source files sampled: {len(source_samples)} files"""
    
    metrics = compute_repo_metrics(repo_path)
    health = evaluate_basic_health(repo_path, metrics)
    
    return {
        "repo_path": repo_path,
        "repo_structure": structure,
        "repo_metadata": metadata,
        "readme_content": readme,
        "dependencies": dependencies,
        "source_samples": source_samples,
        "repo_statistics": metrics,
        "repo_health": health,
        "messages": [AIMessage(content=findings.strip())]
    }
