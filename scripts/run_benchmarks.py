import os
import sys
import time
import json
import subprocess
import requests
import asyncio
import websockets
from datetime import datetime

def run_benchmarks():
    repos = [
        "https://github.com/octocat/Hello-World",
        "https://github.com/pallets/click"
    ]
    
    results = []
    
    raw_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../evidence/raw'))
    os.makedirs(raw_dir, exist_ok=True)
    server_log_path = os.path.join(raw_dir, "server_stdout.log")
    
    print("Starting FastAPI server...")
    with open(server_log_path, "w") as server_log:
        server_process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "src.main:app", "--port", "8001"],
            stdout=server_log,
            stderr=subprocess.STDOUT
        )
        
        try:
            # HTTP readiness loop
            print("Waiting for server to be ready...")
            ready = False
            for _ in range(10):
                try:
                    resp = requests.get("http://localhost:8001/api/health", timeout=2) # Assuming there is a health endpoint or we just check if connection opens. Wait, no health endpoint explicitly mentioned. Let's just do a GET to /
                    if resp.status_code in [200, 404]: # Either way, the server responded
                        ready = True
                        break
                except requests.exceptions.ConnectionError:
                    time.sleep(1)
            
            if not ready:
                print("Server failed to start.")
                sys.exit(1)
                
            print("Server is ready.")
            
            for repo_url in repos:
                print(f"Benchmarking repo: {repo_url}")
                start_time = time.time()
                
                try:
                    resp = requests.post("http://localhost:8001/api/analyze", json={"repo_url": repo_url})
                    resp.raise_for_status()
                    job_id = resp.json()["job_id"]
                    print(f"  Job started with ID: {job_id}")
                except Exception as e:
                    print(f"  Failed to start analysis for {repo_url}: {e}")
                    sys.exit(1)
                
                # Connect to WebSocket
                async def track_ws():
                    ws_events = []
                    try:
                        async with websockets.connect(f"ws://localhost:8001/api/ws/{job_id}", open_timeout=5) as ws:
                            while True:
                                # Add timeout to prevent hanging forever
                                msg = await asyncio.wait_for(ws.recv(), timeout=30.0)
                                data = json.loads(msg)
                                ws_events.append(data)
                                msg_type = data.get("type")
                                if msg_type == "progress":
                                    print(f"    [Progress] {data.get('agent')}: {data.get('message')}")
                                elif msg_type == "completed":
                                    print(f"    [Success] Analysis completed!")
                                    break
                                elif msg_type == "error":
                                    print(f"    [Error] {data.get('message')}")
                                    break
                    except asyncio.TimeoutError:
                        print(f"    [Error] WebSocket wait_for timed out.")
                    except Exception as e:
                        print(f"    WebSocket closed or error: {e}")
                    return ws_events
                    
                ws_events = asyncio.run(track_ws())
                
                end_time = time.time()
                duration = end_time - start_time
                
                success = any(e.get("type") == "completed" for e in ws_events)
                
                # Determine path
                # Since dummy key is used, it falls back
                used_fallback = any("QuotaExceeded" in str(e) or "API Error" in str(e) for e in ws_events) # Rough heuristic from progress messages or just assume True based on .env
                # Let's save raw events
                raw_events_path = os.path.join(raw_dir, f"ws_events_{job_id}.json")
                with open(raw_events_path, "w") as f:
                    json.dump(ws_events, f, indent=2)
                
                results.append({
                    "repo_url": repo_url,
                    "success": success,
                    "duration_seconds": round(duration, 2),
                    "events": len(ws_events),
                    "test_configuration_expected_fallback": True,
                    "raw_events_file": raw_events_path
                })
                
                print(f"  Finished {repo_url} in {duration:.2f} seconds.\n")
                
        finally:
            print("Shutting down server...")
            server_process.terminate()
            server_process.wait()

    # Get Git Hash
    try:
        git_hash = subprocess.check_output(['git', 'rev-parse', '--short', 'HEAD']).decode('ascii').strip()
    except Exception:
        git_hash = "unknown"

    summary = {
        "metadata": {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "os": os.name,
            "python_version": sys.version,
            "git_hash": git_hash
        },
        "runs": results
    }

    processed_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../evidence/processed'))
    os.makedirs(processed_dir, exist_ok=True)
    with open(os.path.join(processed_dir, "benchmark_summary.json"), "w") as f:
        json.dump(summary, f, indent=2)
        
    print("Benchmark complete. Results saved.")
    
    # Return non-zero exit code if any failed
    if not all(r["success"] for r in results):
        sys.exit(1)
    
if __name__ == "__main__":
    run_benchmarks()
