"""Write ai-review context to GitHub Actions outputs."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Protocol


class ReviewContextLike(Protocol):
    text: str
    mode: str
    infrastructure_failure: bool


class OutputConfigError(RuntimeError):
    """Output environment is missing required GitHub Actions fields."""


def sanitize_file_identifier(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")
    return cleaned or "local"


def append_output(output_path: Path, key: str, value: str) -> None:
    with output_path.open("a", encoding="utf-8") as output:
        output.write(f"{key}={value}\n")


def choose_multiline_delimiter(key: str, value: str) -> str:
    payload_lines = set(value.splitlines())
    base = f"EOF_{key.upper()}"
    delimiter = base
    suffix = 0
    while delimiter in payload_lines:
        suffix += 1
        delimiter = f"{base}_{suffix}"
    return delimiter


def append_multiline_output(output_path: Path, key: str, value: str) -> None:
    delimiter = choose_multiline_delimiter(key, value)
    with output_path.open("a", encoding="utf-8") as output:
        output.write(f"{key}<<{delimiter}\n{value}\n{delimiter}\n")


def write_outputs(review_context: ReviewContextLike) -> None:
    github_output = os.environ.get("GITHUB_OUTPUT")
    if not github_output:
        raise OutputConfigError("GITHUB_OUTPUT is required")

    output_path = Path(github_output)
    run_id = os.environ.get("GITHUB_RUN_ID", "local")
    context_identifier = sanitize_file_identifier(os.environ.get("PR_NUMBER") or run_id)
    runner_temp = os.environ.get("RUNNER_TEMP")
    if not runner_temp:
        raise OutputConfigError("RUNNER_TEMP is required")
    workspace = Path(runner_temp).resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    context_file = workspace / f"ai-review-context-pr{context_identifier}.txt"
    context_file.write_text(review_context.text, encoding="utf-8")

    append_output(output_path, "context_mode", review_context.mode)
    append_output(output_path, "context_file", str(context_file))
    if review_context.infrastructure_failure:
        append_output(output_path, "context_infra_failure", "true")
    append_multiline_output(output_path, "context_built", review_context.text)
