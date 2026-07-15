# RepoIntel: Engineering Case Study

## Problem
Onboarding onto new codebases or evaluating open-source repositories for security and architectural quality is historically a slow, manual process. Developers must pull the code, read through undocumented structures, manually check for secrets or monolithic patterns, and assess DevOps maturity. We needed a way to automate this "Staff Engineer" review process using AI.

## Constraints
- **Strict API Rate Limits**: Relying on the free tier of the Google Gemini API meant facing aggressive `429 Too Many Requests` limits.
- **Context Management**: Passing an entire repository to an LLM context window in a single prompt is difficult to structure and manage.
- **Storage Constraints**: Cloning dozens of repositories concurrently onto a single server would quickly cause storage bloat and disk exhaustion.
- **State Traps**: Multi-agent orchestration systems (like LangGraph) can easily fall into infinite loops if an agent fails to return expected state.

## Architecture
RepoIntel uses a **Supervisor-Worker Agent Architecture** powered by LangGraph. I chose decomposition into specialized stages to separate repository scanning, analysis, and report generation while keeping state explicit. The system streams progress via **WebSockets** and utilizes **FastAPI** for backend orchestration.

## Important Engineering Decisions
1. **Zero-Token Deterministic Fallbacks**: Rather than crashing when the LLM API is unavailable or exhausted, the system catches the failure and generates a fully formatted report based strictly on the heuristic data gathered by the `repo_scanner` agent, using 0 tokens.
2. **Payload Minification**: Implemented a pre-processor (`minify_content`) that strips consecutive blank lines and trailing whitespaces from source files before LLM ingestion, heavily reducing payload characters without losing semantic meaning.
3. **Ephemeral Storage Pattern**: Used FastAPI lifespan context managers and strict `finally` blocks to ensure temporary `git clone` directories are purged immediately after analysis or upon unexpected server shutdown.

## Challenges Encountered & Solved
**The Infinite Loop Exception**
When a repository failed to clone, the LangGraph supervisor repeatedly tasked the scanner to try again, leading to `RecursionError` and server lockups.
*Solution*: Implemented sentinel error markers. If the scanner fails, it mutates the state with `{"_error": ...}`. The supervisor's routing logic was updated to instantly break the loop upon detecting this flag, and a hard `recursion_limit=30` was applied to the graph stream.

**Rate Limiting**
Agents were crashing mid-analysis when hitting Google's rate limits.
*Solution*: Built a custom `llm_manager.py` that intercepts all LLM calls, implementing **API Key Rotation** and **Exponential Backoff**.

## Testing Methodology
I created a custom testing suite (`scripts/run_benchmarks.py` and `scripts/test_resilience.py`) that utilizes `subprocess` and `websockets` to perform true End-to-End integration tests against public GitHub repositories and isolated mocked tests for API resilience.

## Verified Results
- **Resilience**: In one synthetic whitespace-heavy code sample, the production minifier reduced character count from 86 to 53 (38.37%). 2/2 test-created Repo-Intel temporary directories were successfully removed.
- **Performance**: During a local Windows 11 test on 2026-07-15, two public repositories completed the end-to-end workflow in deterministic fallback mode. Observed wall-clock durations were 7.48s and 10.27s.

## Limitations
- The system currently only supports public repositories via unauthenticated `git clone`.
- Large monorepos may still hit context limits if they contain too many massive files.

## What I Would Improve Next
- Implement GitHub OAuth to pass user credentials for scanning private repositories.
- Replace the in-memory `jobs` state tracker with Redis to support horizontally scaling the FastAPI instances.
