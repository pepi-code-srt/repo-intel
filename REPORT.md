# RepoIntel: Architecture & Incident Resolution Report

This document serves as a comprehensive post-mortem and architectural summary for **RepoIntel**. It details the core problems encountered during development, the root causes, and the engineering solutions implemented to resolve them. It is designed to explain the "Why" and "How" behind the system to stakeholders or technical interviewers.

---

## Executive Summary: What it is & How it works

**What is RepoIntel?**
RepoIntel is an AI-powered GitHub repository analysis tool. You give it a GitHub link, and it acts like an automated Staff Engineer—it downloads the code, reads the structure, evaluates the code quality, checks for security risks, and generates a professional markdown report detailing what the repository does and how to improve it.

**How does it work? (Simple Points)**
1. **The User Interface:** The user enters a GitHub URL into a modern, dark-themed web dashboard.
2. **The Scanner Agent:** The backend temporarily downloads (clones) the code, fetches metadata (like stars and languages), and packages the code into small, optimized chunks.
3. **The Brain (Supervisor):** A LangGraph "Supervisor" manages the workflow. It decides which agent should look at the code next.
4. **The Analyzer Agent:** An AI agent (powered by Gemini) reads the code chunks and grades the repository on three categories: Code Quality, Security, and DevOps Readiness.
5. **The Report Generator:** A final agent compiles all the grades, stats, and AI findings into a beautiful, easy-to-read Markdown report.
6. **The Cleanup:** The temporary code is immediately deleted from the server to save disk space, and the final report is streamed live to the user's screen.

---

## 1. Dependency Resolution & Checkpoint Conflicts

### **The Problem**
During the initial startup phase, the FastAPI server crashed with a fatal exception:
`TypeError: Reviver.__init__() got an unexpected keyword argument 'allowed_objects'`

Additionally, `pip` reported severe version conflicts between `google-genai`, `langchain-core`, and `langgraph-checkpoint`.

### **The Cause**
The ecosystem around LangGraph and LangChain is rapidly evolving. We were using mismatched versions of `langchain-core` (0.2.1) and newer `langgraph-checkpoint` packages that introduced new serialization arguments (`allowed_objects`) which older core packages didn't support.

### **The Solution**
- Performed a surgical dependency upgrade, carefully unpinning heavily restricted versions to allow `pip` to resolve a mutually compatible dependency tree.
- Standardized on **LangGraph 1.2.8** and updated the LangChain core libraries to ensure the state serializers (JSONPlus) functioned correctly.

---

## 2. The Infinite Loop (LangGraph Recursion Error)

### **The Problem**
When a user submitted an invalid GitHub URL (or a private repository), the application would hang, burn resources, and eventually crash with a `RecursionError` or timeout.

### **The Cause**
The LangGraph workflow was built as a state machine. When the `repo_scanner` agent failed to clone a repository, it returned an empty state. The `supervisor` agent, seeing no findings, would command the `repo_scanner` to try again. This created a runaway infinite loop. Furthermore, the `recursion_limit` parameter was placed in `workflow.compile()`, which was an invalid argument in our LangGraph version, leaving no safety net.

### **The Solution**
- **State Markers:** Updated the `repo_scanner` to explicitly return a sentinel error marker `{"_error": "Failed to clone..."}` if the `git clone` operation failed.
- **Deterministic Routing:** Modified the `supervisor.py` router logic. If it detects the `_error` key, it instantly breaks the loop and routes the state directly to the `report_generator`.
- **Safety Nets:** Moved the recursion safety guard to the invocation level (`graph.astream(..., config={"recursion_limit": 30})`), ensuring the loop can never exceed 30 iterations even in catastrophic edge cases.

---

## 3. Gemini API Rate Limits & Token Optimization

### **The Problem**
Because we were using the Gemini Free Tier (which strictly limits requests to 20 per day), our agents were constantly hitting `429 Too Many Requests (RESOURCE_EXHAUSTED)` errors. A single analysis requires multiple LLM calls, meaning we were burning through our quota in just 3-4 repo scans. 

### **The Cause**
The default Google GenAI client handles standard network retries, but when it hits a hard Quota Exceeded error, it immediately throws an exception. Furthermore, we were sending massive, unoptimized file payloads (like raw Dockerfiles and source code) to the LLM.

### **The Solution**
- **Custom LLM Manager (`src/utils/llm_manager.py`):** Intercepted all LLM calls with a custom wrapper.
- **API Key Rotation:** Updated `config.py` to scan `.env` for *multiple* fallback keys (`GOOGLE_API_KEY`, `GEMINI_API_KEY1`, etc.). If the primary key is exhausted, the manager gracefully hands over to the next key without failing the user's request.
- **Exponential Backoff:** Added an intelligent pause-and-retry mechanism. Instead of spamming the API when rate-limited, the system waits 2 seconds, then 4, then 8, allowing short-term token buckets to replenish.
- **Token Minification (Zero-Loss):** Implemented a `_minify` function in the `engineering_analyzer` that aggressively strips consecutive blank lines and trailing whitespaces from source files before sending them to Gemini. This reduced payload sizes (and token usage) by ~20% without losing a single line of semantic code.

---

## 4. Graceful Degradation & Zero-Token Fallbacks

### **The Problem**
If all API keys were exhausted (or GitHub's API went down), the system would dump a massive, unreadable raw JSON string to the frontend, resulting in a terrible user experience.

### **The Solution**
- **Intelligence Report System:** Rewrote the LLM prompt to focus strictly on what is *missing*, critical risks, and actionable fixes, turning the output into a true Staff Engineer report rather than a generic README clone.
- **Deterministic Fallback Generation:** Modified `report_generator.py` so that if the LLM completely fails, Python takes the structured data gathered by the earlier agents and manually formats a beautiful Markdown report (with tables, health badges, and score calculation). This provides the user with 90% of the value using **0 API tokens**.

---

## 5. Storage Bloat & Disk Management

### **The Problem**
The application clones repositories to the local disk (`/tmp`) to analyze them. If the server crashed or the analysis failed, these repositories were left behind, causing massive disk bloat over time.

### **The Solution**
- **Immediate Cleanup:** Wrapped the WebSocket stream runner in `routes.py` in a `finally` block to guarantee the `shutil.rmtree` cleanup executes immediately after the analysis ends (success or fail).
- **Lifespan Hooks:** Added an `asynccontextmanager` hook in FastAPI's `main.py` that triggers on server shutdown (`Ctrl+C`), actively hunting down and deleting any orphaned `repo-intel-` temp directories.

---

## 6. Frontend Redesign

### **The Problem**
The initial UI was functional but felt generic, and it poorly handled WebSocket disconnections.

### **The Solution**
- Implemented a sleek, pure black (`#000`) modern aesthetic.
- Added client-side polling logic so that if the WebSocket disconnects unexpectedly, the frontend gracefully falls back to a REST API (`/api/report/{job_id}`) to fetch the final report.
- Added live agent streaming (🧠 Supervisor, 📂 Scanner, 🔬 Analyzer, 📝 Generator) to keep the user engaged during processing latency.

---

## 7. Interview Q&A Guide (How to explain this project)

If you are presenting this project in a technical interview, expect interviewers to drill into the **System Design**, **Resilience**, and **Optimization** aspects. Here is how they will ask and how you should reply.

### ❓ Q1: "How did you handle the LLM API rate limits? What happens if the API goes down?"
**How they might ask it:** *"I see you're using Gemini. LLMs are notoriously slow and rate-limited. How does your system behave under load or when you hit a 429 Too Many Requests error?"*

**How to Reply:**
> "I built a resilient LLM wrapper (`llm_manager.py`) to handle this. When the system hits a `429 Quota Exceeded` error, it doesn't crash. Instead, it implements **Exponential Backoff**—pausing briefly, then retrying with double the wait time.
> 
> Furthermore, it implements **API Key Rotation**. If the primary key is completely exhausted, it catches the exception and seamlessly rotates to a fallback key stored in the `.env` file to continue the analysis.
> 
> Finally, I designed a **Deterministic Fallback**. If the API is completely down and all keys fail, the system doesn't return a 500 error. The Report Generator agent bypasses the LLM and mathematically calculates health scores using the structured JSON data gathered by earlier agents, returning a fully formatted Markdown report using zero API tokens."

### ❓ Q2: "Can you explain how you prevent infinite loops in your LangGraph state machine?"
**How they might ask it:** *"You're using LangGraph. State machines can easily get trapped in cycles if an agent fails. How do you prevent runaway executions?"*

**How to Reply:**
> "Initially, we did face an issue where if a repository failed to clone, the scanner returned empty data, and the supervisor kept asking the scanner to retry indefinitely. 
> 
> I resolved this by implementing **Sentinel Error Markers**. If the clone fails, the `repo_scanner` agent mutates the state with `{"_error": "failed to clone"}`. 
> 
> I then updated the Supervisor's routing logic to become deterministic: if it sees the `_error` flag, it instantly breaks the cycle and routes directly to the `report_generator`. Additionally, as a hard safety net, I implemented a strict `recursion_limit=30` at the invocation level (`astream`) to guarantee the process is killed before it can exhaust server resources."

### ❓ Q3: "How did you optimize the LLM payload? Aren't you blowing past token limits by sending entire codebases?"
**How they might ask it:** *"Sending a repository to an LLM sounds expensive. How do you manage the context window and token usage?"*

**How to Reply:**
> "I implemented aggressive **Token Minification**. Before any file (like a Dockerfile, `docker-compose.yml`, or source code) is sent to the LLM, it passes through a `_minify` pre-processor. 
> 
> This function strips out consecutive blank lines and excessive trailing whitespaces. Because LLMs tokenize whitespace, this simple step reduced our payload sizes by roughly 20%. We save thousands of tokens per run, drastically reducing the chances of hitting rate limits, all without losing a single line of semantic code logic."

### ❓ Q4: "How does your system manage disk space? If you're cloning repos, doesn't the server disk fill up?"
**How they might ask it:** *"If 100 users scan repos, you're downloading 100 codebases to the server. How do you manage storage bloat?"*

**How to Reply:**
> "I designed the system to be ephemeral. The `routes.py` execution block uses a `finally` clause. No matter what happens—whether the analysis succeeds, fails, or crashes—the temporary cloned directory is immediately deleted using `shutil.rmtree`.
> 
> To handle edge cases like the server suddenly crashing or being stopped via `Ctrl+C`, I implemented a FastAPI `lifespan` context manager. On startup and shutdown, the server actively hunts for orphaned `repo-intel-` temp directories in the OS `/tmp` folder and purges them. The disk footprint always returns to zero."
