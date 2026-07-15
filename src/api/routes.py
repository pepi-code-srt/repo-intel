"""
RepoIntel — API Routes
Handles analysis jobs, WebSocket progress, and report retrieval.
"""
import uuid
import asyncio
import shutil
import tempfile
import os
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from typing import Dict
from .schemas import AnalyzeRequest, AnalyzeResponse, ReportResponse
from ..graph.workflow import build_graph
from ..utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()

# In-memory store for demo purposes. Use Redis in production.
jobs: Dict[str, dict] = {}
active_connections: Dict[str, WebSocket] = {}

# Pre-compile the LangGraph workflow
graph = build_graph()


@router.post("/analyze", response_model=AnalyzeResponse)
async def start_analysis(req: AnalyzeRequest):
    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "status": "pending",
        "repo_url": req.repo_url,
        "report": None,
        "logs": [],
    }

    asyncio.create_task(run_analysis(job_id, req.repo_url))

    return AnalyzeResponse(job_id=job_id, message="Analysis started.")


async def send_progress(job_id: str, message: str, agent: str = "system"):
    """Send a progress update to the WebSocket and log it."""
    jobs[job_id]["logs"].append(message)
    logger.info(message)

    if job_id in active_connections:
        ws = active_connections[job_id]
        try:
            await ws.send_json({"type": "progress", "agent": agent, "message": message})
        except Exception:
            pass


async def run_analysis(job_id: str, repo_url: str):
    logger.info(f"Starting analysis for job {job_id}: {repo_url}")
    jobs[job_id]["status"] = "running"

    initial_state = {
        "repo_url": repo_url,
        "repo_path": "",
        "repo_structure": {},
        "repo_metadata": {},
        "readme_content": "",
        "dependencies": [],
        "source_samples": {},
        "repo_statistics": {},
        "repo_health": {},
        "analyzed_commit_sha": None,
        "evidence": {},
        "evidence_metadata": {},
        "agent_findings": {},
        "analysis_mode": "structural",
        "ai_model_used": None,
        "ai_requests_log": [],
        "fast_helper_result": None,
        "fast_helper_model": None,
        "final_report": "",
        "report_metadata": {},
        "fallback_reason": None,
        "error_message": None,
        "fix_instructions": None,
        "progress_messages": [],
    }

    cloned_path = None

    try:
        async for output in graph.astream(initial_state, config={"recursion_limit": 10}):
            for node_name, state_update in output.items():
                # Generate user-facing progress messages based on node
                if node_name == "repo_scanner":
                    if "_error" in state_update.get("repo_structure", {}):
                        msg = "❌ Repository clone failed"
                    else:
                        stats = state_update.get("repo_statistics", {})
                        msg = (
                            f"✓ Repository cloned and scanned — "
                            f"{stats.get('total_files', '?')} files, "
                            f"{stats.get('lines_of_code', '?'):,} LOC"
                        )

                elif node_name == "engineering_analyzer":
                    mode = state_update.get("analysis_mode", "structural")
                    ai_model = state_update.get("ai_model_used")
                    fast_model = state_update.get("fast_helper_model")

                    if fast_model:
                        await send_progress(
                            job_id,
                            f"✓ Fast classification completed (model: {fast_model})",
                            "fast_helper",
                        )

                    if mode in ("ai_enhanced", "ai_enhanced_fallback"):
                        fallback_note = " (fallback model)" if mode == "ai_enhanced_fallback" else ""
                        msg = f"✓ AI engineering analysis completed{fallback_note} (model: {ai_model})"
                    else:
                        reason = state_update.get("fallback_reason", "unknown")
                        error_msg = state_update.get("error_message", "")
                        msg = f"⚠ AI analysis unavailable ({reason}). Structural analysis completed."
                        if error_msg:
                            await send_progress(job_id, f"ℹ {error_msg}", "system")
                        fix = state_update.get("fix_instructions", "")
                        if fix:
                            await send_progress(job_id, f"💡 How to fix: {fix}", "system")

                elif node_name == "report_generator":
                    msg = "✓ Final report generated"

                else:
                    msg = f"✓ {node_name} completed"

                await send_progress(job_id, msg, node_name)

                # Track cloned repo path for cleanup
                if "repo_path" in state_update and state_update["repo_path"]:
                    cloned_path = state_update["repo_path"]

                # Capture the final report
                if "final_report" in state_update and state_update["final_report"]:
                    jobs[job_id]["report"] = state_update["final_report"]

        jobs[job_id]["status"] = "completed"
        logger.info(f"Job {job_id} completed successfully.")

        # Send final completion via WS
        if job_id in active_connections:
            ws = active_connections[job_id]
            try:
                await ws.send_json({"type": "completed", "report": jobs[job_id]["report"]})
            except Exception:
                pass

    except Exception as e:
        error_str = str(e)
        logger.error(f"Job {job_id} failed: {error_str}")
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["logs"].append(f"Error: {error_str}")
        if job_id in active_connections:
            try:
                await active_connections[job_id].send_json({
                    "type": "error",
                    "message": f"Analysis failed: {error_str}",
                })
            except Exception:
                pass
    finally:
        # Clean up cloned repo immediately after analysis
        if cloned_path:
            try:
                shutil.rmtree(cloned_path, ignore_errors=True)
                logger.info(f"Cleaned up cloned repo: {cloned_path}")
                await send_progress(job_id, "✓ Temporary files cleaned up", "cleanup")
            except Exception:
                pass


@router.get("/report/{job_id}", response_model=ReportResponse)
async def get_report(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    return ReportResponse(
        job_id=job_id,
        status=jobs[job_id]["status"],
        report=jobs[job_id].get("report") or "",
    )


@router.websocket("/ws/{job_id}")
async def websocket_endpoint(websocket: WebSocket, job_id: str):
    await websocket.accept()
    if job_id not in jobs:
        await websocket.send_json({"type": "error", "message": "Job not found"})
        await websocket.close()
        return

    active_connections[job_id] = websocket
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for job {job_id}")
    finally:
        if job_id in active_connections:
            del active_connections[job_id]


def cleanup_all_temp_repos():
    """Clean all repo-intel temp directories on shutdown."""
    temp_dir = tempfile.gettempdir()
    count = 0
    for entry in os.listdir(temp_dir):
        if entry.startswith("repo-intel-"):
            full_path = os.path.join(temp_dir, entry)
            try:
                shutil.rmtree(full_path, ignore_errors=True)
                count += 1
            except Exception:
                pass
    if count:
        logger.info(f"Shutdown cleanup: removed {count} temp repo(s).")
