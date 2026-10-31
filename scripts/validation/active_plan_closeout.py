#!/usr/bin/env python3
"""Advisory check for active execution plans whose tracking issues are closed."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import threading
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# The typed contract, package path (evidence.py states why).
from scripts.validation.evidence import (  # noqa: E402
    REASON_ADVISORY_FINDINGS,
    REASON_LOOKUP_FAILED,
    REASON_MALFORMED_OUTPUT,
    REASON_TIMEOUT,
    REASON_TOOL_ABSENT,
    WORKING_TREE,
    CheckOutcome,
)

_VALIDATOR = "validate_active_plan_closeout"
_SCOPE = "tracking issues of active execution plans"

EXIT_OK = 0
EXIT_CONFIG = 2
DEFAULT_REPO = "rjmurillo/ai-agents"
GH_TIMEOUT_SECONDS = 30
# Concurrent ``gh issue view`` calls. Each call is a network round trip, so the
# serial loop cost one round trip per reference (issue #6734). Eight keeps the
# burst well under GitHub's secondary rate limits.
MAX_LOOKUP_WORKERS = 8
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
        return f"{self.plan_path}: {issues} closed. Move the plan to completed/ or abandoned/."


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
    active_dir = repo_root / ".project-toolkit" / "plans" / "active"
    if not active_dir.is_dir():
        return []

    warnings: list[ActivePlanWarning] = []
    for plan in sorted(active_dir.glob("*.md")):
        issue_numbers = issue_refs(plan.read_text(encoding="utf-8"))
        if not issue_numbers:
            continue

        states = [_normalize_state(issue_state_lookup(number)) for number in issue_numbers]
        for issue_number, state in zip(issue_numbers, states, strict=True):
            if state is not None and state not in KNOWN_STATES:
                _print_lookup_advisory(
                    issue_number,
                    REASON_MALFORMED_OUTPUT,
                    f"unrecognized state {state} for #{issue_number} in "
                    f"{plan.relative_to(repo_root).as_posix()}",
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


def _print_lookup_advisory(issue_number: int, reason: str, message: str) -> None:
    """Print one typed line for a lookup that returned no usable state.

    Every path that makes ``gh_issue_state`` return ``None`` names a reason
    code, so a grep counts how many lookups failed and why. ``BLOCKED`` covers a
    precondition that was absent or an answer that never came; a state that was
    unreadable is ``UNKNOWN``.
    """
    detail = f"could not inspect #{issue_number}: {message}"
    if reason == REASON_MALFORMED_OUTPUT:
        outcome = CheckOutcome.unknown(_VALIDATOR, reason=reason, scope=_SCOPE, detail=detail)
    else:
        outcome = CheckOutcome.blocked(_VALIDATOR, reason=reason, scope=_SCOPE, detail=detail)
    _emit_advisory(outcome.report_line())


_advisory_sink = threading.local()


def _emit_advisory(line: str) -> None:
    """Print an advisory line, or buffer it when a prefetch worker is capturing.

    A worker thread buffers its lines so the main thread can replay them in
    plan order. Output then matches the serial run whatever order the lookups
    finish in.
    """
    buffer: list[str] | None = getattr(_advisory_sink, "lines", None)
    if buffer is None:
        print(line)
    else:
        buffer.append(line)


_REPO_RE = re.compile(r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$")


def gh_issue_state(
    issue_number: int,
    *,
    repo: str,
    env: Mapping[str, str] | None = None,
) -> str | None:
    """Return a GitHub issue state, or None when lookup cannot prove closure."""
    match = _REPO_RE.fullmatch(repo)
    if match is None:
        _print_lookup_advisory(issue_number, REASON_LOOKUP_FAILED, f"invalid repo format: {repo!r}")
        return None
    validated_repo = match.group(0)
    command = [
        "gh",
        "issue",
        "view",
        str(issue_number),
        "--repo",
        validated_repo,
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
        _print_lookup_advisory(issue_number, REASON_TOOL_ABSENT, "gh executable unavailable")
        return None
    except subprocess.TimeoutExpired:
        _print_lookup_advisory(issue_number, REASON_TIMEOUT, "gh lookup timed out")
        return None
    except OSError as exc:
        _print_lookup_advisory(issue_number, REASON_LOOKUP_FAILED, f"gh lookup failed: {exc}")
        return None

    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()
        suffix = f": {detail[0]}" if detail else ""
        _print_lookup_advisory(issue_number, REASON_LOOKUP_FAILED, f"gh lookup failed{suffix}")
        return None

    state = _normalize_state(result.stdout)
    if state is None:
        _print_lookup_advisory(issue_number, REASON_MALFORMED_OUTPUT, "gh returned no state")
    return state


@dataclass(frozen=True, slots=True)
class _FetchedState:
    """One prefetched lookup: its state, buffered advisory lines, and any error."""

    state: str | None
    advisories: tuple[str, ...]
    error: Exception | None = None


def _fetch_buffered(issue_number: int, repo: str) -> _FetchedState:
    """Run one lookup on a worker thread, capturing its advisory lines."""
    lines: list[str] = []
    _advisory_sink.lines = lines
    try:
        state = gh_issue_state(issue_number, repo=repo)
    except Exception as exc:  # Replayed on the main thread, as the serial run raised it.
        return _FetchedState(None, tuple(lines), exc)
    finally:
        del _advisory_sink.lines
    return _FetchedState(state, tuple(lines))


def _active_plan_issue_numbers(repo_root: Path) -> list[int]:
    """Return the unique issue numbers referenced by the active plans, sorted."""
    active_dir = repo_root / ".project-toolkit" / "plans" / "active"
    if not active_dir.is_dir():
        return []
    numbers: set[int] = set()
    try:
        for plan in active_dir.glob("*.md"):
            numbers.update(issue_refs(plan.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        # Prefetch is an optimization. Let the serial pass hit and report the error.
        return []
    return sorted(numbers)


def _prefetch_states(repo_root: Path, repo: str) -> dict[int, _FetchedState]:
    """Look up every distinct referenced issue concurrently, once each."""
    numbers = _active_plan_issue_numbers(repo_root)
    if len(numbers) < 2:
        return {}
    with ThreadPoolExecutor(max_workers=min(MAX_LOOKUP_WORKERS, len(numbers))) as pool:
        fetched = pool.map(lambda number: _fetch_buffered(number, repo), numbers)
        return dict(zip(numbers, fetched, strict=True))


def _findings_detail(plans: int, unresolved: int, lookups: int) -> str:
    detail = f"{plans} active plan(s) have only closed tracking issues"
    if unresolved:
        detail += f"; {unresolved} of {lookups} lookup(s) returned no usable state"
    return detail


def validate_active_plan_closeout(repo_root: Path, *, repo: str = DEFAULT_REPO) -> CheckOutcome:
    """Warn when an active plan can be closed out. Advisory only.

    The result is typed (issue #5636). A closeable plan is ``FAIL`` with reason
    ``advisory.findings``. A lookup that returned no usable state, or a state
    outside ``KNOWN_STATES``, makes the clean verdict unprovable, so the run is
    ``BLOCKED`` with reason ``lookup.failed``: before this change an
    unreachable ``gh`` and "every plan still open" printed the same ``[PASS]``.
    ``pre_pr_policy`` licenses both pairs by name, so the push is still not
    blocked.
    """
    lookups = 0
    unresolved = 0
    prefetched = _prefetch_states(repo_root, repo)

    def counted_lookup(issue: int) -> str | None:
        nonlocal lookups, unresolved
        lookups += 1
        fetched = prefetched.get(issue)
        if fetched is None:
            state = gh_issue_state(issue, repo=repo)
        else:
            # Replay what the serial lookup would have printed, at the same point.
            for line in fetched.advisories:
                print(line)
            if fetched.error is not None:
                raise fetched.error
            state = fetched.state
        if _normalize_state(state) not in KNOWN_STATES:
            unresolved += 1
        return state

    warnings = active_plan_warnings(repo_root, issue_state_lookup=counted_lookup)
    if warnings:
        print("[WARNING] Active execution plans have closed tracking issues:")
        for warning in warnings:
            print(f"  - {warning.format()}")
        print("Note: advisory only. Exit code unchanged.")
        return CheckOutcome.failed(
            _VALIDATOR,
            reason=REASON_ADVISORY_FINDINGS,
            revision=WORKING_TREE,
            scope=_SCOPE,
            examined=lookups,
            findings=len(warnings),
            detail=_findings_detail(len(warnings), unresolved, lookups),
        )
    if unresolved:
        print(
            "[WARNING] Active plan closeout advisory: "
            f"{unresolved} of {lookups} issue lookup(s) returned no usable state"
        )
        return CheckOutcome.blocked(
            _VALIDATOR,
            reason=REASON_LOOKUP_FAILED,
            scope=_SCOPE,
            detail=f"{unresolved} of {lookups} issue lookup(s) returned no usable state",
        )
    print("[PASS] Active plan closeout advisory: no active plans with all tracking issues closed")
    return CheckOutcome.passed(_VALIDATOR, revision=WORKING_TREE, scope=_SCOPE, examined=lookups)


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
