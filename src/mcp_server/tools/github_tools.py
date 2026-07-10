import os
import shutil
import tempfile
from git import Repo
import requests

def clone_repo(repo_url: str) -> str:
    """Clones a GitHub repository to a temporary directory."""
    temp_dir = tempfile.mkdtemp(prefix="repo-intel-")
    try:
        Repo.clone_from(repo_url, temp_dir)
        return temp_dir
    except Exception as e:
        return f"Error cloning repo: {str(e)}"

def get_repo_structure(repo_path: str, max_depth: int = 3) -> dict:
    """Returns the directory structure of the cloned repository."""
    if not os.path.exists(repo_path):
        return {"error": "Repository path does not exist."}
    
    def _build_tree(dir_path, current_depth):
        if current_depth > max_depth:
            return "..."
        tree = {}
        try:
            for item in sorted(os.listdir(dir_path)):
                if item.startswith('.') and item != '.github':
                    continue
                item_path = os.path.join(dir_path, item)
                if os.path.isdir(item_path):
                    tree[item] = _build_tree(item_path, current_depth + 1)
                else:
                    tree[item] = "file"
        except Exception:
            pass
        return tree

    return _build_tree(repo_path, 1)

def get_repo_metadata(repo_url: str) -> dict:
    """Fetches basic metadata about the repository using GitHub's public API."""
    if "github.com/" not in repo_url:
        return {"error": "Not a valid GitHub URL."}
    
    parts = repo_url.rstrip('/').split('github.com/')
    if len(parts) < 2:
         return {"error": "Invalid GitHub URL format."}
         
    repo_path = parts[1]
    if repo_path.endswith('.git'):
        repo_path = repo_path[:-4]
        
    api_url = f"https://api.github.com/repos/{repo_path}"
    headers = {"Accept": "application/vnd.github.v3+json"}
    
    try:
        response = requests.get(api_url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            metadata = {
                "name": data.get("name"),
                "full_name": data.get("full_name"),
                "description": data.get("description"),
                "stars": data.get("stargazers_count"),
                "forks": data.get("forks_count"),
                "open_issues": data.get("open_issues_count"),
                "language": data.get("language"),
                "updated_at": data.get("updated_at"),
                "created_at": data.get("created_at"),
                "default_branch": data.get("default_branch"),
                "topics": data.get("topics", []),
                "license": data.get("license", {}).get("name") if data.get("license") else None,
            }
            
            # Fetch language breakdown
            lang_url = f"{api_url}/languages"
            lang_resp = requests.get(lang_url, headers=headers, timeout=10)
            if lang_resp.status_code == 200:
                lang_data = lang_resp.json()
                total_bytes = sum(lang_data.values()) if lang_data else 1
                metadata["languages"] = {
                    lang: round((bytes_count / total_bytes) * 100, 1)
                    for lang, bytes_count in lang_data.items()
                }
            else:
                metadata["languages"] = {}
            
            # Fetch contributors (top 5)
            contrib_url = f"{api_url}/contributors?per_page=5"
            contrib_resp = requests.get(contrib_url, headers=headers, timeout=10)
            if contrib_resp.status_code == 200:
                metadata["contributors"] = [
                    {"login": c.get("login"), "contributions": c.get("contributions")}
                    for c in contrib_resp.json()
                ]
            else:
                metadata["contributors"] = []
            
            return metadata
        return {"error": f"GitHub API returned {response.status_code}"}
    except Exception as e:
        return {"error": f"API request failed: {str(e)}"}


def read_file_content(repo_path: str, filename: str, max_chars: int = 3000) -> str:
    """Reads a file from the cloned repo, returns its content truncated to max_chars."""
    filepath = os.path.join(repo_path, filename)
    if not os.path.exists(filepath):
        return ""
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read(max_chars)
        if len(content) == max_chars:
            content += "\n...(truncated)"
        return content
    except Exception:
        return ""


def read_source_samples(repo_path: str, extensions: list = None, max_files: int = 3, max_chars_per_file: int = 2000) -> dict:
    """Reads a few key source files from the repo for analysis.
    
    Returns a dict of {relative_path: content} for up to max_files files.
    """
    if extensions is None:
        extensions = [".py", ".js", ".ts", ".java", ".go", ".rs"]
    
    samples = {}
    
    for root, dirs, files in os.walk(repo_path):
        # Skip hidden dirs, node_modules, venv, __pycache__
        dirs[:] = [d for d in dirs if not d.startswith('.') 
                   and d not in ('node_modules', 'venv', '.venv', '__pycache__', 'dist', 'build')]
        
        for filename in files:
            if len(samples) >= max_files:
                return samples
            
            _, ext = os.path.splitext(filename)
            if ext.lower() not in extensions:
                continue
            
            # Skip test files and config files for main code analysis
            if filename.startswith("test_") or filename == "setup.py" or filename == "conftest.py":
                continue
            
            filepath = os.path.join(root, filename)
            rel_path = os.path.relpath(filepath, repo_path)
            
            try:
                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read(max_chars_per_file)
                if content.strip():
                    if len(content) == max_chars_per_file:
                        content += "\n...(truncated)"
                    samples[rel_path] = content
            except Exception:
                continue
    
    return samples

def compute_repo_metrics(repo_path: str) -> dict:
    """Computes deterministic metrics about the repository."""
    metrics = {
        "total_files": 0,
        "python_files": 0,
        "js_files": 0,
        "lines_of_code": 0,
        "tests_found": 0,
        "docker_files": 0,
        "github_actions": 0
    }
    
    if not os.path.exists(repo_path):
        return metrics
        
    for root, dirs, files in os.walk(repo_path):
        # Exclude common large/hidden directories
        dirs[:] = [d for d in dirs if d not in ('.git', 'node_modules', 'venv', '.venv', '__pycache__', 'dist', 'build')]
        
        for file in files:
            metrics["total_files"] += 1
            file_lower = file.lower()
            
            if file_lower.endswith(".py"):
                metrics["python_files"] += 1
            elif file_lower.endswith(".js") or file_lower.endswith(".ts"):
                metrics["js_files"] += 1
                
            if "test" in file_lower:
                metrics["tests_found"] += 1
                
            if "dockerfile" in file_lower:
                metrics["docker_files"] += 1
                
            if ".github" in root.replace('\\', '/') and "workflows" in root.replace('\\', '/'):
                metrics["github_actions"] += 1
                
            # Count lines of code (simple heuristic, only for source files)
            if file_lower.endswith((".py", ".js", ".ts", ".java", ".go", ".rs", ".html", ".css", ".md")):
                filepath = os.path.join(root, file)
                try:
                    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                        metrics["lines_of_code"] += sum(1 for _ in f)
                except Exception:
                    pass
                    
    return metrics

def evaluate_basic_health(repo_path: str, metrics: dict) -> dict:
    """Evaluates basic repository health flags."""
    health = {
        "tests": metrics.get("tests_found", 0) > 0,
        "docker": metrics.get("docker_files", 0) > 0,
        "ci": metrics.get("github_actions", 0) > 0,
        "readme": os.path.exists(os.path.join(repo_path, "README.md")) or os.path.exists(os.path.join(repo_path, "readme.md")),
        "license": os.path.exists(os.path.join(repo_path, "LICENSE")) or os.path.exists(os.path.join(repo_path, "LICENSE.md")),
    }
    return health
