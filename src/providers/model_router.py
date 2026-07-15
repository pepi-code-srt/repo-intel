"""
RepoIntel — Task-Based Model Router
Maps task roles to configured model IDs.
"""
import logging
from ..config import get_model_config

logger = logging.getLogger(__name__)


def get_model_for_task(task_role: str) -> str:
    """
    Returns the model ID for a given task role.

    Task roles:
        "primary_engineering_review" -> primary model
        "fast_helper"               -> fast model
        "fallback"                  -> fallback model

    Falls back to primary model for unknown roles.
    """
    config = get_model_config()
    role_mapping = {
        "primary_engineering_review": "primary",
        "fast_helper": "fast",
        "fallback": "fallback",
    }
    model_role = role_mapping.get(task_role, "primary")
    model_id = config.get(model_role, config["primary"])
    return model_id


def get_fallback_model_for(task_role: str) -> str | None:
    """
    Returns the fallback model for a given task, or None if no fallback is configured
    or the fallback is the same as the primary.
    """
    config = get_model_config()
    primary_model = get_model_for_task(task_role)
    fallback_model = config.get("fallback")

    if fallback_model and fallback_model != primary_model:
        return fallback_model
    return None
