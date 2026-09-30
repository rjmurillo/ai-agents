#!/usr/bin/env python3
"""Fail on a bypass toggle or advisory workflow step the allowlist does not authorize.

Issue #5636, owner decision D17. Two constructs let a check pass without
proving its contract: an environment toggle with ``SKIP_`` in its name, and a
workflow job or step with ``continue-on-error``. This gate finds every use in
the tracked tree and compares it with
``.agents/governance/bypass-allowlist.json`` (loaded by ``bypass_allowlist.py``).

It fails, exit 1, on:

- a toggle used in tracked source with no ``toggle`` entry;
- a ``continue-on-error`` job or step with no ``continue-on-error`` entry;
- two ``continue-on-error`` steps in one job that share a name, because one
  entry would authorize both;
- an entry that authorizes a current use but whose ``expires`` date has passed,
  or any entry whose ``expires`` date is more than ``MAX_EXPIRY_DAYS`` days out,
  so an exception cannot be made permanent by writing a far date.

An entry that matches no current use is stale. It grants nothing, so it prints a
notice and does not fail.

Where it runs. The pre-PR sequence runs it as the "Bypass Allowlist" gate, and
``tests/validation/test_check_bypass_allowlist_cli.py`` runs it on the whole tree
inside the required "Run Python Tests" context. On a pull request that context
may narrow to the tests the changed files import, so the whole-tree test can wait
until ``merge_group`` or ``push``, which run the full partition. Both callers are
edited by the pull request they judge, so this is a guardrail and a review
prompt, not a control: ADR-101 puts a control on a plane the candidate cannot
edit, and this is not one.

Scope, stated so a clean run is not read as more than it proves. The tracked
paths come from ``git ls-tree`` at ``HEAD``. Their contents are read from the
working tree, so the result carries ``rev=WORKING_TREE``, and a tracked symlink
is skipped rather than followed. A ``SKIP_`` name is found as a string literal in
Python (parsed, not grepped) and as a whole token on any non-comment line of
YAML, shell, PowerShell, TOML, and JSON, so ``$env:SKIP_X``, ``env.SKIP_X``,
``"SKIP_X":`` and ``SKIP_X = 1`` all count. The scan skips ``tests/``, ``docs/``,
``src/`` (generated mirrors), ``templates/``, ``.project-toolkit/``,
``.claude-mem/``, ``.serena/``, and Markdown. It does not find a toggle that is
assembled at run time, a bypass that is not named ``SKIP_``, or a shell
``|| true``. A prose mention in a scanned file needs an allowlist entry. The
allowlist records that an exception exists and is owned. It does not
authenticate who sets the variable at run time: any local user can still set
``SKIP_AUTOFIX=1``.

EXIT CODES (ADR-035):
  0 - every use is authorized and unexpired
  1 - an unlisted use, or an expired entry that authorizes a current use
  2 - the allowlist file is missing a required shape or cannot be read
  3 - the tracked tree could not be read (git failed, a file was unreadable or
      unparseable), so the scan is incomplete
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import stat
import subprocess
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import yaml

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.validation.bypass_allowlist import (  # noqa: E402
    TOGGLE_NAME,
    Allowlist,
    AllowlistError,
    load_allowlist,
)
from scripts.validation.evidence import (  # noqa: E402
    REASON_ENTRIES_UNREADABLE,
    REASON_LISTING_FAILED,
    REASON_VIOLATIONS_FOUND,
    WORKING_TREE,
    CheckOutcome,
    EvidenceState,
)

VALIDATOR = "validate_bypass_allowlist"
SCOPE = "SKIP_ toggles in tracked source and continue-on-error in workflows"
GIT_TIMEOUT_SECONDS = 30
MAX_EXPIRY_DAYS = 370
EXIT_OK, EXIT_LOGIC, EXIT_CONFIG, EXIT_EXTERNAL = 0, 1, 2, 3

_SKIPPED_PREFIXES = (
    "tests/",
    "docs/",
    "src/",
    "templates/",
    ".project-toolkit/",
    ".claude-mem/",
    ".serena/",
    "node_modules/",
)
_TOGGLE_SUFFIXES = (".py", ".yml", ".yaml", ".sh", ".ps1", ".psm1", ".toml", ".json", ".jsonc")
_WORKFLOW_DIR = ".github/workflows/"
_ACTIONS_DIR = ".github/actions/"
_STRING_TOGGLE_RE = re.compile(f"^{TOGGLE_NAME}$")
_TEXT_TOGGLE_RE = re.compile(rf"(?<![A-Za-z0-9_])(?P<name>{TOGGLE_NAME})(?![A-Za-z0-9_])")


@dataclass(frozen=True)
class StepUse:
    """One ``continue-on-error`` job or step found in a workflow."""

    path: str
    job: str
    step: str

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.path, self.job, self.step)


class TreeReadError(Exception):
    """The tracked tree could not be read completely."""

    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(detail)
        self.reason = reason
        self.detail = detail


def tracked_files(repo_root: Path) -> list[str]:
    """Return the paths tracked at ``HEAD``, or raise ``TreeReadError``.

    Read as bytes and decoded with ``os.fsdecode``, so a file name that is not
    valid UTF-8 keeps its exact bytes and still resolves on disk. A lossy decode
    would turn it into a path that does not exist and skip the file unscanned.
    """
    command = ["git", "-C", str(repo_root), "ls-tree", "-r", "-z", "--name-only", "HEAD"]
    try:
        result = subprocess.run(
            command, capture_output=True, timeout=GIT_TIMEOUT_SECONDS, check=False
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise TreeReadError(REASON_LISTING_FAILED, f"git ls-tree could not run: {exc}") from exc
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise TreeReadError(
            REASON_LISTING_FAILED, f"git ls-tree failed: {detail or f'exit {result.returncode}'}"
        )
    return [os.fsdecode(name) for name in result.stdout.split(b"\0") if name]


def _read_text(repo_root: Path, relpath: str) -> str | None:
    """Return the file text, ``None`` when the tracked file is absent from the tree.

    A tracked path deleted in the working tree is not an error: the deletion is
    the change being made. Any other read failure raises ``TreeReadError``.
    """
    path = repo_root / relpath
    try:
        if stat.S_ISLNK(os.lstat(path).st_mode):
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise TreeReadError(REASON_ENTRIES_UNREADABLE, f"{relpath} unreadable: {exc}") from exc


def _is_toggle_scanned(relpath: str) -> bool:
    return relpath.endswith(_TOGGLE_SUFFIXES) and not relpath.startswith(_SKIPPED_PREFIXES)


def _python_toggles(source: str, relpath: str) -> set[str]:
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise TreeReadError(REASON_ENTRIES_UNREADABLE, f"{relpath} does not parse: {exc}") from exc
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and _STRING_TOGGLE_RE.match(node.value)
    }


def _text_toggles(source: str) -> set[str]:
    found: set[str] = set()
    for line in source.splitlines():
        if line.lstrip().startswith("#"):
            continue
        found.update(match.group("name") for match in _TEXT_TOGGLE_RE.finditer(line))
    return found


def find_toggles(repo_root: Path, files: Iterable[str]) -> dict[str, list[str]]:
    """Map each toggle name found to the sorted paths that use it."""
    found: dict[str, list[str]] = {}
    for relpath in files:
        if not _is_toggle_scanned(relpath):
            continue
        source = _read_text(repo_root, relpath)
        if source is None:
            continue
        is_python = relpath.endswith(".py")
        names = _python_toggles(source, relpath) if is_python else _text_toggles(source)
        for name in names:
            found.setdefault(name, []).append(relpath)
    return {name: sorted(paths) for name, paths in found.items()}


def _is_workflow_file(relpath: str) -> bool:
    if not relpath.endswith((".yml", ".yaml")):
        return False
    direct = relpath.startswith(_WORKFLOW_DIR) and "/" not in relpath[len(_WORKFLOW_DIR) :]
    action = relpath.startswith(_ACTIONS_DIR) and relpath.rsplit("/", 1)[-1] in {
        "action.yml",
        "action.yaml",
    }
    return direct or action


def _is_enabled(value: object) -> bool:
    """True unless ``value`` is the literal false: an expression counts as enabled."""
    if isinstance(value, str):
        return value.strip().lower() != "false"
    return bool(value)


def _step_label(step: dict[str, Any], index: int) -> str:
    return str(step.get("name") or step.get("id") or f"#{index}")


def _steps_of(container: object) -> list[dict[str, Any]]:
    steps = container.get("steps") if isinstance(container, dict) else None
    return [s for s in steps if isinstance(s, dict)] if isinstance(steps, list) else []


def _workflow_uses(relpath: str, document: object) -> list[StepUse]:
    if not isinstance(document, dict):
        return []
    found: list[StepUse] = []
    jobs = document.get("jobs")
    containers: dict[str, object] = dict(jobs) if isinstance(jobs, dict) else {}
    if "runs" in document:
        containers["(composite)"] = document["runs"]
    for job, container in containers.items():
        if isinstance(container, dict) and _is_enabled(container.get("continue-on-error", False)):
            found.append(StepUse(relpath, str(job), ""))
        for index, step in enumerate(_steps_of(container)):
            if _is_enabled(step.get("continue-on-error", False)):
                found.append(StepUse(relpath, str(job), _step_label(step, index)))
    return found


def find_advisory_steps(repo_root: Path, files: Iterable[str]) -> list[StepUse]:
    """Return every ``continue-on-error`` job or step in the workflow files."""
    found: list[StepUse] = []
    for relpath in files:
        if not _is_workflow_file(relpath):
            continue
        source = _read_text(repo_root, relpath)
        if source is None:
            continue
        try:
            document = yaml.safe_load(source)
        except yaml.YAMLError as exc:
            raise TreeReadError(REASON_ENTRIES_UNREADABLE, f"{relpath} is not YAML: {exc}") from exc
        found.extend(_workflow_uses(relpath, document))
    return found


def _toggle_problems(
    toggles: dict[str, list[str]], allowlist: Allowlist, today: date
) -> list[str]:
    problems: list[str] = []
    for name, paths in sorted(toggles.items()):
        entry = allowlist.toggles.get(name)
        if entry is None:
            problems.append(f"unlisted toggle {name} used in {', '.join(paths)}")
        elif entry.expires < today:
            problems.append(f"toggle {name} expired {entry.expires} (owner {entry.owner})")
    return problems


def _step_problems(uses: list[StepUse], allowlist: Allowlist, today: date) -> list[str]:
    problems: list[str] = []
    for use in sorted(uses, key=lambda u: u.key):
        label = f"{use.path} job {use.job!r} step {use.step!r}"
        entry = allowlist.steps.get(use.key)
        if entry is None:
            problems.append(f"unlisted continue-on-error at {label}")
        elif entry.expires < today:
            problems.append(f"continue-on-error at {label} expired {entry.expires}")
    return problems


def _duplicate_problems(uses: list[StepUse]) -> list[str]:
    """Name each key shared by more than one ``continue-on-error`` step."""
    seen: dict[tuple[str, str, str], int] = {}
    for use in uses:
        seen[use.key] = seen.get(use.key, 0) + 1
    return [
        f"{count} continue-on-error steps share {key[0]} job {key[1]!r} step {key[2]!r}; "
        "rename them so each needs its own entry"
        for key, count in sorted(seen.items())
        if count > 1
    ]


def _horizon_problems(allowlist: Allowlist, today: date) -> list[str]:
    """Name each entry whose expiry is further out than ``MAX_EXPIRY_DAYS``."""
    limit = today + timedelta(days=MAX_EXPIRY_DAYS)
    message = f"expiry {{}} is more than {MAX_EXPIRY_DAYS} days out ({{}})"
    problems = [
        message.format(t.expires, t.toggle) for t in allowlist.toggles.values() if t.expires > limit
    ]
    problems += [
        message.format(e.expires, e.key) for e in allowlist.steps.values() if e.expires > limit
    ]
    return problems


def stale_entries(
    allowlist: Allowlist, toggles: dict[str, list[str]], uses: list[StepUse]
) -> list[str]:
    """Name every entry that matches no current use."""
    used_steps = {u.key for u in uses}
    stale = [f"toggle {name}" for name in sorted(allowlist.toggles) if name not in toggles]
    stale += [f"step {key}" for key in sorted(allowlist.steps) if key not in used_steps]
    return stale


def evaluate(repo_root: Path, allowlist: Allowlist, today: date) -> tuple[CheckOutcome, list[str]]:
    """Return the typed result and the stale-entry notices."""
    try:
        files = tracked_files(repo_root)
        toggles = find_toggles(repo_root, files)
        uses = find_advisory_steps(repo_root, files)
    except TreeReadError as exc:
        blocked = CheckOutcome.blocked(
            VALIDATOR, reason=exc.reason, scope=SCOPE, detail=exc.detail
        )
        return blocked, []
    problems = (
        _toggle_problems(toggles, allowlist, today)
        + _step_problems(uses, allowlist, today)
        + _duplicate_problems(uses)
        + _horizon_problems(allowlist, today)
    )
    stale = stale_entries(allowlist, toggles, uses)
    examined = len(toggles) + len(uses)
    if problems:
        return (
            CheckOutcome.failed(
                VALIDATOR,
                reason=REASON_VIOLATIONS_FOUND,
                revision=WORKING_TREE,
                scope=SCOPE,
                examined=examined,
                findings=len(problems),
                detail="; ".join(problems),
            ),
            stale,
        )
    detail = f"{len(toggles)} toggle(s) and {len(uses)} continue-on-error step(s), all authorized"
    return (
        CheckOutcome.passed(
            VALIDATOR, revision=WORKING_TREE, scope=SCOPE, examined=examined, detail=detail
        ),
        stale,
    )


def validate_bypass_allowlist(repo_root: Path, today: date | None = None) -> CheckOutcome:
    """Typed entry point for callers that hold a repository root."""
    allowlist = load_allowlist(repo_root)
    outcome, _ = evaluate(repo_root, allowlist, today or date.today())
    return outcome


def _exit_code(outcome: CheckOutcome) -> int:
    if outcome.state is EvidenceState.PASS:
        return EXIT_OK
    return EXIT_LOGIC if outcome.state is EvidenceState.FAIL else EXIT_EXTERNAL


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns an ADR-035 exit code."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo-root", type=Path, default=_PROJECT_ROOT)
    parser.add_argument("--today", type=date.fromisoformat, default=None, help="test seam")
    args = parser.parse_args(argv)
    try:
        allowlist = load_allowlist(args.repo_root)
    except AllowlistError as exc:
        print(f"[FAIL] bypass allowlist is invalid: {json.dumps(str(exc))}", file=sys.stderr)
        return EXIT_CONFIG
    outcome, stale = evaluate(args.repo_root, allowlist, args.today or date.today())
    print(outcome.report_line())
    for notice in stale:
        print(f"[NOTICE] stale allowlist entry, matches no current use: {json.dumps(notice)}")
    return _exit_code(outcome)


if __name__ == "__main__":
    raise SystemExit(main())
