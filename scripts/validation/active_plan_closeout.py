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
GH_TIMEOUT_SECONDS = 30
TERMINAL_STATES = frozenset({"CLOSED", "MERGED"})
NONTERMINAL_STATES = frozenset({"OPEN", "DRAFT", "LOCKED"})
KNOWN_STATES = TERMINAL_STATES | NONTERMINAL_STATES
ISSUE_REF_RE = re.compile(
    r"(?:https://github\.com/[^/\s]+/[^/\s]+/(?:issues|pull)/|(?<![A-Za-z0-9/])#)(\d+)"
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

        states = [_normalize_state(issue_state_lookup(number)) for number in issue_numbers]
        for issue_number, state in zip(issue_numbers, states, strict=True):
            if state is not None and state not in KNOWN_STATES:
                print(
                    "[WARNING] Active plan closeout advisory saw "
                    f"unrecognized state {state} for #{issue_number} in "
                    f"{plan.relative_to(repo_root).as_posix()}"
                )

        if states and all(state in TERMINAL_STATES for state in states):
            warnings.append(
                ActivePlanWarning(
                    plan_path=plan.relative_to(repo_root).as_posix(),
                    issue_numbers=issue_numbers,
                )
            )

    return warnings


def _normalize_state(state: str | None) -> str | None:
    if state is None:
        return None
    normalized = state.strip().upper()
    return normalized or None


def _print_lookup_advisory(issue_number: int, message: str) -> None:
    print(
        "[WARNING] Active plan closeout advisory could not inspect "
        f"#{issue_number}: {message}"
    )


_REPO_RE = re.compile(r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$")


def gh_issue_state(
    issue_number: int,
    *,
    repo: str,
    env: Mapping[str, str] | None = None,
) -> str | None:
    """Return a GitHub issue state, or None when lookup cannot prove closure."""
    if not _REPO_RE.fullmatch(repo):
        _print_lookup_advisory(issue_number, f"invalid repo format: {repo!r}")
        return None
    command = [
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
    ]
    try:
        result = subprocess.run(
            command,
            env=dict(env) if env is not None else None,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
            timeout=GH_TIMEOUT_SECONDS,
        )
    except FileNotFoundError:
        _print_lookup_advisory(issue_number, "gh executable unavailable")
        return None
    except subprocess.TimeoutExpired:
        _print_lookup_advisory(issue_number, "gh lookup timed out")
        return None
    except OSError as exc:
        _print_lookup_advisory(issue_number, f"gh lookup failed: {exc}")
        return None

    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()
        suffix = f": {detail[0]}" if detail else ""
        _print_lookup_advisory(issue_number, f"gh lookup failed{suffix}")
        return None

    state = _normalize_state(result.stdout)
    if state is None:
        _print_lookup_advisory(issue_number, "gh returned no state")
    return state


def validate_active_plan_closeout(repo_root: Path) -> bool:
    """Warn when an active plan can be closed out. Advisory only."""
    repo = os.environ.get("GH_REPO", DEFAULT_REPO)
    warnings = active_plan_warnings(
        repo_root,
        issue_state_lookup=lambda issue: gh_issue_state(issue, repo=repo),
    )
    if not warnings:
        print(
            "[PASS] Active plan closeout advisory: "
            "no active plans with all tracking issues closed"
        )
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
