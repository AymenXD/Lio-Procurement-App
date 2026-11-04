"""The one shared OpenAI client, used by extraction, classification and catalog matching."""

import logging
import time
from functools import cache

from openai import OpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)


@cache
def get_client() -> OpenAI:
    """Created once: 60 s timeout, one automatic retry on 429/5xx/connection errors."""
    return OpenAI(api_key=settings.openai_api_key, timeout=60, max_retries=1)


def log_call(step: str, started: float, outcome: str, usage: object = None) -> None:
    """Log duration, tokens and outcome only; never document text or the key."""
    logger.info(
        "AI %s outcome=%s duration_ms=%d prompt_tokens=%s completion_tokens=%s",
        step,
        outcome,
        (time.perf_counter() - started) * 1000,
        getattr(usage, "prompt_tokens", None),
        getattr(usage, "completion_tokens", None),
    )
