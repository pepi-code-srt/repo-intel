def minify_content(content: str) -> str:
    """Remove consecutive blank lines and excessive trailing whitespace."""
    return "\n".join(line.rstrip() for line in content.splitlines() if line.strip()) if content else ""
