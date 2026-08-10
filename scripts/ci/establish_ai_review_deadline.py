#!/usr/bin/env python3
"""Publish the absolute deadline used by the shared AI review action."""

from __future__ import annotations

import os
import re
import sys
import time
from collections.abc import Mapping
from pathlib import Path

EXIT_OK = 0
EXIT_CONFIG = 2
CONTEXT_BUDGET_SECONDS = 210
MINIMUM_MODEL_BUDGET_SECONDS = 300
FINALIZATION_RESERVE_SECONDS = 60
DEADLINE_PATTERN = re.compile(r"[0-9]+(?:\.[0-9]+)?")


def resolve_deadline(env: Mapping[str, str], *, now: float) -> float:
    timeout_text = env.get("TIMEOUT_MINUTES", "")
    try:
        timeout_minutes = int(timeout_text)
    except ValueError as exc:
        raise ValueError("timeout-minutes must be a non-negative integer") from exc
    if timeout_minutes < 0:
        raise ValueError("timeout-minutes must be a non-negative integer")

    inherited = env.get("INHERITED_DEADLINE_EPOCH", "")
    if inherited:
        if not DEADLINE_PATTERN.fullmatch(inherited):
            raise ValueError("AI_REVIEW_ACTION_DEADLINE_EPOCH must be numeric")
        return float(inherited)

    model_budget = max(timeout_minutes * 60, MINIMUM_MODEL_BUDGET_SECONDS)
    return now + CONTEXT_BUDGET_SECONDS + model_budget + FINALIZATION_RESERVE_SECONDS


def main() -> int:
    output = os.environ.get("GITHUB_OUTPUT", "")
    if not output:
        print("error: GITHUB_OUTPUT is required", file=sys.stderr)
        return EXIT_CONFIG
    try:
        deadline = resolve_deadline(os.environ, now=time.time())
        with Path(output).open("a", encoding="utf-8") as handle:
            handle.write(f"deadline_epoch={deadline:.6f}\n")
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
