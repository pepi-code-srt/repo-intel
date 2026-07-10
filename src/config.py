from dotenv import load_dotenv
from pathlib import Path
import os

# Use absolute path to .env to avoid CWD issues
load_dotenv(Path(__file__).parent.parent / ".env")

# Collect all possible API keys for rotation
AVAILABLE_API_KEYS = []
for key in ["GOOGLE_API_KEY", "GEMINI_API_KEY", "GEMINI_API_KEY1", "GEMINI_API_KEY2"]:
    val = os.getenv(key)
    if val and val not in AVAILABLE_API_KEYS:
        AVAILABLE_API_KEYS.append(val)

MODEL_NAME = os.getenv("MODEL_NAME", "gemini-2.5-flash")

if not AVAILABLE_API_KEYS:
    raise RuntimeError(
        "No API keys found. "
        "Add GOOGLE_API_KEY or GEMINI_API_KEY to your .env file."
    )

# Primary key for fallback usage where rotation isn't easily supported
GOOGLE_API_KEY = AVAILABLE_API_KEYS[0]

# Startup diagnostic
print("=" * 40)
print("RepoIntel Config Loaded")
print(f"  API Keys Loaded: {len(AVAILABLE_API_KEYS)}")
print(f"  Primary Key prefix: {GOOGLE_API_KEY[:8]}...")
print(f"  Model: {MODEL_NAME}")
print("=" * 40)
