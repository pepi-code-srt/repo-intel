# RepoIntel: Interview Guide

This guide contains likely interview questions about the **RepoIntel** project and concise, defensible answers based strictly on the actual codebase.

## System Design & Architecture

**1. Why did you choose a multi-agent architecture (LangGraph) instead of a single LLM prompt?**
*Answer:* I chose decomposition into specialized stages to separate repository scanning, analysis, and report generation while keeping state explicit. Passing an entire repository structure to an LLM context window in a single prompt is difficult to structure and manage; breaking it into a Supervisor, Scanner, Analyzer, and Generator allowed me to pass structured state between narrow, specialized functions.

**2. How do you handle real-time updates to the frontend during analysis?**
*Answer:* I used FastAPI WebSockets (`/api/ws/{job_id}`). As the LangGraph `astream` yields state updates for each node (e.g., when `repo_scanner` finishes), the backend pushes a JSON event over the active WebSocket, updating the UI dynamically.

**3. If 100 users scan repos concurrently, how do you prevent server storage from filling up with cloned repos?**
*Answer:* I implemented an ephemeral storage pattern. Every analysis runs in a `try/finally` block where the `cloned_path` is aggressively deleted via `shutil.rmtree`. Additionally, I attached a FastAPI lifespan hook that hunts for and deletes any orphaned `/tmp/repo-intel-*` directories on server startup and shutdown to catch catastrophic crashes. I verified this in an isolated test where 2/2 mock directories were successfully purged.

## API Resilience & Reliability

**4. How does your system handle Google Gemini API rate limits (HTTP 429 Too Many Requests)?**
*Answer:* I built a custom `invoke_llm_with_retry` wrapper. When a 429 is caught, it triggers an Exponential Backoff strategy. If the key is permanently exhausted or hits a non-retriable error like a 403, it rotates to a secondary fallback key loaded from the `.env` file. I verified this behavior locally using a mocked unit test.

**5. What happens if all your API keys fail or the LLM provider goes down entirely?**
*Answer:* I implemented a Zero-Token Deterministic Fallback. If the Analyzer agent fails completely, it catches the exception, avoids crashing the supervisor, and populates the state with the raw structural metrics (file count, dependencies) gathered by the Scanner. The Report Generator then mathematically formats a Markdown report using this data, costing 0 API tokens while still providing value to the user.

**6. How do you optimize LLM payload usage when scanning codebases?**
*Answer:* I built a Payload Minification pre-processor (`minify_content`). Before sending raw files like Dockerfiles or source code to the LLM, this function strips consecutive blank lines and trailing whitespaces. In a synthetic code sample test, it reduced the character count from 86 to 53 (a 38.37% payload reduction).

## State Management & Edge Cases

**7. How did you prevent your LangGraph state machine from getting stuck in an infinite loop?**
*Answer:* Initially, if a repository failed to clone, the scanner returned empty data, and the supervisor repeatedly tasked it to try again. I solved this by injecting a sentinel error marker into the state (`{"_error": "failed"}`). The supervisor was updated to deterministically route straight to the Report Generator if this flag is detected. As a hard safety net, I also applied a `recursion_limit=30` to the graph invocation.

**8. How do you ensure the frontend doesn't hang if the WebSocket disconnects?**
*Answer:* The frontend establishes the WebSocket, but if it disconnects, it gracefully degrades to HTTP polling against the `/api/report/{job_id}` REST endpoint to fetch the final report.

## Testing & Benchmarks

**9. How did you benchmark the performance of this multi-agent system?**
*Answer:* I wrote a dedicated E2E testing script using `subprocess` and `websockets` to spin up the FastAPI server, trigger the analysis against public repos like `pallets/click`, and measure total duration by tracking the WebSocket lifecycle. In deterministic fallback mode, a local test completed in roughly 8 seconds.

**10. What is the most challenging bug you fixed in this project?**
*Answer:* (Choose one of the above: The LangGraph infinite loop OR the API Rate limit crashing the server) -> Walk through the problem, how you debugged it, and the specific Python/FastAPI solution you implemented.
