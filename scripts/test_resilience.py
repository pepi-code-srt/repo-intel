import os
import sys
import tempfile
import json
import uuid
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.utils.text_utils import minify_content
from src.api.routes import cleanup_all_temp_repos
from src.agents.engineering_analyzer import engineering_analyzer_agent
from src.providers.gemini_provider import ProviderError, GeminiProvider

def test_token_minification():
    print("Testing Character Minification...")
    raw_code = """
def my_function():


    print("Hello")

    return True


"""
    minified = minify_content(raw_code)
    reduction = (1 - (len(minified) / len(raw_code))) * 100
    print(f"  Raw length: {len(raw_code)} chars")
    print(f"  Minified length: {len(minified)} chars")
    print(f"  Reduction: {reduction:.2f}%")
    success = (len(minified) < len(raw_code)) and (len(minified) > 0) and ("print" in minified)
    return {
        "raw_length": len(raw_code),
        "minified_length": len(minified),
        "reduction_percent": round(reduction, 2),
        "success": success
    }

def test_temp_dir_cleanup():
    print("\nTesting Temporary Directory Cleanup...")
    temp_dir = tempfile.gettempdir()
    fake_dirs = [
        os.path.join(temp_dir, f"repo-intel-{uuid.uuid4()}"),
        os.path.join(temp_dir, f"repo-intel-{uuid.uuid4()}")
    ]
    created_count = 0
    for d in fake_dirs:
        os.makedirs(d, exist_ok=True)
        created_count += 1

    cleanup_all_temp_repos()

    remaining_count = 0
    for d in fake_dirs:
        if os.path.exists(d):
            remaining_count += 1

    removed_count = created_count - remaining_count
    print(f"  Created {created_count} test directories.")
    print(f"  Removed {removed_count} test directories.")

    return {
        "created": created_count,
        "removed": removed_count,
        "remaining": remaining_count,
        "success": removed_count == created_count
    }

def test_fail_fast_auth():
    print("\nTesting Fail Fast on Auth/Model Error (Mocked)...")
    
    mock_client = MagicMock()
    mock_model = MagicMock()

    class FakeAPIError(Exception):
        def __init__(self, message, code, status):
            super().__init__(message)
            self.code = code
            self.status = status
            self.message = message

    error = FakeAPIError("403 Forbidden", 403, "PERMISSION_DENIED")
    mock_model.generate_content.side_effect = error
    mock_client.models = mock_model

    success = False
    with patch("src.providers.gemini_provider.genai.Client", return_value=mock_client):
        # Patch APIError inside gemini_provider
        with patch("src.providers.gemini_provider.APIError", FakeAPIError):
            provider = GeminiProvider("fake_key")
            try:
                provider.generate_text("prompt", ["model-1", "model-2"], "task", "role")
            except ProviderError as e:
                if e.category == "auth_error":
                    success = True

    print(f"  Fail-fast exception properly raised: {success}")
    return {"success": success}

def test_model_cascade():
    print("\nTesting Model Cascade on Rate Limit (Mocked)...")
    
    mock_client = MagicMock()
    mock_model = MagicMock()

    class FakeAPIError(Exception):
        def __init__(self, message, code, status):
            super().__init__(message)
            self.code = code
            self.status = status
            self.message = message

    # Trigger 429 for the first model, succeed for the second
    error429 = FakeAPIError("429 Too Many Requests", 429, "RESOURCE_EXHAUSTED")
    mock_model.generate_content.side_effect = [
        error429,
        MagicMock(text="Success")
    ]
    mock_client.models = mock_model

    with patch("src.providers.gemini_provider.genai.Client", return_value=mock_client):
        with patch("src.providers.gemini_provider.APIError", FakeAPIError):
            provider = GeminiProvider("fake_key")
            provider.BACKOFF_SECONDS = 0.01  # speed up test
            text, model_used = provider.generate_text(
                "prompt", ["model-1", "model-2"], "task", "role"
            )

    success = (model_used == "model-2")
    print(f"  Cascade to next model success: {success} (Used: {model_used})")

    return {"success": success, "model_used": model_used}

def test_deterministic_fallback():
    print("\nTesting Deterministic Fallback in Workflow...")
    # Create fake state
    state = {
        "repo_url": "test",
        "repo_metadata": {"full_name": "test"},
        "repo_path": "test",
        "repo_statistics": {"total_files": 10, "lines_of_code": 500},
        "repo_health": {"has_docker": False, "readme": False},
        "repo_structure": {"src": {}},
        "agent_findings": {},
        "source_samples": {}
    }

    # Mock GeminiProvider to throw ProviderError for all models
    def mock_init(*args, **kwargs):
        pass
        
    def mock_generate(*args, **kwargs):
        raise ProviderError("All models failed", category="rate_limit", user_message="Rate limit")

    with patch("src.agents.engineering_analyzer.GeminiProvider.__init__", mock_init):
        with patch("src.agents.engineering_analyzer.GeminiProvider.request_logs", []):
            with patch("src.agents.engineering_analyzer.GeminiProvider.generate_structured", mock_generate):
                with patch("src.agents.engineering_analyzer.ENABLE_FAST_HELPER", False):
                    result_state = engineering_analyzer_agent(state)

    findings = result_state["agent_findings"]["code_quality"]
    print(f"  Fallback status: {findings.get('status')}")
    success = (findings.get('status') == "Not scored (Structural Analysis)" and findings.get('score') is None)
    print(f"  Fallback success: {success}")

    return {"success": success, "status": findings.get('status')}

if __name__ == "__main__":
    results = {}
    has_failure = False
    try:
        results["minification"] = test_token_minification()
        results["cleanup"] = test_temp_dir_cleanup()
        results["fail_fast_auth"] = test_fail_fast_auth()
        results["model_cascade"] = test_model_cascade()
        results["deterministic_fallback"] = test_deterministic_fallback()
    except Exception as e:
        print(f"Test script failed with exception: {e}")
        has_failure = True

    # Check results for failures
    for k, v in results.items():
        if not v.get("success", False):
            print(f"Test {k} failed!")
            has_failure = True

    # Save results to RAW evidence
    raw_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../evidence/raw'))
    os.makedirs(raw_dir, exist_ok=True)
    with open(os.path.join(raw_dir, "resilience_raw_results.json"), "w") as f:
        json.dump(results, f, indent=2)

    # Save summary
    processed_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../evidence/processed'))
    os.makedirs(processed_dir, exist_ok=True)
    with open(os.path.join(processed_dir, "resilience_summary.json"), "w") as f:
        json.dump({k: v.get("success", False) for k, v in results.items()}, f, indent=2)

    print("\nResilience tests complete. Results saved.")

    if has_failure:
        print("One or more tests failed.")
        sys.exit(1)
    else:
        print("All tests passed successfully.")
        sys.exit(0)
