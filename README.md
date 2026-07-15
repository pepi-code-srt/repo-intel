# RepoIntel

AI-powered repository intelligence for public GitHub repositories.

RepoIntel clones and structurally analyzes a repository, selects the most relevant source evidence, and uses task-routed Gemini models to produce an evidence-based engineering review covering architecture, security, code quality, testing, and production readiness.

## What It Does

```text
GitHub Repository
    ↓
Deterministic Structural Scan
    ↓
Evidence Selection
    ↓
Fast Repository Classification
    ↓
Deep Engineering Review
    ↓
Validated Intelligence Report
```

## Current AI Pipeline

- **Structural analysis**: Deterministic Python (LangGraph workflow)
- **Fast classification**: Gemini 3.1 Flash Lite
- **Primary engineering review**: Gemini 3.5 Flash
- **Report rendering**: Deterministic Python
- **Failure mode**: Structural analysis fallback

The architecture uses **task-based model routing** rather than a supervisor loop, applying a strong, capable model (Gemini 3.5 Flash) only when deep semantic understanding is necessary, and utilizing a faster, more economical model (Gemini 3.1 Flash Lite) for simple classification tasks. An automatic **model cascade** is in place: if the primary model hits rate limits or is unavailable, requests failover seamlessly to a fallback model.

## Features

- **Evidence Selection**: Deterministically selects the most critical files (Dockerfiles, main APIs, config) to stay within budget constraints.
- **Model Cascade**: Fails gracefully if Gemini 3.5 Flash is busy, switching to Gemini 3.1 Flash Lite automatically.
- **Structural Fallback**: If all AI models are unavailable (e.g., API keys revoked or quota exhausted), RepoIntel still generates a structural report detailing file counts, languages, CI presence, and basic health metrics.
- **Real-Time Progress**: Powered by FastAPI and WebSockets, users receive real-time granular progress (including per-stage timing) in the frontend.
- **Safe Resource Limits**: Shallow cloning restricts the download depth of repositories, and temporary repositories are safely cleaned up automatically.

## Verified Run

RepoIntel successfully analyzed its own repository (V2 Runtime):

- 39 files scanned
- 2,595 lines of code
- 15 evidence files selected
- 31,354 evidence characters
- 2 successful AI calls
- Analysis mode: AI Enhanced
- Final engineering score: 6.3/10

## Quick Start

### 1. Requirements

- Python 3.12+
- Gemini API Key

### 2. Setup

```bash
python -m venv venv
# Windows
.\venv\Scripts\Activate.ps1
# Linux/Mac
source venv/bin/activate

pip install -r requirements.txt
```

### 3. Configuration

Create a `.env` file in the root directory:

```env
GEMINI_API_KEY=your_gemini_api_key_here
```

### 4. Run the Server

```bash
uvicorn src.main:app --reload --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000` in your browser.

## Docker Deployment

You can also run RepoIntel using Docker Compose:

```bash
docker-compose up --build
```
