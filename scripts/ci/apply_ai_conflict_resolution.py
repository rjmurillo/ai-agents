"""Apply AI-recommended conflict resolutions to a PR branch.

Replaces the inline PowerShell block in pr-maintenance.yml (ADR-006).
Parses the AI findings JSON (handling markdown code fences), checks out
the PR branch, merges the base, applies theirs/ours/combine strategies,
commits, and pushes via safe_push_pr_branch.py.

EXIT CODES (ADR-035):
  0 - Success
  1 - Parse failure, missing required fields, or push failure
  2 - Configuration error (HEAD_REF or BASE_REF not set)
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys
from typing import Any

EXIT_SUCCESS = 0
EXIT_FAILURE = 1
EXIT_CONFIG = 2

_SAFE_PUSH = ".trusted-helper/.github/scripts/safe_push_pr_branch.py"


def _git(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], capture_output=True, text=True, encoding="utf-8")


def _safe_repo_path(filepath: str) -> str:
    """Reject absolute paths and path-traversal sequences; return filepath unchanged."""
    p = pathlib.Path(filepath)
    if p.is_absolute():
        raise ValueError(f"Absolute path rejected: {filepath!r}")
    resolved = (pathlib.Path.cwd() / p).resolve()
    try:
        resolved.relative_to(pathlib.Path.cwd().resolve())
    except ValueError as exc:
        raise ValueError(f"Path traversal rejected: {filepath!r}") from exc
    return filepath


def extract_json(text: str) -> str:
    """Strip markdown code fences from AI output and return the JSON content."""
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence_match:
        return fence_match.group(1).strip()
    return text


def parse_resolutions(findings: str) -> list[dict[str, Any]]:
    """Return list of resolution dicts from AI findings text."""
    json_text = extract_json(findings)
    obj_match = re.search(r"\{[\s\S]*\"resolutions\"[\s\S]*\}", json_text)
    if not obj_match:
        raise ValueError("No JSON object with 'resolutions' key found in AI output")
    parsed = json.loads(obj_match.group(0))
    resolutions = parsed.get("resolutions")
    if resolutions is None:
        raise ValueError("AI output missing 'resolutions' array")
    if not isinstance(resolutions, list) or len(resolutions) == 0:
        raise ValueError("AI returned empty resolutions array")
    return resolutions


def apply_resolution(res: dict[str, Any]) -> None:
    filepath = _safe_repo_path(res.get("file", ""))
    strategy = res.get("strategy", "")
    print(f"Resolving {filepath} with strategy: {strategy}")
    print(f"  Reasoning: {res.get('reasoning', '')}")

    if strategy == "theirs":
        _git(["checkout", "--theirs", filepath])
        _git(["add", filepath])
    elif strategy == "ours":
        _git(["checkout", "--ours", filepath])
        _git(["add", filepath])
    elif strategy == "combine":
        combined = res.get("combined_content")
        if combined is None:
            raise ValueError(f"Combine strategy requires combined_content for {filepath}")
        with open(filepath, "w", encoding="utf-8", newline="") as f:
            f.write(combined)
        _git(["add", filepath])
    else:
        raise ValueError(f"Unknown strategy: {strategy}")


def main() -> int:
    pr_number = os.environ.get("PR_NUMBER", "")
    head_ref = os.environ.get("HEAD_REF", "")
    base_ref = os.environ.get("BASE_REF", "")
    findings = os.environ.get("AI_FINDINGS", "")

    if not all([head_ref, base_ref]):
        print("ERROR: HEAD_REF and BASE_REF must be set", file=sys.stderr)
        return EXIT_CONFIG

    print(f"Applying AI-recommended conflict resolutions for PR #{pr_number}")

    try:
        resolutions = parse_resolutions(findings)
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"::error::Failed to parse AI resolutions: {exc}", file=sys.stderr)
        return EXIT_FAILURE

    # Checkout the PR branch and merge the base to recreate conflict state.
    _git(["fetch", "origin", head_ref])
    _git(["checkout", head_ref])
    _git(["fetch", "origin", base_ref])
    _git(["merge", f"origin/{base_ref}"])

    try:
        for res in resolutions:
            apply_resolution(res)
    except ValueError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        _git(["merge", "--abort"])
        return EXIT_FAILURE

    # Verify no remaining conflicts.
    remaining = _git(["diff", "--name-only", "--diff-filter=U"])
    if remaining.stdout.strip():
        print(f"::error::Unresolved conflicts remain: {remaining.stdout.strip()}", file=sys.stderr)
        _git(["merge", "--abort"])
        return EXIT_FAILURE

    _git(["commit", "-m", f"Merge {base_ref} into {head_ref} - AI-resolved conflicts"])

    push_result = subprocess.run(
        [
            "python3",
            _SAFE_PUSH,
            "--repo-root",
            ".",
            "--branch",
            head_ref,
            "--remote",
            "origin",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if push_result.returncode != 0:
        print(
            f"::error::PR #{pr_number}: verified push failed (exit {push_result.returncode})",
            file=sys.stderr,
        )
        return EXIT_FAILURE

    print(f"::notice::PR #{pr_number}: AI-resolved conflicts successfully")
    return EXIT_SUCCESS


if __name__ == "__main__":
    sys.exit(main())
