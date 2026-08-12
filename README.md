# RepoIntel

AI-powered repository intelligence for public GitHub repositories.

[Interface Demo Placeholder] 

https://github.com/user-attachments/assets/1569206e-aef2-4779-88af-6c34e2f874ab



## What It Does

RepoIntel analyzes public GitHub repositories by separating deterministic repository analysis from semantic AI analysis.

Instead of sending an entire codebase directly to an LLM, RepoIntel first scans the repository, selects high-value source evidence, and then uses task-routed Gemini models to generate an engineering review.

This approach reduces unnecessary context sent to the LLM while keeping the pipeline predictable and resilient to AI API failures.

```text
GitHub URL
    ↓
Repository Scan
    ↓
Evidence Selection
    ↓
Engineering Analysis
    ↓
Model Cascade
    ↓
Engineering Intelligence Report
```

## Architecture

```mermaid
flowchart TD
    User["🌐 User (Browser)"]
    FastAPI["⚙️ FastAPI + WebSocket Server"]
    Scanner["repo_scanner_agent"]
    Clone["Shallow Clone"]
    Structural["Structural Scan\n(files, languages, CI/CD, configs)"]
    Evidence["evidence_selector.py\n(Dockerfiles, entry points, API files,\nCI/CD, config, source modules)"]
    Skip{"_should_skip_analysis"}
    Analyzer["engineering_analyzer_agent"]
    Router["model_router.py"]
    Primary["Gemini 3.5 Flash\n(Primary)"]
    Fallback["Gemini 3.1 Flash Lite\n(Fallback)"]
    Reporter["report_generator_agent"]
    StructReport["Structural Fallback Report"]
    FullReport["Engineering Intelligence Report"]
    WS["WebSocket Progress Events"]

    User -->|"POST /api/analyze\n(GitHub URL)"| FastAPI
    FastAPI -->|"LangGraph Workflow"| Scanner
    Scanner --> Clone
    Clone --> Structural
    Structural --> Evidence
    Evidence --> Skip

    Skip -->|"Scan OK"| Analyzer
    Skip -->|"Scan Failed"| Reporter

    Analyzer --> Router
    Router --> Primary
    Primary -->|"Rate limit / error"| Fallback
    Primary -->|"Success"| Reporter
    Fallback -->|"Success"| Reporter
    Fallback -->|"All models failed"| Reporter

    Reporter -->|"AI available"| FullReport
    Reporter -->|"AI unavailable"| StructReport

    FullReport --> WS
    StructReport --> WS
    WS -->|"ws://host/api/ws/{job_id}"| User

    Scanner -.->|"progress events"| WS
    Analyzer -.->|"progress events"| WS
```

## Design Decisions

### Why deterministic analysis before the LLM?

Repository structure, file counts, language detection, and configuration detection do not require an LLM.

Keeping these operations deterministic makes the system:

* More predictable
* Easier to debug
* Less dependent on external APIs
* More efficient with model context

### Why evidence selection?

Sending an entire repository to an LLM wastes context and increases processing cost.

RepoIntel therefore selects high-value files before semantic analysis so the model can focus on the parts of the repository most relevant to engineering evaluation.

### Why task-based model routing?

Not every operation requires the same model capability.

RepoIntel separates deterministic processing from semantic analysis and uses the configured Gemini models according to the task.

This avoids using expensive model reasoning for operations that can be handled deterministically.

### Why avoid a supervisor loop?

RepoIntel uses a deterministic LangGraph workflow rather than an LLM-controlled supervisor loop.

This provides a predictable execution path and avoids unnecessary iterative model calls.

The workflow is therefore easier to reason about, debug, and control.

### Why fallback behavior?

External AI APIs can fail because of:

* Rate limits
* Quota exhaustion
* Temporary availability issues
* API failures

RepoIntel therefore uses a model cascade and ultimately a deterministic structural fallback.

Even when semantic analysis cannot be completed, the system can still return useful structural information.

## Tech Stack

| Layer                       | Technology                              | Purpose                                       |
| --------------------------- | --------------------------------------- | --------------------------------------------- |
| **API Backend**             | Python, FastAPI                         | Serves the API and manages analysis jobs      |
| **Real-time Communication** | WebSockets                              | Streams pipeline progress to the client       |
| **AI Orchestration**        | LangGraph                               | Defines the deterministic analysis workflow   |
| **LLMs**                    | Gemini 3.5 Flash, Gemini 3.1 Flash Lite | Semantic repository analysis and fallback     |
| **Repository Analysis**     | Python                                  | Deterministic scanning and evidence selection |
| **Deployment**              | Docker, Docker Compose                  | Containerized deployment                      |

## Project Structure

```text
repo-intel/
├── src/
│   ├── agents/
│   │   ├── repo_scanner.py
│   │   ├── evidence_selector.py
│   │   ├── engineering_analyzer.py
│   │   └── report_generator.py
│   │
│   ├── api/
│   │   └── # FastAPI routes and WebSocket handlers
│   │
│   ├── graph/
│   │   └── workflow.py
│   │
│   └── providers/
│       └── # Gemini integrations and model cascading
│
├── frontend/
├── tests/
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## Verified Run

RepoIntel successfully analyzed its own repository using the V2 runtime.

* **39 files scanned**
* **2,595 lines of code**
* **15 evidence files selected**
* **31,354 evidence characters**
* **2 successful AI calls**
* **6.3/10 engineering score**
* **Analysis mode:** AI Enhanced

## Sample Output
<img width="422" height="847" alt="Screenshot 2026-08-11 160925" src="https://github.com/user-attachments/assets/f6e5fbf4-61a6-435f-89bc-c4a3d260cb4e" />

## TerminalOutput
<img width="1496" height="480" alt="image" src="https://github.com/user-attachments/assets/6c19da23-e499-4080-9cf2-cab8d28e3897" />


<!-- TODO: Add screenshots after running RepoIntel on a public repo -->
<!-- 1. Screenshot of the browser UI showing analysis in progress -->
<!-- 2. Screenshot of the final engineering report output -->

## Quick Start

### Requirements

* Python 3.12+
* Gemini API key

### Installation
```bash
How to Open CMD -->Press Windows Key + R on your keyboard.Type cmd into the box.Press Enter.Basic Steps to FollowType cd followed by a space to change folders.Type your folder path or name.Press Enter to run the Below command
```

```bash
git clone https://github.com/pepi-code-srt/repo-intel
```

```bash
python -m venv venv
```

#### Windows

```powershell
.\venv\Scripts\Activate.ps1
```

#### Linux / macOS

```bash
source venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

### Environment Variables

Create a `.env` file in the root directory:

```env
GEMINI_API_KEY=your_gemini_api_key_here
```

### Run Locally

```bash
uvicorn src.main:app --reload --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000
```

## API Endpoints

| Method | Endpoint               | Purpose                                          |
| ------ | ---------------------- | ------------------------------------------------ |
| `POST` | `/api/analyze`         | Initiates an analysis job and returns a `job_id` |
| `GET`  | `/api/report/{job_id}` | Retrieves the generated report                   |

## WebSocket Behavior

RepoIntel uses WebSockets to provide real-time pipeline progress.

### Connection

```text
ws://<host>/api/ws/{job_id}
```

### Progress Event

```json
{
  "type": "progress",
  "agent": "...",
  "message": "..."
}
```

Reports stage progress and timing information.

### Error Event

```json
{
  "type": "error",
  "message": "..."
}
```

Reports analysis failures.

### Completed Event

```json
{
  "type": "completed",
  "report": "..."
}
```

Delivers the final engineering report.

## Docker Deployment

RepoIntel can be deployed using Docker Compose.

```bash
docker-compose up --build
```

The configuration also provides a local `.repo_cache` volume for repository processing.

## Environment Variables

| Variable                | Required | Purpose                                                    |
| ----------------------- | -------- | ---------------------------------------------------------- |
| `GEMINI_API_KEY`        | **Yes**  | Authentication for Google Gemini APIs                      |
| `GEMINI_MODEL_PRIMARY`  | No       | Overrides the primary Gemini model                         |
| `GEMINI_MODEL_FAST`     | No       | Overrides the fast/helper model                            |
| `GEMINI_MODEL_FALLBACK` | No       | Overrides the fallback model                               |
| `ENABLE_FAST_HELPER`    | No       | Enables or disables the optional fast classification phase |

## Failure Handling

The pipeline is designed to avoid failing silently.

### Primary Model Failure

The engineering analysis can fall back to the configured fallback Gemini model when the primary model encounters a supported failure.

### Total AI Failure

If the configured AI models are unavailable, RepoIntel generates a deterministic structural report containing information such as:

* File counts
* Programming languages
* Configuration information
* CI/CD presence
* Basic repository health information

### Repository Failure

If the target repository cannot be cloned or scanned successfully, the workflow skips semantic analysis and proceeds to structural report generation.

## Limitations

* Currently supports public GitHub repositories.
* Shallow cloning limits deep historical analysis such as commit history and contributor velocity.
* The system relies on static repository analysis and AI interpretation.
* It does not compile or execute the analyzed repository.
* It does not perform dynamic security testing.

## Future Improvements

* GitLab and Bitbucket repository support
* Streaming final LLM output through WebSockets
* Deeper repository analysis
* Additional repository security analysis
* Expanded automated evaluation of generated engineering reports

## License

This project is licensed under the MIT License.
