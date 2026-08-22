#!/usr/bin/env python3
"""Add or remove the advisory needs-split PR label."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

CONFIG_ERROR = 2
LABEL = "needs-split"


def _run_gh(args: list[str], *, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["gh", *args],
        check=False,
        input=input_text,
        stdout=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _label_endpoint(repository: str, pr_number: str) -> str:
    return f"repos/{repository}/issues/{pr_number}/labels"


def _existing_labels(repository: str, pr_number: str) -> tuple[int, list[str]]:
    result = _run_gh(
        [
            "api",
            _label_endpoint(repository, pr_number),
            "--jq",
            ".[].name",
        ]
    )
    labels = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return result.returncode, labels


def add_label(repository: str, pr_number: str) -> int:
    exit_code, labels = _existing_labels(repository, pr_number)
    if exit_code != 0:
        print(
            f"::warning::Could not fetch PR labels (exit code: {exit_code}); "
            f"skipping advisory '{LABEL}' label.",
            file=sys.stderr,
        )
        return 0
    if LABEL in labels:
        print(f"PR #{pr_number} already has '{LABEL}' label")
        return 0
    result = _run_gh(
        [
            "api",
            "-X",
            "POST",
            "-H",
            "Accept: application/vnd.github+json",
            _label_endpoint(repository, pr_number),
            "--input",
            "-",
        ],
        input_text=f'{{"labels":["{LABEL}"]}}',
    )
    if result.returncode != 0:
        print(
            f"::warning::Failed to add advisory '{LABEL}' label "
            f"(exit code: {result.returncode}). Cosmetic only; this label is "
            "advisory and carries no enforcement.",
            file=sys.stderr,
        )
        return 0
    print(f"Added '{LABEL}' label to PR #{pr_number}")
    return 0


def remove_label(repository: str, pr_number: str) -> int:
    exit_code, labels = _existing_labels(repository, pr_number)
    if exit_code != 0:
        print(
            f"::warning::Could not fetch PR labels (exit code: {exit_code}); "
            f"skipping advisory '{LABEL}' cleanup.",
            file=sys.stderr,
        )
        return 0
    if LABEL not in labels:
        return 0
    result = _run_gh(
        [
            "api",
            "-X",
            "DELETE",
            "-H",
            "Accept: application/vnd.github+json",
            f"{_label_endpoint(repository, pr_number)}/{LABEL}",
        ]
    )
    if result.returncode != 0:
        print(
            f"::warning::Failed to remove advisory '{LABEL}' label "
            f"(exit code: {result.returncode}). Cosmetic only; this label is "
            "advisory and carries no enforcement.",
            file=sys.stderr,
        )
        return 0
    print(f"Removed '{LABEL}' label from PR #{pr_number}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("add", "remove"), required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    pr_number = os.environ.get("PR_NUMBER", "")
    if args.mode == "add":
        return add_label(repository, pr_number)
    return remove_label(repository, pr_number)


if __name__ == "__main__":
    raise SystemExit(main())
