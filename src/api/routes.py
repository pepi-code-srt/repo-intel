import uuid
import asyncio
import glob
import shutil
import tempfile
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
        "logs": []
    }
    
    # Always run fresh analysis — no cache
    asyncio.create_task(run_analysis(job_id, req.repo_url))
    
    return AnalyzeResponse(job_id=job_id, message="Analysis started.")

async def run_analysis(job_id: str, repo_url: str):
    logger.info(f"Starting analysis for job {job_id}: {repo_url}")
    jobs[job_id]["status"] = "running"
    
    initial_state = {
        "repo_url": repo_url,
        "messages": [],
        "repo_path": "",
        "repo_structure": {},
        "repo_metadata": {},
        "readme_content": "",
        "dependencies": [],
        "source_samples": {},
        "repo_statistics": {},
        "repo_health": {},
        "agent_findings": {},
        "final_report": "",
        "report_metadata": {},
        "next_agent": ""
    }
    
    cloned_path = None
    
    try:
        # We use astream to get events as they happen
        async for output in graph.astream(initial_state, config={"recursion_limit": 30}):
            # Output is a dict keyed by the node name that just ran
            for node_name, state_update in output.items():
                msg = f"Agent '{node_name}' completed its task."
                jobs[job_id]["logs"].append(msg)
                logger.info(msg)
                
                # Track cloned repo path for cleanup
                if "repo_path" in state_update and state_update["repo_path"]:
                    cloned_path = state_update["repo_path"]
                
                # Send update via WebSocket if connected
                if job_id in active_connections:
                    ws = active_connections[job_id]
                    try:
                        await ws.send_json({"type": "progress", "agent": node_name, "message": msg})
                    except Exception:
                        pass
                
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
        logger.error(f"Job {job_id} failed: {str(e)}")
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["logs"].append(f"Error: {str(e)}")
        if job_id in active_connections:
            try:
                await active_connections[job_id].send_json({"type": "error", "message": str(e)})
            except Exception:
                pass
    finally:
        # Clean up cloned repo immediately after analysis
        if cloned_path:
            try:
                shutil.rmtree(cloned_path, ignore_errors=True)
                logger.info(f"Cleaned up cloned repo: {cloned_path}")
            except Exception:
                pass

@router.get("/report/{job_id}", response_model=ReportResponse)
async def get_report(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
        
    return ReportResponse(
        job_id=job_id,
        status=jobs[job_id]["status"],
        report=jobs[job_id].get("report") or ""
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
        # Keep connection open until client disconnects or job finishes
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
    import os
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
