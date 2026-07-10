import time
import logging
from langchain_google_genai import ChatGoogleGenerativeAI
from ..config import AVAILABLE_API_KEYS, MODEL_NAME

logger = logging.getLogger(__name__)

def invoke_llm_with_retry(messages_or_prompt, structured_schema=None, max_retries_per_key=3, backoff_factor=2):
    """
    Invokes the LLM with exponential backoff and API key rotation.
    Handles 429 Too Many Requests by gracefully backing off and switching keys.
    """
    if not AVAILABLE_API_KEYS:
        raise ValueError("No API keys available.")
        
    last_exception = None
    
    for key_idx, api_key in enumerate(AVAILABLE_API_KEYS):
        logger.info(f"Attempting LLM call with API Key #{key_idx + 1}")
        
        # Initialize LLM for this specific key
        llm = ChatGoogleGenerativeAI(
            model=MODEL_NAME,
            api_key=api_key,
            temperature=0,
            max_output_tokens=8192,
            timeout=120,
            # We handle retries manually to control backoff and key rotation
            max_retries=0,
        )
        
        executor = llm
        if structured_schema:
            executor = llm.with_structured_output(structured_schema)
            
        wait_time = 2  # Initial wait time in seconds
        
        for attempt in range(max_retries_per_key):
            try:
                response = executor.invoke(messages_or_prompt)
                return response
            except Exception as e:
                exc_str = str(e)
                last_exception = e
                
                # Check if it's a rate limit error (429)
                if "429" in exc_str or "RESOURCE_EXHAUSTED" in exc_str:
                    logger.warning(f"Rate limit hit on API Key #{key_idx + 1}, attempt {attempt + 1}/{max_retries_per_key}. Waiting {wait_time}s...")
                    time.sleep(wait_time)
                    wait_time *= backoff_factor  # Exponential backoff
                else:
                    # For other errors, log and break out of the retry loop for this key
                    logger.error(f"Non-retriable error on API Key #{key_idx + 1}: {exc_str}")
                    break
                    
        logger.warning(f"Exhausted retries for API Key #{key_idx + 1}. Switching to next key if available.")
        
    logger.error("All API keys and retries exhausted.")
    raise last_exception
