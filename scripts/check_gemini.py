"""
RepoIntel Gemini Model Diagnostic
Tests which model IDs actually work with the current API key.
Usage: python scripts/check_gemini.py
"""
import os
import sys
import time

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent.parent / ".env")


def main():
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("[FAIL] No GEMINI_API_KEY or GOOGLE_API_KEY found in .env")
        sys.exit(1)

    print(f"[OK] API key loaded (length={len(api_key)})")
    print()

    # Test 1: SDK import
    try:
        from google import genai
        from google.genai import types
        print(f"[OK] google-genai SDK imported (version: {genai.__version__ if hasattr(genai, '__version__') else 'unknown'})")
    except ImportError as e:
        print(f"[FAIL] Cannot import google-genai: {e}")
        sys.exit(1)

    client = genai.Client(api_key=api_key)

    # Candidate models to test — ordered by likely availability
    candidates = [
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        "gemini-2.5-pro",
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
        "gemini-3.5-flash",
        "gemini-3.1-flash-lite",
        "gemini-3-flash",
    ]

    print()
    print("=" * 60)
    print("PLAIN TEXT GENERATION TESTS")
    print("=" * 60)

    working_models = []

    for model_id in candidates:
        try:
            start = time.time()
            response = client.models.generate_content(
                model=model_id,
                contents="Reply with exactly: PING_OK",
                config=types.GenerateContentConfig(
                    temperature=0,
                    max_output_tokens=32,
                ),
            )
            elapsed = int((time.time() - start) * 1000)
            text = (response.text or "").strip()
            print(f"[OK]   {model_id:30s}  {elapsed:5d}ms  response='{text[:50]}'")
            working_models.append(model_id)
        except Exception as e:
            err = str(e)[:100]
            print(f"[FAIL] {model_id:30s}  {err}")

    print()
    print("=" * 60)
    print("STRUCTURED OUTPUT TEST (minimal schema)")
    print("=" * 60)

    if not working_models:
        print("[SKIP] No working models found, cannot test structured output.")
        return

    # Use the first working model for structured test
    test_model = working_models[0]

    # Minimal schema — no dict fields, no additionalProperties
    from pydantic import BaseModel

    class TestResponse(BaseModel):
        status: str
        summary: str

    try:
        start = time.time()
        response = client.models.generate_content(
            model=test_model,
            contents="Analyze this text: 'Hello World'. Return status and summary.",
            config=types.GenerateContentConfig(
                temperature=0,
                max_output_tokens=256,
                response_mime_type="application/json",
                response_schema=TestResponse,
            ),
        )
        elapsed = int((time.time() - start) * 1000)
        print(f"[OK]   Structured output with {test_model}  {elapsed}ms")
        print(f"       Response: {response.text[:200]}")

        # Try to parse
        import json
        parsed = json.loads(response.text)
        validated = TestResponse(**parsed)
        print(f"       Parsed:   status={validated.status}, summary={validated.summary[:80]}")
    except Exception as e:
        print(f"[FAIL] Structured output with {test_model}: {e}")

    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Working models: {working_models}")
    if len(working_models) >= 2:
        print(f"  Recommended primary: {working_models[0]}")
        print(f"  Recommended fast:    {working_models[1]}")
        print(f"  Recommended fallback: {working_models[-1]}")
    elif len(working_models) == 1:
        print(f"  Single model mode: {working_models[0]}")
    print()
    print("Set these in your .env:")
    if len(working_models) >= 2:
        print(f"  GEMINI_MODEL_PRIMARY={working_models[0]}")
        print(f"  GEMINI_MODEL_FAST={working_models[1]}")
        print(f"  GEMINI_MODEL_FALLBACK={working_models[-1]}")
    elif len(working_models) == 1:
        print(f"  GEMINI_MODEL_PRIMARY={working_models[0]}")
        print(f"  GEMINI_MODEL_FAST={working_models[0]}")
        print(f"  GEMINI_MODEL_FALLBACK={working_models[0]}")


if __name__ == "__main__":
    main()
