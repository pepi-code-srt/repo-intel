import os
import json
import hashlib
import logging
from pathlib import Path
from ..config import MODEL_NAME

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).parent.parent.parent / ".repo_cache"

def get_cache_key(repo_url: str, commit_sha: str, mode: str) -> str:
    """Generates a stable cache key for a specific repository, commit, and analysis mode."""
    if not commit_sha:
        return None
    raw = f"{repo_url}:{commit_sha}:{mode}:{MODEL_NAME}:v1"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def check_cache(repo_url: str, commit_sha: str, mode: str) -> dict:
    """Checks if a valid analysis exists in the cache."""
    key = get_cache_key(repo_url, commit_sha, mode)
    if not key:
        return None
        
    cache_path = CACHE_DIR / f"{key}.json"
    if cache_path.exists():
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                logger.info(f"Cache hit for {repo_url} at commit {commit_sha[:7]} ({mode} mode)")
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to read cache file {cache_path}: {e}")
    
    logger.info(f"Cache miss for {repo_url} at commit {commit_sha[:7] if commit_sha else 'unknown'}")
    return None

def write_cache(repo_url: str, commit_sha: str, mode: str, findings: dict):
    """Writes structured analysis findings to the cache."""
    key = get_cache_key(repo_url, commit_sha, mode)
    if not key:
        return
        
    CACHE_DIR.mkdir(exist_ok=True)
    cache_path = CACHE_DIR / f"{key}.json"
    
    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(findings, f, indent=2)
            logger.info(f"Wrote cache for {repo_url} at commit {commit_sha[:7]} ({mode} mode)")
    except Exception as e:
        logger.error(f"Failed to write cache file {cache_path}: {e}")
