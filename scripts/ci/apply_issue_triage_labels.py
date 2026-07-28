#!/usr/bin/env python3
"""Apply labels for the AI issue triage workflow."""

from __future__ import annotations

import json
import os
import re
import subprocess

LABEL_PATTERN = re.compile(r"^(?=.{1,50}$)[A-Za-z0-9](?:[A-Za-z0-9 _.-]*[A-Za-z0-9])?$")
PRIORITY_PATTERN = re.compile(r"^P[0-4]$")


def _run_gh(args: list[str], *, discard_stderr: bool = False) -> subprocess.CompletedProcess[str]:
    stderr = subprocess.DEVNULL if discard_stderr else subprocess.STDOUT
    return subprocess.run(
        ["gh", *args],
        check=False,
        stdout=subprocess.PIPE,
        stderr=stderr,
        text=True,
    )


def _existing_label_names(label: str) -> list[str]:
    result = _run_gh(
        ["label", "list", "--search", label, "--json", "name", "-q", ".[].name"],
        discard_stderr=True,
    )
    return [line for line in result.stdout.splitlines() if line]


def _label_exists(label: str) -> bool:
    existing_lower = {name.lower() for name in _existing_label_names(label)}
    return label.lower() in existing_lower


def _parse_labels(raw_labels: str) -> list[str]:
    if not raw_labels or raw_labels == "[]":
        return []
    try:
        labels = json.loads(raw_labels)
    except json.JSONDecodeError as exc:
        print(f"WARNING: Failed to parse labels JSON: {exc}")
        return []
    if isinstance(labels, str):
        return [labels]
    if isinstance(labels, list):
        return [str(label) for label in labels]
    return []


def _ensure_label(label: str, description: str, color: str | None = None) -> bool:
    if _label_exists(label):
        return True

    print(f"Creating label: {label}")
    args = ["label", "create", label, "--description", description]
    if color is not None:
        args.extend(["--color", color])
    result = _run_gh(args)
    return result.returncode == 0


def _add_label(issue_number: str, label: str) -> bool:
    print(f"Adding label: {label}")
    result = _run_gh(["issue", "edit", issue_number, "--add-label", label])
    return result.returncode == 0


def apply_labels(*, issue_number: str, labels_json: str, priority: str) -> int:
    failed_labels: list[str] = []
    failed_creates: list[str] = []

    for label in _parse_labels(labels_json):
        if not LABEL_PATTERN.fullmatch(label):
            print(f"WARNING: Skipping invalid label: {label}")
            continue

        if not _ensure_label(label, "Auto-created by AI triage"):
            print(f"WARNING: Failed to create label: {label}")
            failed_creates.append(label)

        if not _add_label(issue_number, label):
            print(f"WARNING: Failed to add label '{label}' to issue #{issue_number}")
            failed_labels.append(label)

    if PRIORITY_PATTERN.fullmatch(priority):
        priority_label = f"priority:{priority}"
        if not _ensure_label(priority_label, "Priority level", "FFA500"):
            print(f"WARNING: Failed to create priority label: {priority_label}")
            failed_creates.append(priority_label)

        if not _add_label(issue_number, priority_label):
            print(f"WARNING: Failed to add priority label '{priority_label}'")
            failed_labels.append(priority_label)

    if failed_labels or failed_creates:
        print("")
        print("=== LABEL OPERATIONS SUMMARY ===")
        if failed_creates:
            print(f"Failed to create labels: {', '.join(failed_creates)}")
        if failed_labels:
            print(f"Failed to apply labels: {', '.join(failed_labels)}")
        print("===============================")

    return 0


def main(argv: list[str] | None = None) -> int:
    if argv:
        return 2
    return apply_labels(
        issue_number=os.environ.get("ISSUE_NUMBER", ""),
        labels_json=os.environ.get("LABELS_JSON", ""),
        priority=os.environ.get("PRIORITY", ""),
    )


if __name__ == "__main__":
    raise SystemExit(main())
