#!/usr/bin/env python3
"""Advisory check for active execution plans whose tracking issues are closed."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

EXIT_OK = 0
EXIT_CONFIG = 2
DEFAULT_REPO = "rjmurillo/ai-agents"
ISSUE_REF_RE = re.compile(
    r"(?:https://github\.com/[^/\s]+/[^/\s]+/issues/|(?<![A-Za-z0-9/])#)(\d+)"
)


@dataclass(frozen=True, slots=True)
class ActivePlanWarning:
    """An active plan whose known tracking issues are closed."""

    plan_path: str
    issue_numbers: tuple[int, ...]

    def format(self) -> str:
        issues = ", ".join(f"#{number}" for number in self.issue_numbers)
        return (
            f"{self.plan_path}: {issues} closed. Move the plan to completed/ "
            "or abandoned/."
        )


IssueStateLookup = Callable[[int], str | None]


def issue_refs(markdown: str) -> tuple[int, ...]:
    """Return unique issue references from a plan body."""
    return tuple(sorted({int(match.group(1)) for match in ISSUE_REF_RE.finditer(markdown)}))


def active_plan_warnings(
    repo_root: Path,
    *,
    issue_state_lookup: IssueStateLookup,
) -> list[ActivePlanWarning]:
    """Find active plans whose referenced issues all resolve closed."""
    active_dir = repo_root / ".agents" / "plans" / "active"
    if not active_dir.is_dir():
        return []

    warnings: list[ActivePlanWarning] = []
    for plan in sorted(active_dir.glob("*.md")):
        if plan.name == ".gitkeep":
            continue

        issue_numbers = issue_refs(plan.read_text(encoding="utf-8"))
        if not issue_numbers:
            continue

        states = [issue_state_lookup(number) for number in issue_numbers]
        if all(state == "CLOSED" for state in states):
            warnings.append(
                ActivePlanWarning(
                    plan_path=plan.relative_to(repo_root).as_posix(),
                    issue_numbers=issue_numbers,
                )
            )

    return warnings


def gh_issue_state(
    issue_number: int,
    *,
    repo: str,
    env: Mapping[str, str] | None = None,
) -> str | None:
    """Return a GitHub issue state, or None when lookup cannot prove closure."""
    result = subprocess.run(
        [
            "gh",
            "issue",
            "view",
            str(issue_number),
            "--repo",
            repo,
            "--json",
            "state",
            "--jq",
            ".state",
        ],
        env=dict(env) if env is not None else None,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    state = result.stdout.strip().upper()
    return state or None


def validate_active_plan_closeout(repo_root: Path) -> bool:
    """Warn when an active plan can be closed out. Advisory only."""
    repo = os.environ.get("GH_REPO", DEFAULT_REPO)
    warnings = active_plan_warnings(
        repo_root,
        issue_state_lookup=lambda issue: gh_issue_state(issue, repo=repo),
    )
    if not warnings:
        print("[PASS] Active plan closeout advisory found no closed active plans")
        return True

    print("[WARNING] Active execution plans have closed tracking issues:")
    for warning in warnings:
        print(f"  - {warning.format()}")
    print("Note: advisory only. Exit code unchanged.")
    return True


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the advisory check."""
    args = build_parser().parse_args(argv)
    repo_root = args.repo_root.resolve()
    if not repo_root.is_dir():
        print(f"[ERROR] repo root does not exist: {repo_root}", file=sys.stderr)
        return EXIT_CONFIG

    validate_active_plan_closeout(repo_root)
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
