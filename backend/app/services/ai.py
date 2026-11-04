"""The one shared OpenAI client, used by extraction and catalog matching."""

from functools import cache

from openai import OpenAI

from app.core.config import settings


@cache
def get_client() -> OpenAI:
    """Created once: 60 s timeout, one automatic retry on 429/5xx/connection errors."""
    return OpenAI(api_key=settings.openai_api_key, timeout=60, max_retries=1)
