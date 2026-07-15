# RepoIntel Benchmark and Resilience Report

## Environment Details
- **Date**: 2026-07-15
- **OS**: Windows 11
- **Python Version**: 3.12.10
- **Testing Approach**: End-to-end FastAPI subprocess execution + WebSocket streaming

---

## 1. Resilience & Reliability Testing

All claims made in the architecture report were strictly tested using `scripts/test_resilience.py`.

### Payload/Character Minification
- **Test**: Passed raw Python code with excessive blank lines and trailing spaces through the exact production `minify_content` function.
- **Result**:
  - Raw length: 86 characters
  - Minified length: 53 characters
  - **Reduction**: 38.37%
- **Conclusion**: In one synthetic whitespace-heavy code sample, the production minifier reduced character count from 86 to 53 (38.37%).

### Temporary Directory Cleanup
- **Test**: Created fake temporary cloned directories mimicking LangGraph state, then invoked `cleanup_all_temp_repos()`.
- **Result**: 2/2 test-created Repo-Intel temporary directories were removed. No unrelated OS temporary directories were impacted.
- **Conclusion**: Ephemeral storage cleanup logic successfully purged the test samples.

### API Key Rotation, Backoff, and Deterministic Fallback
- **API Key Rotation**: Tested via mocking by simulating 429 failures before a subsequent configured-key attempt succeeded.
- **Exponential Backoff**: Tested via mocking. Verified the system successfully issues sleep commands of 2, 4, and 8 seconds before degrading.
- **Exhaustion**: Verified the system successfully catches and aborts if all keys return non-retriable 403 Forbidden errors.
- **Deterministic Fallback**: Simulated a 429 quota exhaustion inside the real LangGraph node (`engineering_analyzer_agent`). Verified that it produces a 0-token fallback state (`QuotaExceeded`) instead of crashing the orchestration graph.

---

## 2. Happy Path End-to-End Benchmarks

Tested the LangGraph orchestration end-to-end on two real public repositories. Because the `.env` contained a dummy API key, the system fell back to the Zero-Token Deterministic Fallback mode to still generate reports.

| Repository | Status | Events Streamed | Total Duration |
|------------|--------|-----------------|----------------|
| `octocat/Hello-World` | **SUCCESS** | 7 WebSocket events | 7.64s |
| `pallets/click` | **SUCCESS** | 7 WebSocket events | 9.19s |

**Findings**:
1. During a local Windows 11 test on 2026-07-15, two public repositories completed the end-to-end workflow in deterministic fallback mode.
2. Observed wall-clock durations were 7.64s and 9.19s, with 7 WebSocket events captured for each run.
