"""Retry logic with exponential backoff."""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable

logger = logging.getLogger(__name__)

_DEFAULT_MAX_RETRIES = 3
_DEFAULT_RETRY_DELAY = 30


def _get_config_int(env_var: str, default: int) -> int:
    raw = os.environ.get(env_var, "")
    if raw.strip().isdigit():
        return int(raw)
    return default


def invoke_with_retry[T](
    func: Callable[[], T],
    max_retries: int | None = None,
    initial_delay: int | None = None,
) -> T:
    """Execute *func* with exponential backoff on failure.

    Raises the last exception after all retries are exhausted.
    """
    if max_retries is None:
        max_retries = _get_config_int("MAX_RETRIES", _DEFAULT_MAX_RETRIES)
    if initial_delay is None:
        initial_delay = _get_config_int("RETRY_DELAY", _DEFAULT_RETRY_DELAY)

    delay = initial_delay
    last_error: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            return func()
        except Exception as exc:
            last_error = exc
            if attempt == max_retries:
                raise RuntimeError(
                    f"All {max_retries} attempts failed. Last error: {exc}"
                ) from exc
            logger.warning(
                "Attempt %d/%d failed, retrying in %ds...",
                attempt,
                max_retries,
                delay,
            )
            time.sleep(delay)
            delay *= 2

    # Unreachable, but satisfies type checker
    raise RuntimeError(f"All {max_retries} attempts failed. Last error: {last_error}")
