"""
RepoIntel — Central Configuration
All model names, task routing, and environment configuration in one place.
"""
from dotenv import load_dotenv
from pathlib import Path
import os

# Use absolute path to .env to avoid CWD issues
load_dotenv(Path(__file__).parent.parent / ".env")

# === API Key ===
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

if not GEMINI_API_KEY:
    raise RuntimeError(
        "No API key found. "
        "Add GEMINI_API_KEY to your .env file."
    )

# === Model Configuration ===
# Strongest model first. If it's busy (503) or rate-limited (429),
# the provider automatically cascades to the next model.
# gemini-3.5-flash = strongest reasoning, low quota (5 RPM, 20 RPD)
# gemini-3.1-flash-lite = fast, high quota (15 RPM, 500 RPD)
GEMINI_MODEL_PRIMARY = os.getenv("GEMINI_MODEL_PRIMARY", "gemini-3.5-flash")
GEMINI_MODEL_FAST = os.getenv("GEMINI_MODEL_FAST", "gemini-3.1-flash-lite")
GEMINI_MODEL_FALLBACK = os.getenv("GEMINI_MODEL_FALLBACK", "gemini-3.1-flash-lite")

# === Evidence Limits ===
MAX_EVIDENCE_FILES = int(os.getenv("MAX_EVIDENCE_FILES", "15"))
MAX_CHARS_PER_FILE = int(os.getenv("MAX_CHARS_PER_FILE", "4000"))
MAX_TOTAL_EVIDENCE_CHARS = int(os.getenv("MAX_TOTAL_EVIDENCE_CHARS", "40000"))

# === Optional Features ===
ENABLE_FAST_HELPER = os.getenv("ENABLE_FAST_HELPER", "true").lower() == "true"


def get_model_config() -> dict:
    """Returns the current model configuration as a dict of role -> model_id."""
    return {
        "primary": GEMINI_MODEL_PRIMARY,
        "fast": GEMINI_MODEL_FAST,
        "fallback": GEMINI_MODEL_FALLBACK,
    }


def get_model_cascade() -> list[str]:
    """
    Returns the ordered list of models to try: strongest first, then fallbacks.
    Deduplicates so we don't retry the same model twice.
    """
    seen = set()
    cascade = []
    for model in [GEMINI_MODEL_PRIMARY, GEMINI_MODEL_FAST, GEMINI_MODEL_FALLBACK]:
        if model not in seen:
            cascade.append(model)
            seen.add(model)
    return cascade


# Startup diagnostic
print("=" * 50)
print("RepoIntel Config Loaded")
print(f"  Primary model:  {GEMINI_MODEL_PRIMARY}")
print(f"  Fast model:     {GEMINI_MODEL_FAST}")
print(f"  Fallback model: {GEMINI_MODEL_FALLBACK}")
print(f"  Model cascade:  {' → '.join(get_model_cascade())}")
print(f"  Fast helper:    {'enabled' if ENABLE_FAST_HELPER else 'disabled'}")
print("=" * 50)
