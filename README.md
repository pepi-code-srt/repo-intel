# RepoIntel

An AI-Powered GitHub Repository Analysis Agent built with **LangGraph**, **Model Context Protocol (MCP)**, and **FastAPI** that acts as an automated Staff Engineer.

## Overview
RepoIntel solves the problem of manual codebase onboarding and security auditing. Aimed at Developers, Tech Leads, and Security Engineers, it temporarily clones a public GitHub repository, analyzes its structure, assesses code quality and security, and generates a structured Markdown report.

## Key Features
- **Multi-Agent Orchestration**: Uses LangGraph to route tasks between a Scanner, Analyzer, and Report Generator.
- **Resilient AI Pipeline**: Features exponential backoff, API key rotation, and zero-token deterministic fallbacks for handling strict LLM rate limits.
- **Resource Management**: Uses payload minification to reduce payload size and FastAPI lifespan hooks to aggressively clean up temporary cloned repositories.
- **Real-Time Streaming**: Uses WebSockets to stream agent progress back to a sleek, dark-themed frontend.

## Architecture

```mermaid
graph TD
    User([User URL Input]) --> WS[FastAPI WebSocket]
    WS --> Supervisor[LangGraph Supervisor]
    
    Supervisor --> Scanner[Repo Scanner Agent]
    Scanner --> |git clone, parse structure| Supervisor
    
    Supervisor --> Analyzer[Engineering Analyzer]
    Analyzer --> |LLM context minification| Gemini[Google Gemini API]
    Analyzer --> |Error: 429| Fallback[Zero-Token Fallback]
    Fallback --> Supervisor
    Gemini --> Supervisor
    
    Supervisor --> Generator[Report Generator]
    Generator --> |Markdown synthesis| Supervisor
    
    Supervisor --> Cleanup[shutil.rmtree /tmp/repo-intel-*]
    Cleanup --> Final[Final Report Delivered]
```

## Tech Stack
- **AI Orchestration**: LangGraph, LangChain
- **Tooling**: FastMCP
- **LLM**: Google Gemini API (`gemini-2.5-flash`)
- **Backend**: FastAPI, WebSockets
- **Frontend**: HTML5, CSS3, Vanilla JS

## Getting Started

1. Clone the repository and navigate to it:
   ```bash
   git clone https://github.com/pepi-code-srt/repo-intel.git
   cd repo-intel
   ```

2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   # On Windows:
   .\venv\Scripts\activate
   # On Mac/Linux:
   source venv/bin/activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Set up your environment variables:
   ```bash
   cp .env.example .env
   ```
   *Edit `.env` and add your Google Gemini API key.*

5. Run the server:
   ```bash
   uvicorn src.main:app --reload
   ```

6. Open your browser to `http://localhost:8000` and paste a GitHub URL!

## Evaluation / Benchmarks

We have conducted strict resilience and benchmark testing. All testing scripts are available in `scripts/` and full results are in `evidence/reports/BENCHMARK_REPORT.md`.

* **End-to-End Analysis**: During a local Windows 11 test on 2026-07-15, two public repositories completed the end-to-end workflow in deterministic fallback mode. Observed wall-clock durations were 7.56s and 8.13s, with 7 WebSocket events captured for each run.
* **Payload Minification**: In one synthetic whitespace-heavy code sample, the production minifier automatically stripped semantic whitespace resulting in a **38.37% payload character reduction** before sending to the LLM.
* **Graceful Degradation**: If the API key is exhausted or invalid, the system automatically falls back to a deterministic 0-token report generator, successfully streaming the completion event without crashing. (Verified via isolated mock tests and E2E runs).

## Limitations
- **Public Repositories Only**: Currently relies on unauthenticated `git clone`, so it cannot analyze private repositories.
- **Large Repositories**: Large monorepos may still hit context limits if they contain too many massive files.

## Future Improvements
- Integrate GitHub OAuth for private repository scanning.
- Replace in-memory `jobs` dictionary with Redis for horizontal scalability.
