import os

def read_file(file_path: str) -> str:
    """Reads the contents of a specific file."""
    if not os.path.exists(file_path):
        return f"Error: File not found at {file_path}"
    
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            return content
    except UnicodeDecodeError:
        return "Error: Binary file or invalid encoding."
    except Exception as e:
        return f"Error reading file: {str(e)}"
