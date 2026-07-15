import os
import sys
import tempfile
import json
import uuid
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.utils.text_utils import minify_content
from src.utils.llm_manager import invoke_llm_with_retry
from src.main import cleanup_all_temp_repos
from src.agents.engineering_analyzer import engineering_analyzer_agent

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
    return {
        "raw_length": len(raw_code),
        "minified_length": len(minified),
        "reduction_percent": round(reduction, 2)
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

def test_api_key_rotation():
    print("\nTesting API Key Rotation (Mocked)...")
    import src.utils.llm_manager as llm_manager
    original_keys = list(llm_manager.AVAILABLE_API_KEYS)
    llm_manager.AVAILABLE_API_KEYS = ["KEY_1", "KEY_2", "KEY_3"]
    
    mock_llm_instance = MagicMock()
    # First key receives simulated 429/rate-limit failure
    # Second key receives simulated 429/rate-limit failure
    # Third key succeeds
    mock_llm_instance.invoke.side_effect = [
        Exception("429 Too Many Requests"), 
        Exception("429 Too Many Requests"),
        "Success_Response"
    ]
    
    with patch("src.utils.llm_manager.ChatGoogleGenerativeAI", return_value=mock_llm_instance):
        with patch("time.sleep"): # avoid actual sleeping
            result = invoke_llm_with_retry("test prompt", max_retries_per_key=1)
        
    print(f"  Result: {result}")
    success = (result == "Success_Response")
    print(f"  Rotation success: {success}")
    
    llm_manager.AVAILABLE_API_KEYS = original_keys
    return {"success": success}

def test_exponential_backoff():
    print("\nTesting Exponential Backoff Timing (Mocked)...")
    import src.utils.llm_manager as llm_manager
    original_keys = list(llm_manager.AVAILABLE_API_KEYS)
    llm_manager.AVAILABLE_API_KEYS = ["ONLY_KEY"]
    
    mock_llm_instance = MagicMock()
    # Trigger 429 three times
    mock_llm_instance.invoke.side_effect = [
        Exception("429 Too Many Requests"),
        Exception("429 Too Many Requests"),
        Exception("429 Too Many Requests"),
        "Success"
    ]
    
    sleep_calls = []
    def mock_sleep(seconds):
        sleep_calls.append(seconds)
        
    with patch("src.utils.llm_manager.ChatGoogleGenerativeAI", return_value=mock_llm_instance):
        with patch("time.sleep", side_effect=mock_sleep):
            try:
                invoke_llm_with_retry("test", max_retries_per_key=3, backoff_factor=2)
            except Exception:
                pass # Expected if it exhausts all 3 retries without hitting 'Success'
                
    print(f"  Observed sleep sequence: {sleep_calls}")
    success = (sleep_calls == [2, 4, 8])
    print(f"  Backoff success: {success}")
    
    llm_manager.AVAILABLE_API_KEYS = original_keys
    return {"success": success, "sleep_sequence": sleep_calls}

def test_all_keys_exhausted():
    print("\nTesting All Keys Exhausted (Mocked)...")
    import src.utils.llm_manager as llm_manager
    original_keys = list(llm_manager.AVAILABLE_API_KEYS)
    llm_manager.AVAILABLE_API_KEYS = ["KEY_1", "KEY_2"]
    
    mock_llm_instance = MagicMock()
    # All fail with non-retriable error
    mock_llm_instance.invoke.side_effect = Exception("403 Forbidden")
    
    success = False
    with patch("src.utils.llm_manager.ChatGoogleGenerativeAI", return_value=mock_llm_instance):
        try:
            invoke_llm_with_retry("test", max_retries_per_key=1)
        except Exception as e:
            if "403" in str(e):
                success = True
                
    print(f"  Exhaustion exception properly raised: {success}")
    llm_manager.AVAILABLE_API_KEYS = original_keys
    return {"success": success}

def test_deterministic_fallback():
    print("\nTesting Deterministic Fallback in Workflow...")
    # Create fake state
    state = {
        "repo_statistics": {"files": 10},
        "repo_health": {"has_docker": False},
        "repo_structure": {"src": {}},
        "agent_findings": {}
    }
    
    # Mock LLM to throw Exhausted
    def mock_invoke(*args, **kwargs):
        raise Exception("RESOURCE_EXHAUSTED 429 Too Many Requests")
        
    with patch("src.agents.engineering_analyzer.invoke_llm_with_retry", side_effect=mock_invoke):
        result_state = engineering_analyzer_agent(state)
        
    findings = result_state["agent_findings"]["code_quality"]
    print(f"  Fallback status: {findings.get('status')}")
    success = (findings.get('status') == "QuotaExceeded" and findings.get('score') is None)
    print(f"  Fallback success: {success}")
    
    return {"success": success, "status": findings.get('status')}

if __name__ == "__main__":
    results = {}
    try:
        results["minification"] = test_token_minification()
        results["cleanup"] = test_temp_dir_cleanup()
        results["api_rotation"] = test_api_key_rotation()
        results["exponential_backoff"] = test_exponential_backoff()
        results["all_keys_exhausted"] = test_all_keys_exhausted()
        results["deterministic_fallback"] = test_deterministic_fallback()
    except Exception as e:
        print(f"Test script failed: {e}")
        
    # Save results to RAW evidence
    raw_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../evidence/raw'))
    os.makedirs(raw_dir, exist_ok=True)
    with open(os.path.join(raw_dir, "resilience_raw_results.json"), "w") as f:
        json.dump(results, f, indent=2)
        
    # We can still save a summary
    processed_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../evidence/processed'))
    os.makedirs(processed_dir, exist_ok=True)
    with open(os.path.join(processed_dir, "resilience_summary.json"), "w") as f:
        json.dump({k: v.get("success", True) if "success" in v else v for k, v in results.items()}, f, indent=2)
        
    print("\nResilience tests complete. Results saved.")
