#!/usr/bin/env python3
"""Blocking gate: ruff's ARG rules may report no unused argument outside the baseline.

The gate runs ``ruff check --select ARG --isolated`` with JSON output over the
tracked Python files under ``SCAN_ROOTS``. ruff resolves each name in its own
scope, so a parameter named ``path`` or ``args`` is reported when that function
never reads it, even if another function uses the same name. It reports unused
function, method, class-method, static-method, and lambda arguments
(``ARG001`` to ``ARG005``). ``--isolated`` makes ruff read no configuration
file, so an edit to ``pyproject.toml``, a nested ``ruff.toml``,
``per-file-ignores``, ``exclude``, or ``dummy-variable-rgx`` cannot hide a
finding.

What it does not catch: unused imports, unused functions, classes, variables,
or attributes, and unreachable code. ``check_unreachable_code.py`` covers
unreachable statements; the repo-wide ruff ``F`` rules cover unused imports.
ARG is not in the repo-wide ruff ``select``: adding it there would turn every
listed finding red in the other ruff gates. ruff also exempts these shapes
by design, so the gate never sees them: a stub body (``pass``, ``...``, a
docstring alone, or ``raise NotImplementedError``), a method decorated
``@override``, ``@abstractmethod``, or ``@overload``, a dunder method such as
``__eq__``, and a function that calls ``locals()``.

Each finding is keyed as ``<path>: <code> <argument> in <owner>``, where the
owner is the dotted scope of the function that holds the argument, with no line
number, so an edit elsewhere in a file does not churn the key. The findings
must equal the committed baseline in ``unused_arguments_baseline.txt`` next to
this script. It runs as the pre-push ``python-unused-arguments`` job, the
``Unused Argument Detection`` gate in ``pre_pr.py``, and a step in the
``pytest`` workflow:

- A finding the baseline does not list fails the gate. Use the argument, or
  remove it. A leading underscore marks an argument as intentionally unused.
  A failure prints the line ruff reported for each new finding.
- A baseline entry ruff no longer reports also fails the gate. Delete the line
  in the same change that fixed it.
- The gate ignores noqa comments (``--ignore-noqa``), so a bare noqa comment
  on a ``def`` line cannot hide a finding.
- The escapes that remain are a leading underscore, the ruff exemptions listed
  above, and a baseline line that already exists.

The baseline can only shrink, and the gate enforces it against the merge base.
It reads the baseline as committed at ``git merge-base HEAD <base-ref>``, so
the branch cannot edit what it is held to. This follows the merge-base idea of
``scripts/ci/base_derived_ratchet.py`` (issues #5363 and #6108) but does not
call its ``run()``: that function compares a count, and a count lets a swap
pass (fix one finding, add another). This gate compares the set of keys. Any
baseline line the branch has that the merge base lacks fails. A swap to a
different function or argument fails; a swap that gives the same function the
same argument name cannot occur, because that is the same key. When git reports
a file as renamed since the merge base, the base lines for it follow the new
path, so renaming a file means changing the path on its baseline lines and
nothing else. Renaming a function that holds a baseline line, or moving it to
another class, changes its key: that reads as a new finding, so use or remove
the argument in that change. ``--base-ref`` names the ref; with none, the gate
tries ``refs/remotes/origin/HEAD``, ``origin/main``, then ``main``, and exits 2
when none resolves, as ``base_derived_ratchet.py`` does. Whether the merge base
carries ``check_unused_arguments.py`` decides the first run, as ``introduced_at``
does there: without the script at the merge base this change introduces the
gate and the growth check has nothing to compare. With the script there and the
baseline file gone from its path, the gate fails (exit 1), so moving the
baseline cannot turn the check off.

The scan reads only files git tracks under the scan roots, so an untracked
draft cannot fail a push that CI, checking out the same commit, passes. A
tracked file reads its working-tree content, so an uncommitted edit to a
tracked file can fail a local push that CI would pass.

One total deadline (``TOTAL_DEADLINE_SECONDS``) covers every git and ruff call
from interpreter start, below the 90s lefthook cap, so exit 3 prints before
lefthook kills the job. Environment setup by ``uv run`` before the interpreter
starts is outside that budget.

ruff comes from the interpreter running the gate (``python -P -m ruff``) when
that environment has it, and from ``PATH`` otherwise.

Exit codes (ADR-035):
    0 - Success (findings equal the baseline, no baseline growth)
    1 - Logic error (new finding, stale baseline entry, baseline growth, or the
        baseline missing at the merge base that carries the gate)
    2 - Config error (bad baseline, unreadable source, nothing scanned, repo
        root not a git work tree, git or ruff not installed or failing, no base
        ref resolved)
    3 - External error (git or ruff timed out, the deadline ran out, or the
        merge base could not be read)
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.ci.count_ratchet import git_environment
from scripts.validation.unused_arguments_git import (
    KEY_SEPARATOR,
    Deadline,
    ExternalToolError,
    GateConfigError,
    run_git,
)
from scripts.validation.unused_arguments_growth import (
    DEFAULT_BASE_REFS,
    baseline_growth,
    parse_baseline,
)
from scripts.validation.unused_arguments_owner import owning_function

REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE_RELPATH = Path("scripts/validation/unused_arguments_baseline.txt")

# Canonical sources of the [tool.coverage.run] roots: the .claude/hooks and
# src/claude/hooks trees render from templates/hooks, so each file is scanned
# once at its source. .claude/skills is mostly directory links into
# src/claude/skills, which git lists as symlinks and the scan skips; its real
# tracked files are repo-local skills with no other copy, so they are scanned.
SCAN_ROOTS = ("scripts", "src/claude", "templates/hooks", ".claude/lib", ".claude/skills")

# Generated copies under the scan roots, scanned once at their source. A path
# equal to an entry, or under an entry that ends in "/", is skipped. Test trees
# are skipped by directory name in _is_excluded. Linked files need no entry:
# the scan skips every tracked symlink (mode 120000), which covers the
# .claude/lib links into src/claude/lib. The seven top-level src/claude/lib
# modules below are byte-identical copies of real files in .claude/lib. The
# skill-bundled copies of redact_secrets.py and metrics_writer.py are real
# files in each skill (a skill must be self-contained), so each is scanned and
# one unused argument in them takes one baseline line per copy.
EXCLUDED_PATHS = (
    "src/claude/hooks/",
    "src/claude/lib/ai_review_common/",
    "src/claude/lib/bootstrap.py",
    "src/claude/lib/claude_hook_dispatch.py",
    "src/claude/lib/claude_hook_protocol.py",
    "src/claude/lib/failure_classifier/",
    "src/claude/lib/github_core/",
    "src/claude/lib/hook_dispatch.py",
    "src/claude/lib/hook_dispatch_protocol.py",
    "src/claude/lib/hook_dispatch_timeout.py",
    "src/claude/lib/hook_utilities/",
    "src/claude/lib/output_capture.py",
    "src/claude/lib/shim_loader.py",
    "src/claude/skills/review/scripts/validate_review_marker.py",
)

RUFF_TIMEOUT_SECONDS = 60
# Windows caps a command line near 32K characters; batch the file list.
RUFF_BATCH_SIZE = 200


_ARG_CODE = re.compile(r"ARG\d{3}")
_ARGUMENT_NAME = re.compile(r"`([^`]+)`")


@dataclass(frozen=True)
class ScanResult:
    """Finding keys, the ruff rows behind them, and the number of files passed to ruff."""

    keys: list[str]
    scanned_files: int
    rows: dict[str, list[int]] = field(default_factory=dict)


@dataclass(frozen=True)
class Comparison:
    """Findings outside the baseline and baseline entries with no finding."""

    new: list[str]
    stale: list[str]


def load_baseline(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise GateConfigError(f"cannot read baseline {path}: {exc}") from exc
    return parse_baseline(text)


def compare(findings: Iterable[str], baseline: Iterable[str]) -> Comparison:
    """Compare as multisets: two identical findings need two baseline lines."""
    found = Counter(findings)
    allowed = Counter(baseline)
    return Comparison(
        new=sorted((found - allowed).elements()),
        stale=sorted((allowed - found).elements()),
    )


def _is_excluded(relpath: str) -> bool:
    if "tests" in PurePosixPath(relpath).parts:
        return True
    return any(
        relpath.startswith(entry) if entry.endswith("/") else relpath == entry
        for entry in EXCLUDED_PATHS
    )


def tracked_python_files(
    repo_root: Path, roots: Sequence[str] = SCAN_ROOTS, deadline: Deadline | None = None
) -> list[Path]:
    """Return the tracked regular ``.py`` files under ``roots``, as absolute paths."""
    listing = run_git(
        repo_root, ["ls-files", "-z", "--stage", "--", *roots], deadline or Deadline()
    )
    if listing.returncode != 0:
        raise GateConfigError(
            f"git ls-files failed under {repo_root}: {listing.stderr.strip() or 'no output'}"
        )
    files: list[Path] = []
    for entry in listing.stdout.split("\0"):
        meta, sep, relpath = entry.partition("\t")
        if not sep or not relpath.endswith(".py") or _is_excluded(relpath):
            continue
        # A symlink's target is scanned at its own path when it is in scope.
        # A deletion not yet committed has no file to read.
        if meta.startswith("120000 "):
            continue
        path = repo_root / relpath
        if path.is_file():
            files.append(path)
    return files


def resolve_ruff() -> list[str]:
    """Return the ruff command: this interpreter's copy first, then ``PATH``.

    ``pre-pr-validation`` runs ``uv run --frozen python`` without
    ``--extra dev``, so the interpreter, not ``PATH``, is what the project
    pinned. ``python -m ruff`` finds the copy inside that environment even when
    its ``bin`` directory is not on ``PATH``.
    """
    if importlib.util.find_spec("ruff") is not None:
        # -P keeps a ruff.py in the working directory from shadowing the tool.
        return [sys.executable, "-P", "-m", "ruff"]
    found = shutil.which("ruff")
    if found is None:
        raise GateConfigError("ruff is not installed; run `uv sync --extra dev`")
    return [found]


def _run_ruff(
    repo_root: Path, ruff: Sequence[str], batch: Sequence[Path], deadline: Deadline
) -> list[dict[str, object]]:
    timeout = deadline.timeout_for(RUFF_TIMEOUT_SECONDS, "a ruff batch")
    try:
        completed = subprocess.run(
            [
                *ruff,
                "check",
                "--select",
                "ARG",
                "--output-format",
                "json",
                "--no-cache",
                # Read no ruff config: per-file-ignores, exclude, extend-exclude,
                # dummy-variable-rgx, and a nested ruff.toml would otherwise let
                # a branch edit hide a finding. Explicit paths are always checked.
                "--isolated",
                # A bare noqa comment on a def line would otherwise hide a finding.
                "--ignore-noqa",
                "--",
                *map(str, batch),
            ],
            cwd=repo_root,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            env=git_environment(),
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise ExternalToolError(f"unused-argument gate: ruff timed out after {timeout:g}s") from exc
    except OSError as exc:
        raise GateConfigError(f"cannot run ruff: {exc}") from exc
    # ruff exits 0 with no findings and 1 with findings; anything else is a failure.
    if completed.returncode not in (0, 1):
        raise GateConfigError(
            f"ruff exited {completed.returncode}: {completed.stderr.strip() or 'no output'}"
        )
    try:
        parsed = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise GateConfigError(f"ruff did not print JSON: {exc}") from exc
    if not isinstance(parsed, list):
        raise GateConfigError(f"ruff JSON is not a list: {type(parsed).__name__}")
    findings: list[dict[str, object]] = []
    for item in parsed:
        if not isinstance(item, dict):
            raise GateConfigError(f"ruff JSON holds a non-object entry: {item!r}")
        findings.append(item)
    return findings


def _finding_key(item: dict[str, object], resolved_root: Path) -> str:
    """Return ``<path>: <code> <argument> in <owner>`` for one ruff row."""
    code = item.get("code")
    filename = str(item.get("filename", ""))
    if not (isinstance(code, str) and _ARG_CODE.fullmatch(code)):
        # ruff reports a syntax error as an entry whose code is not an ARG rule.
        raise GateConfigError(f"ruff could not parse {filename}: {item.get('message')}")
    match = _ARGUMENT_NAME.search(str(item.get("message", "")))
    if match is None:
        raise GateConfigError(f"ruff {code} message names no argument: {item.get('message')!r}")
    try:
        relative = Path(filename).resolve().relative_to(resolved_root)
    except ValueError as exc:
        raise GateConfigError(f"ruff reported {filename}, outside {resolved_root}") from exc
    name = match.group(1)
    owner = owning_function(
        _read_source(Path(filename)), filename, _finding_row(item), _finding_column(item), name
    )
    return f"{relative.as_posix()}{KEY_SEPARATOR}{code} {name} in {owner}"


def _read_source(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise GateConfigError(f"cannot read {path} to name an owner: {exc}") from exc


def _location_field(item: dict[str, object], field_name: str) -> int:
    location = item.get("location")
    value = location.get(field_name) if isinstance(location, dict) else None
    return value if isinstance(value, int) else 0


def _finding_row(item: dict[str, object]) -> int:
    return _location_field(item, "row")


def _finding_column(item: dict[str, object]) -> int:
    return _location_field(item, "column")


def scan(repo_root: Path, deadline: Deadline | None = None) -> ScanResult:
    """Run ``ruff check --select ARG`` over the tracked files in scope."""
    deadline = deadline or Deadline()
    ruff = resolve_ruff()
    files = tracked_python_files(repo_root, deadline=deadline)
    if not files:
        raise GateConfigError(f"no tracked Python files under {list(SCAN_ROOTS)}")
    resolved_root = repo_root.resolve()
    keys: list[str] = []
    rows: dict[str, list[int]] = {}
    for start in range(0, len(files), RUFF_BATCH_SIZE):
        for item in _run_ruff(repo_root, ruff, files[start : start + RUFF_BATCH_SIZE], deadline):
            key = _finding_key(item, resolved_root)
            keys.append(key)
            rows.setdefault(key, []).append(_finding_row(item))
    return ScanResult(
        keys=sorted(keys),
        scanned_files=len(files),
        rows={key: sorted(found) for key, found in rows.items()},
    )


def _describe(key: str, result: ScanResult, baseline: Sequence[str]) -> str:
    """Return a new finding as ``path: message`` plus the lines ruff gave."""
    rows = result.rows[key]
    where = ", ".join(str(row) for row in rows)
    allowed = Counter(baseline)[key]
    if allowed:
        return f"{key} (line {where}; the baseline lists {allowed} of {len(rows)})"
    return f"{key} (line {where})"


def _rename_hint(outcome: Comparison) -> str:
    stale_messages = {key.partition(KEY_SEPARATOR)[2] for key in outcome.stale}
    moved = [key for key in outcome.new if key.partition(KEY_SEPARATOR)[2] in stale_messages]
    if not moved:
        return ""
    return (
        " A new finding and a stale line share a rule and argument: if the file moved, "
        "change the path on the stale line to the new path instead of adding a line."
    )


def validate(
    repo_root: Path,
    baseline_path: Path,
    base_ref: str | None = None,
    deadline: Deadline | None = None,
) -> bool:
    """Return True when ruff's ARG findings equal the baseline and it did not grow."""
    deadline = deadline or Deadline()
    baseline = load_baseline(baseline_path)
    result = scan(repo_root, deadline)
    outcome = compare(result.keys, baseline)
    growth = baseline_growth(repo_root, baseline_path, baseline, base_ref, deadline)
    if not outcome.new and not outcome.stale and not growth.added and not growth.error:
        print(
            f"check_unused_arguments: OK. Scanned {result.scanned_files} Python file(s); "
            f"{len(result.keys)} finding(s), all in the baseline of {len(baseline)}; "
            f"{growth.note}."
        )
        return True
    for key in outcome.new:
        print(f"  new unused argument: {_describe(key, result, baseline)}", file=sys.stderr)
    for key in outcome.stale:
        print(f"  stale baseline entry: {key}", file=sys.stderr)
    for key in growth.added:
        print(f"  baseline line not in the merge base: {key}", file=sys.stderr)
    if growth.error:
        print(f"  {growth.error}", file=sys.stderr)
    print(
        f"\ncheck_unused_arguments: {len(outcome.new)} new finding(s), "
        f"{len(outcome.stale)} stale baseline line(s), {len(growth.added)} added baseline "
        f"line(s) across {result.scanned_files} scanned file(s). Use or remove each new "
        f"argument; never add it to the baseline. Delete each stale line from "
        f"{baseline_path.name}.{_rename_hint(outcome)} {growth.note}.",
        file=sys.stderr,
    )
    return False


def validate_unused_arguments(repo_root: Path) -> bool:
    """pre_pr gate entry point. Fails closed when the scan cannot run."""
    try:
        return validate(repo_root, repo_root / BASELINE_RELPATH)
    except (GateConfigError, ExternalToolError) as exc:
        print(f"error: unused-argument gate did not run: {exc}", file=sys.stderr)
        return False


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument(
        "--baseline", type=Path, default=None, help=f"default: <repo-root>/{BASELINE_RELPATH}"
    )
    parser.add_argument(
        "--base-ref",
        default=None,
        help="ref whose merge base with HEAD holds the baseline ceiling "
        f"(default: first that resolves of {', '.join(DEFAULT_BASE_REFS)})",
    )
    args = parser.parse_args(argv)
    repo_root = args.repo_root.resolve()
    baseline = args.baseline if args.baseline is not None else repo_root / BASELINE_RELPATH
    try:
        return 0 if validate(repo_root, baseline, args.base_ref) else 1
    except GateConfigError as exc:
        print(f"error: unused-argument gate did not run: {exc}", file=sys.stderr)
        return 2
    except ExternalToolError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
