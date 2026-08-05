"""Retry logic with exponential backoff."""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable
from typing import TypeVar

logger = logging.getLogger(__name__)

# PEP 695 generic syntax `def invoke_with_retry[T](...)` requires Python 3.12+,
# but this module must parse under the hook-execution syntax floor of Python
# 3.10 (scripts/validation/validate_python_syntax.py), independent of the
# pyproject install contract. Use the 3.10-compatible TypeVar form.
# PR #1965 copilot review (cluster G).
T = TypeVar("T")

_DEFAULT_MAX_RETRIES = 3
_DEFAULT_RETRY_DELAY = 30


def _get_config_int(env_var: str, default: int) -> int:
    raw = os.environ.get(env_var, "")
    if raw.strip().isdigit():
        return int(raw)
    return default


def invoke_with_retry(
    func: Callable[[], T],
    max_retries: int | None = None,
    initial_delay: int | None = None,
) -> T:
    """Execute *func* with exponential backoff on failure.

    Raises the last exception after all retries are exhausted.

    Raises `ValueError` when the resolved `max_retries` is not an integer or is
    below 1. The loop never runs for a non-positive value, and its fallthrough
    then reports `All 0 attempts failed. Last error: None`, which reads as an
    exhausted retry sequence for a call that was never made. `MAX_RETRIES=0`
    in the environment reaches this, so it is a live misconfiguration
    (issue #4121).
    """
    if max_retries is None:
        max_retries = _get_config_int("MAX_RETRIES", _DEFAULT_MAX_RETRIES)
    if initial_delay is None:
        initial_delay = _get_config_int("RETRY_DELAY", _DEFAULT_RETRY_DELAY)
    if type(max_retries) is not int or max_retries < 1:
        raise ValueError(
            f"max_retries must be an integer >= 1, got {max_retries!r}"
        )

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
