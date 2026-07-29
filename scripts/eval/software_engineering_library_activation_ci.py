#!/usr/bin/env python3
"""CI wrappers for the software-engineering-library activation gate."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

SCENARIOS = (
    "tests/evals/rule-scenarios/clean-architecture.json",
    "tests/evals/rule-scenarios/domain-driven-design.json",
    "tests/evals/rule-scenarios/enterprise-patterns.json",
    "tests/evals/rule-scenarios/refactoring.json",
    "tests/evals/rule-scenarios/release-it.json",
    "tests/evals/rule-scenarios/philosophy-of-software-design.json",
    "tests/evals/rule-scenarios/data-intensive-applications.json",
    "tests/evals/rule-scenarios/working-with-legacy-code.json",
)

RESULTS_PATH = Path("activation-results.json")
STATE_PATH = Path(".eval-state/software-engineering-library-activation-state.json")
REPORT_PATH = Path("activation-gate-report.md")
THRESHOLD_REPORT_PATH = Path("activation-threshold-report.json")
LABEL = "software-engineering-library-activation"
OWNER_LABEL = "agent-qa"
AUTOMATED_LABEL = "automated"


def _numeric_or(value: str, fallback: str) -> str:
    """Return ``value`` when it is a decimal integer, else ``fallback``.

    A run id and an issue number are numbers, and both reach argv. A value
    beginning with a dash would be read by the receiving parser as a flag
    rather than as a value, so enforcing the contract they already have
    removes the argument-injection primitive rather than escaping it.

    The ASCII test is not redundant with ``isdigit``. ``"\u0661\u0662\u0663".isdigit()``
    is ``True`` and ``int()`` accepts it, so a bare ``isdigit`` guard forwards a
    string that is a number to Python and a different token to every other
    program that receives it.
    """
    return value if value.isascii() and value.isdigit() else fallback


def run_id() -> str:
    """The workflow run id, refused unless it is a plain number."""
    return _numeric_or(os.environ.get("GITHUB_RUN_ID", ""), "unknown")


def run(command: Sequence[str], *, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=check, text=True)


def live_eval() -> int:
    eval_command = [
        "uv",
        "run",
        "python",
        "scripts/eval/eval-rule-activation.py",
        "--output",
        str(RESULTS_PATH),
        "--scenarios",
        *SCENARIOS,
    ]
    eval_exit = run(eval_command).returncode
    if eval_exit in {2, 4}:
        return eval_exit
    if not RESULTS_PATH.is_file() or RESULTS_PATH.stat().st_size == 0:
        return eval_exit

    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    gate_command = [
        "uv",
        "run",
        "python",
        "scripts/eval/software_engineering_library_activation_gate.py",
        "--results",
        str(RESULTS_PATH),
        "--state",
        str(STATE_PATH),
        "--output-state",
        str(STATE_PATH),
        "--report",
        str(REPORT_PATH),
        "--threshold-report",
        str(THRESHOLD_REPORT_PATH),
        "--run-id",
        run_id(),
        "--fail-on-threshold",
    ]
    gate_exit = run(gate_command).returncode
    if eval_exit == 3:
        return eval_exit
    return gate_exit


def workflow_url() -> str:
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    repository = os.environ.get("GITHUB_REPOSITORY", "rjmurillo/ai-agents")
    return f"{server}/{repository}/actions/runs/{run_id()}"


def open_issue_number() -> str:
    result = subprocess.run(
        [
            "gh",
            "issue",
            "list",
            "--label",
            LABEL,
            "--state",
            "open",
            "--json",
            "number",
            "--jq",
            ".[0].number // \"\"",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def write_body(path: Path, body: str) -> None:
    path.write_text(body.strip() + "\n", encoding="utf-8")


def create_issue() -> int:
    issue_body = Path("issue-body.md")
    write_body(
        issue_body,
        f"""
        ## Software Engineering Library Activation Threshold

        The weekly ADR-088 activation gate failed. Review the uploaded
        `activation-gate-report.md` artifact and open a restoration PR if any
        reference reached the consecutive activation failure threshold.

        Restoration PR policy:
        - Restore the failing book reference to the always-on rule surface, or
          strengthen the skill trigger and scenario coverage.
        - Include the latest activation gate report in the PR body.
        - The PR must pass this workflow before merge.

        Workflow run: {workflow_url()}
        """,
    )
    return run(
        [
            "gh",
            "issue",
            "create",
            "--title",
            "software-engineering-library activation rollback threshold",
            "--body-file",
            str(issue_body),
            "--label",
            f"{LABEL},{OWNER_LABEL},{AUTOMATED_LABEL}",
        ]
    ).returncode


def comment_issue(issue_number: str) -> int:
    comment_body = Path("comment-body.md")
    write_body(
        comment_body,
        f"""
        The weekly ADR-088 activation gate failed again.

        Review the latest uploaded activation artifacts and keep or open the
        restoration PR until this workflow passes.

        Workflow run: {workflow_url()}
        """,
    )
    return run(
        ["gh", "issue", "comment", issue_number, "--body-file", str(comment_body)]
    ).returncode


def alert_issue() -> int:
    issue_number = _numeric_or(open_issue_number(), "")
    if issue_number:
        return comment_issue(issue_number)
    return create_issue()


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="CI helpers for software-engineering-library activation."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("live-eval", help="Run live eval and activation gate.")
    subparsers.add_parser("alert-issue", help="Create or update rollback alert issue.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    if args.command == "live-eval":
        return live_eval()
    if args.command == "alert-issue":
        return alert_issue()
    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    sys.exit(main())
