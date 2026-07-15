"""Quick test: provider cascade + structured output."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import GEMINI_API_KEY, get_model_cascade
from src.providers.gemini_provider import GeminiProvider

provider = GeminiProvider(api_key=GEMINI_API_KEY)
cascade = get_model_cascade()
print(f"Testing cascade: {cascade}")
print()

# Test 1: Plain text generation
print("=== TEST 1: Plain text generation ===")
text, model = provider.generate_text(
    prompt="Reply with exactly: REPOINTEL_TEST_OK",
    model_cascade=cascade,
    task_id="test_plain",
    task_role="test",
)
print(f"[OK] model={model}, response={text.strip()[:60]}")
print()

# Test 2: Structured output
print("=== TEST 2: Structured output ===")
from src.agents.schemas import FastHelperResponse
result, model2 = provider.generate_structured(
    prompt="Classify this repo: a Python FastAPI web app with Docker. Return JSON.",
    schema=FastHelperResponse,
    model_cascade=cascade,
    task_id="test_structured",
    task_role="test",
)
print(f"[OK] model={model2}, type={result.get('repository_type', '?')}")
print()

# Test 3: Full EngineeringFindings schema
print("=== TEST 3: Full EngineeringFindings schema ===")
from src.agents.schemas import EngineeringFindings
result3, model3 = provider.generate_structured(
    prompt="""Analyze this small Python project evidence:
--- main.py ---
from fastapi import FastAPI
app = FastAPI()

@app.get("/")
def root():
    return {"status": "ok"}

--- requirements.txt ---
fastapi
uvicorn

Score code_quality, security, and devops (0-10 each).""",
    schema=EngineeringFindings,
    model_cascade=cascade,
    task_id="test_full_schema",
    task_role="primary_engineering_review",
    system_instruction="You are a senior engineer reviewing code. Return structured JSON only.",
)
print(f"[OK] model={model3}")
print(f"  code_quality: score={result3['code_quality']['score']}, status={result3['code_quality']['status']}")
print(f"  security:     score={result3['security']['score']}, status={result3['security']['status']}")
print(f"  devops:       score={result3['devops']['score']}, status={result3['devops']['status']}")
print()

# Print all request logs
print("=== REQUEST LOGS ===")
for log in provider.request_logs:
    cat = log.error_category or "-"
    print(f"  [{log.status:7s}] task={log.task_id:25s} model={log.model:25s} dur={log.duration_ms:5d}ms  cat={cat}")

print()
print("ALL TESTS PASSED")
