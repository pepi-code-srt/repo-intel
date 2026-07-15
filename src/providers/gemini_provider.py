"""
RepoIntel — Clean Gemini Provider
Single provider abstraction using the official google-genai SDK.

KEY BEHAVIOR: Smart model first, automatic cascade on failure.
  1. Try the strongest model (e.g., gemini-3.5-flash)
  2. If busy (503) or rate-limited (429), try next model
  3. If ALL models fail, return a clear error explaining what happened and how to fix it
"""
import time
import json
import logging
from typing import Optional, Type
from pydantic import BaseModel
from google import genai
from google.genai import types
from google.genai.errors import APIError

logger = logging.getLogger(__name__)


class ProviderError(Exception):
    """Classified provider error with user-facing guidance."""
    def __init__(self, message: str, category: str = "unknown", retryable: bool = False,
                 user_message: str = "", fix_instructions: str = ""):
        super().__init__(message)
        self.category = category
        self.retryable = retryable
        self.user_message = user_message or message
        self.fix_instructions = fix_instructions


class AIRequestLog(BaseModel):
    """Sanitized metadata for one AI request."""
    task_id: str
    task_role: str
    model: str
    attempt: int
    status: str  # "success" | "error"
    duration_ms: int
    error_category: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None


# === Error classification ===

_ERROR_GUIDANCE = {
    "model_not_found": {
        "user_msg": "The AI model '{model}' is no longer available.",
        "fix": (
            "Update your .env file with a valid model:\n"
            "  GEMINI_MODEL_PRIMARY=gemini-3.1-flash-lite\n"
            "Then restart the server."
        ),
    },
    "auth_error": {
        "user_msg": "Your Gemini API key is invalid or missing permissions.",
        "fix": (
            "1. Go to https://aistudio.google.com/apikey\n"
            "2. Create or copy your API key\n"
            "3. Add it to your .env file: GEMINI_API_KEY=your_key_here\n"
            "4. Restart the server."
        ),
    },
    "rate_limit": {
        "user_msg": "All configured AI models are currently rate-limited.",
        "fix": (
            "The free tier has limited requests per minute/day.\n"
            "Wait a few minutes and try again, or:\n"
            "1. Check your quota at https://aistudio.google.com\n"
            "2. Consider upgrading your API plan for higher limits."
        ),
    },
    "invalid_request": {
        "user_msg": "The AI request was rejected due to a schema or format issue.",
        "fix": "This is a bug in RepoIntel. Please report it.",
    },
    "server_error": {
        "user_msg": "All AI models are temporarily unavailable (server error).",
        "fix": "Google's servers may be experiencing issues. Wait a few minutes and try again.",
    },
    "timeout": {
        "user_msg": "The AI request timed out.",
        "fix": "Try again. If it keeps happening, the repository may be too large to analyze.",
    },
}


def _classify_error(e: APIError, model: str) -> ProviderError:
    """Classify an API error into a known category with user-facing guidance."""
    exc_str = str(e)
    code = getattr(e, 'code', None)

    if code == 404 or "not found" in exc_str.lower():
        cat = "model_not_found"
        retryable = False
    elif code in (401, 403) or "API_KEY_INVALID" in exc_str or "PERMISSION_DENIED" in exc_str:
        cat = "auth_error"
        retryable = False
    elif code == 400 or "INVALID_ARGUMENT" in exc_str:
        cat = "invalid_request"
        retryable = False
    elif code == 429 or "RESOURCE_EXHAUSTED" in exc_str:
        cat = "rate_limit"
        retryable = True  # Can retry with a different model
    elif code is not None and code >= 500:
        cat = "server_error"
        retryable = True
    elif "timeout" in exc_str.lower():
        cat = "timeout"
        retryable = True
    else:
        cat = "unknown"
        retryable = False

    guidance = _ERROR_GUIDANCE.get(cat, {"user_msg": exc_str, "fix": ""})
    user_msg = guidance["user_msg"].format(model=model)

    return ProviderError(
        message=exc_str,
        category=cat,
        retryable=retryable,
        user_message=user_msg,
        fix_instructions=guidance["fix"],
    )


class GeminiProvider:
    """
    Single clean Gemini provider using the official google-genai SDK.

    KEY: Uses automatic model cascade.
    - Tries the strongest model first
    - On retryable failure (503, 429), tries the next model in the cascade
    - On permanent failure (404, 401), skips that model
    - If ALL models fail, returns a clear error with fix instructions
    """

    MAX_RETRIES_PER_MODEL = 1  # Keep it tight — don't hammer one model
    BACKOFF_SECONDS = 2.0

    def __init__(self, api_key: str):
        if not api_key:
            raise ProviderError(
                "No API key provided.",
                category="auth_error",
                user_message="No Gemini API key configured.",
                fix_instructions="Add GEMINI_API_KEY=your_key to your .env file and restart.",
            )
        self._client = genai.Client(api_key=api_key)
        self._request_logs: list[AIRequestLog] = []

    @property
    def request_logs(self) -> list[AIRequestLog]:
        """Get all recorded request logs (sanitized, no secrets)."""
        return self._request_logs

    def generate_text(
        self,
        prompt: str,
        model_cascade: list[str],
        task_id: str,
        task_role: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.2,
        max_output_tokens: int = 8192,
    ) -> tuple[str, str]:
        """
        Plain text generation with automatic model cascade.
        Returns (response_text, model_used).
        Tries strongest model first, falls through on failure.
        """
        config_args = {
            "temperature": temperature,
            "max_output_tokens": max_output_tokens,
        }
        if system_instruction:
            config_args["system_instruction"] = system_instruction

        return self._execute_with_cascade(
            prompt=prompt,
            model_cascade=model_cascade,
            task_id=task_id,
            task_role=task_role,
            config_args=config_args,
            structured_schema=None,
        )

    def generate_structured(
        self,
        prompt: str,
        schema: Type[BaseModel],
        model_cascade: list[str],
        task_id: str,
        task_role: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.1,
        max_output_tokens: int = 8192,
    ) -> tuple[dict, str]:
        """
        Structured JSON generation with automatic model cascade.
        Returns (parsed_dict, model_used).
        """
        config_args = {
            "temperature": temperature,
            "max_output_tokens": max_output_tokens,
            "response_mime_type": "application/json",
            "response_schema": schema,
        }
        if system_instruction:
            config_args["system_instruction"] = system_instruction

        return self._execute_with_cascade(
            prompt=prompt,
            model_cascade=model_cascade,
            task_id=task_id,
            task_role=task_role,
            config_args=config_args,
            structured_schema=schema,
        )

    def _execute_with_cascade(
        self,
        prompt: str,
        model_cascade: list[str],
        task_id: str,
        task_role: str,
        config_args: dict,
        structured_schema: Optional[Type[BaseModel]],
    ):
        """
        Try each model in cascade order. First success wins.
        On retryable/transient failures, move to next model.
        On permanent failures (auth, invalid request), stop immediately.
        """
        all_errors: list[tuple[str, ProviderError]] = []

        for model in model_cascade:
            try:
                result = self._execute_single(
                    prompt=prompt,
                    model=model,
                    task_id=task_id,
                    task_role=task_role,
                    config_args=config_args,
                    structured_schema=structured_schema,
                )
                # Success — log which model was used
                if model != model_cascade[0]:
                    logger.info(
                        "[AI] Cascade: primary model '%s' was unavailable, succeeded with '%s'",
                        model_cascade[0], model,
                    )
                return result

            except ProviderError as e:
                all_errors.append((model, e))
                logger.warning(
                    "[AI] Model '%s' failed (%s): %s — trying next model...",
                    model, e.category, str(e)[:150],
                )

                # Auth errors are permanent — don't try other models with same key
                if e.category == "auth_error":
                    break

                # Invalid request is a code bug — don't try other models (same schema)
                if e.category == "invalid_request":
                    break

                # For rate_limit, server_error, model_not_found, timeout — try next model
                continue

        # ALL models failed — build a clear user-facing error
        raise self._build_cascade_error(all_errors, model_cascade)

    def _build_cascade_error(
        self, errors: list[tuple[str, ProviderError]], cascade: list[str]
    ) -> ProviderError:
        """Build a clear, user-facing error when all models in the cascade have failed."""
        if not errors:
            return ProviderError(
                "No models configured.",
                category="no_models",
                user_message="No AI models are configured.",
                fix_instructions="Add GEMINI_MODEL_PRIMARY to your .env file.",
            )

        # Find the most common/important error category
        categories = [e.category for _, e in errors]

        # Build a summary of what happened
        model_status_lines = []
        for model, err in errors:
            model_status_lines.append(f"  • {model}: {err.category} — {err.user_message}")
        model_status = "\n".join(model_status_lines)

        # Determine the best fix based on what went wrong
        if "auth_error" in categories:
            primary_cat = "auth_error"
        elif all(c in ("rate_limit", "server_error") for c in categories):
            primary_cat = "rate_limit"
        elif "invalid_request" in categories:
            primary_cat = "invalid_request"
        elif "model_not_found" in categories and all(c == "model_not_found" for c in categories):
            primary_cat = "model_not_found"
        else:
            primary_cat = categories[-1]  # Use the last error's category

        guidance = _ERROR_GUIDANCE.get(primary_cat, {"user_msg": "AI analysis failed.", "fix": ""})

        user_message = (
            f"AI analysis could not be completed. "
            f"All {len(errors)} configured model(s) failed:\n{model_status}"
        )
        fix = guidance["fix"]

        return ProviderError(
            message=f"All models failed: {categories}",
            category=primary_cat,
            user_message=user_message,
            fix_instructions=fix,
        )

    def _execute_single(
        self,
        prompt: str,
        model: str,
        task_id: str,
        task_role: str,
        config_args: dict,
        structured_schema: Optional[Type[BaseModel]],
    ):
        """Execute against a single model with bounded retry (1 retry for transient errors)."""
        last_error = None

        for attempt in range(1, self.MAX_RETRIES_PER_MODEL + 1):
            start_ms = time.time()
            try:
                response = self._client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=types.GenerateContentConfig(**config_args),
                )
                elapsed = int((time.time() - start_ms) * 1000)

                # Extract usage metadata
                input_tokens = None
                output_tokens = None
                if hasattr(response, 'usage_metadata') and response.usage_metadata:
                    um = response.usage_metadata
                    input_tokens = getattr(um, 'prompt_token_count', None)
                    output_tokens = getattr(um, 'candidates_token_count', None)

                # Log success
                log_entry = AIRequestLog(
                    task_id=task_id, task_role=task_role, model=model,
                    attempt=attempt, status="success", duration_ms=elapsed,
                    input_tokens=input_tokens, output_tokens=output_tokens,
                )
                self._request_logs.append(log_entry)
                logger.info(
                    "[AI] task=%s model=%s attempt=%d status=success duration=%dms tokens_in=%s tokens_out=%s",
                    task_id, model, attempt, elapsed,
                    input_tokens or "?", output_tokens or "?",
                )

                # Parse result
                if structured_schema is not None:
                    text = response.text or ""
                    parsed = json.loads(text)
                    validated = structured_schema(**parsed)
                    return (validated.model_dump(), model)
                else:
                    return (response.text or "", model)

            except APIError as e:
                elapsed = int((time.time() - start_ms) * 1000)
                classified = _classify_error(e, model)

                log_entry = AIRequestLog(
                    task_id=task_id, task_role=task_role, model=model,
                    attempt=attempt, status="error", duration_ms=elapsed,
                    error_category=classified.category,
                )
                self._request_logs.append(log_entry)
                logger.warning(
                    "[AI] task=%s model=%s attempt=%d status=error category=%s duration=%dms",
                    task_id, model, attempt, classified.category, elapsed,
                )

                last_error = classified

                if not classified.retryable or attempt >= self.MAX_RETRIES_PER_MODEL:
                    raise classified

                # Brief backoff before retry on same model
                time.sleep(self.BACKOFF_SECONDS)

            except json.JSONDecodeError as e:
                elapsed = int((time.time() - start_ms) * 1000)
                self._request_logs.append(AIRequestLog(
                    task_id=task_id, task_role=task_role, model=model,
                    attempt=attempt, status="error", duration_ms=elapsed,
                    error_category="invalid_response",
                ))
                raise ProviderError(
                    f"Failed to parse AI response as JSON: {e}",
                    category="invalid_response",
                    user_message="The AI returned an invalid response format.",
                    fix_instructions="This is a bug in RepoIntel. Try again or report the issue.",
                )

            except ProviderError:
                raise

            except Exception as e:
                elapsed = int((time.time() - start_ms) * 1000)
                self._request_logs.append(AIRequestLog(
                    task_id=task_id, task_role=task_role, model=model,
                    attempt=attempt, status="error", duration_ms=elapsed,
                    error_category="unknown",
                ))
                raise ProviderError(
                    str(e),
                    category="unknown",
                    user_message=f"Unexpected error with model '{model}'.",
                    fix_instructions="Try again. If it persists, check your API key and model configuration.",
                )

        raise last_error or ProviderError("Retries exhausted", category="exhausted")
