# RepoIntel

An AI-Powered GitHub Repository Analysis Agent built with **LangGraph**, **Model Context Protocol (MCP)**, and **FastAPI**.

## Architecture

RepoIntel uses a **Supervisor-Worker** multi-agent architecture:
1. **Supervisor Agent (Router)**: Determines the sequence of execution.
2. **Worker Agents**:
   - `Repo Scanner`: Clones repo and maps file structure.
   - `Code Quality`: Analyzes architectural patterns and best practices.
   - `Security Analyzer`: Scans for common vulnerabilities.
   - `Report Generator`: Synthesizes findings into a professional markdown report.
3. **MCP Server**: Provides standardized tools for the agents to interact with the file system and GitHub API securely.

## Tech Stack
- **AI Orchestration**: LangGraph, LangChain
- **Tool Protocol**: FastMCP
- **LLM**: Gemini API
- **Backend**: FastAPI, WebSockets (for real-time agent streaming)
- **Frontend**: HTML5, CSS3, Vanilla JS

## Quickstart

1. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: .\venv\Scripts\activate
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Set up your `.env` file:
   ```bash
   cp .env.example .env
   # Add your GEMINI_API_KEY
   ```

4. Run the server:
   ```bash
   uvicorn src.main:app --reload
   ```

5. Open your browser to `http://localhost:8000` and paste a GitHub URL!
