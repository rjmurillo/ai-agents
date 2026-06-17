#!/usr/bin/env python3
"""Flag any issue or PR that carries more than one ``priority:*`` label.

Issue #2623, part 1: different bots and agents stamp priority independently
with no reconciliation step, so issues accumulate contradictory labels (for
example ``priority:P1`` and ``priority:P2`` on the same issue). A label query
for "what is P1" then becomes unanswerable. This validator detects the
condition so triage can reconcile it; the prevention side (making the labels
mutually exclusive at write time) lives in
``.claude/skills/github/scripts/issue/set_issue_labels.py``.

The ``priority:`` prefix and the ``P0..P3`` values match the canonical
producer ``.claude/skills/github/scripts/issue/set_issue_labels.py``, which
writes ``priority:{P0|P1|P2|P3}`` via its
``VALID_PRIORITIES = ("P0", "P1", "P2", "P3")`` constant and
``f"priority:{args.priority}"`` formatting. The ``PRIORITY_PREFIX``
constant is ``"priority:"`` in both files.

Stricter/looser/different than canonical
-----------------------------------------
This validator is intentionally **looser** on the suffix: it matches any label
whose name starts with ``"priority:"`` (case-insensitive), not only the
``P0..P3`` values listed in ``VALID_PRIORITIES``. Reason: a malformed or
legacy priority label (for example ``priority:high`` stamped by a non-canonical
tool) must still be counted and flagged when it collides with another priority
label. Restricting to ``P0..P3`` would silently miss those collisions.

Exit codes (ADR-035):
    0 - at most one priority label present (clean)
    1 - more than one priority label present (logic failure: contradiction)
    2 - usage/configuration error (missing required argument)
    3 - external error (gh unavailable / API failure / not authenticated)

stdout carries a single human-readable status line, for example
``OK: issue #2623 has 1 priority label (priority:P2)`` or
``FAIL: issue #2623 has 2 priority labels: priority:P1, priority:P2``.
"""

from __future__ import annotations

import argparse
import json
import subprocess

PRIORITY_PREFIX = "priority:"
# Bounded timeout on the outbound gh call (release-it.md: every outbound call
# sets an explicit timeout). A validator must not hang on a slow API.
GH_TIMEOUT_SECONDS = 15

EXIT_OK = 0
EXIT_DUAL = 1
EXIT_CONFIG = 2
EXIT_EXTERNAL = 3


def find_priority_labels(label_names: list[str]) -> list[str]:
    """Return the ``priority:*`` labels in ``label_names``, sorted.

    Matches on the ``priority:`` prefix, case-insensitively, so a label
    stamped as ``Priority:P1`` by a non-canonical tool is still detected.
    Sorting makes the returned order (and any message built from it)
    deterministic regardless of input order.
    """
    matches = [
        name
        for name in label_names
        if isinstance(name, str)
        and name.lower().startswith(PRIORITY_PREFIX)
    ]
    return sorted(matches)


def evaluate(label_names: list[str], target: str) -> tuple[int, str]:
    """Return (exit_code, status_line) for a label set on ``target``."""
    priority_labels = find_priority_labels(label_names)
    count = len(priority_labels)
    if count <= 1:
        label_word = "priority label" if count == 1 else "priority labels"
        suffix = f" ({priority_labels[0]})" if count == 1 else ""
        return EXIT_OK, f"OK: {target} has {count} {label_word}{suffix}"
    joined = ", ".join(priority_labels)
    return (
        EXIT_DUAL,
        f"FAIL: {target} has {count} priority labels: {joined}",
    )


def _run_gh_view(kind: str, number: int) -> subprocess.CompletedProcess[str]:
    """Fetch an issue or PR's labels via gh. ``kind`` is 'issue' or 'pr'."""
    cmd = ["gh", kind, "view", str(number), "--json", "labels"]
    return subprocess.run(
        cmd,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=GH_TIMEOUT_SECONDS,
        check=False,
    )


def _fetch_labels(kind: str, number: int) -> tuple[int, list[str] | None, str]:
    """Return (exit_code_on_error, labels_or_None, error_status).

    On success returns (EXIT_OK, [names], ""). On any gh failure returns
    (EXIT_EXTERNAL, None, status) so the caller fails closed.
    """
    try:
        proc = _run_gh_view(kind, number)
    except FileNotFoundError:
        return EXIT_EXTERNAL, None, "FAIL: gh CLI not found"
    except subprocess.TimeoutExpired:
        return (
            EXIT_EXTERNAL,
            None,
            f"FAIL: gh {kind} view timed out after {GH_TIMEOUT_SECONDS}s",
        )

    if proc.returncode != 0:
        return EXIT_EXTERNAL, None, f"FAIL: gh {kind} view failed (exit {proc.returncode})"

    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return EXIT_EXTERNAL, None, "FAIL: gh returned unparseable JSON"

    labels_field = payload.get("labels")
    labels = labels_field if isinstance(labels_field, list) else []
    names = [
        item.get("name")
        for item in labels
        if isinstance(item, dict) and item.get("name")
    ]
    return EXIT_OK, names, ""


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Exit 1 when an issue/PR carries more than one priority:* label."
        )
    )
    parser.add_argument(
        "--labels",
        nargs="*",
        default=None,
        help="Label names to check directly (no network).",
    )
    parser.add_argument(
        "--issue", type=int, default=0, help="Issue number to fetch via gh."
    )
    parser.add_argument(
        "--pr", type=int, default=0, help="PR number to fetch via gh."
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.labels is not None:
        exit_code, status = evaluate(args.labels, "labels")
        print(status)
        return exit_code

    if args.issue:
        kind, number = "issue", args.issue
    elif args.pr:
        kind, number = "pr", args.pr
    else:
        print("FAIL: provide --labels, --issue, or --pr")
        return EXIT_CONFIG

    err_code, names, err_status = _fetch_labels(kind, number)
    if names is None:
        print(err_status)
        return err_code

    exit_code, status = evaluate(names, f"{kind} #{number}")
    print(status)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
