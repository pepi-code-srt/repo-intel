import os
import json

def parse_requirements(file_path: str) -> list:
    """Parses a requirements.txt file and returns a list of dependencies."""
    if not os.path.exists(file_path):
        return []
        
    deps = []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    deps.append(line.split('==')[0].split('>=')[0].strip())
    except Exception:
        pass
    return deps

def parse_package_json(file_path: str) -> dict:
    """Parses a package.json file and returns dependencies."""
    if not os.path.exists(file_path):
        return {}
        
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return {
                "dependencies": list(data.get("dependencies", {}).keys()),
                "devDependencies": list(data.get("devDependencies", {}).keys())
            }
    except Exception:
        return {}
