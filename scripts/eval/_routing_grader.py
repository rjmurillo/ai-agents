"""Deterministic grader and control checks for routing benchmark scenarios (issue #5425).

Grading order follows the issue's "Grading priority": executable ground truth
only. `grade` never reads `Scenario.judge_dimensions`, so no model judge can
override a failing deterministic criterion.

`grade(scenario, workdir)` does four things on a scratch copy of `workdir`
(the driver's directory is never modified):

1. diff `workdir` against the scenario's `initial/` state;
2. flag every changed path outside `allowed_paths` or inside `forbidden_paths`;
3. require every `expected_changed_paths` glob to match a changed path;
4. overlay the grader-only `hidden/` files and run the validation commands.

Validation commands run without a shell. The first argv element `python` is
replaced by `sys.executable`, the environment is a small allowlist, and each
command has a timeout. The commands execute driver-written code with the
grader's own privileges. Nothing here isolates that code at the operating
system level: the environment allowlist limits inherited secrets, and the
scratch copy limits what the code finds in the working directory. Callers run
this on benchmark scratch directories only, inside whatever sandbox already
contains the driver.

Glob semantics: `fnmatch.fnmatchcase` on posix relative paths. `*` also
matches `/`, so `pkg/*.py` covers `pkg/sub/mod.py`.
"""

from __future__ import annotations

import fnmatch
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from _routing_scenario import (
    Category,
    RoutingCorpusError,
    Scenario,
    Validation,
    fixture_files,
)

OUTPUT_LIMIT_CHARS = 4000
OVERLAY_NAMES: tuple[str, ...] = ("known_good", "known_bad")
_IGNORED_PARTS = frozenset({"__pycache__"})
_ENV_ALLOWLIST = ("PATH", "SYSTEMROOT", "TMPDIR", "TEMP", "TMP")


class Verdict(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"


@dataclass(frozen=True, slots=True)
class CommandResult:
    argv: tuple[str, ...]
    returncode: int
    timed_out: bool
    output: str

    @property
    def passed(self) -> bool:
        return self.returncode == 0 and not self.timed_out


@dataclass(frozen=True, slots=True)
class GradeResult:
    verdict: Verdict
    changed_paths: tuple[str, ...]
    scope_violations: tuple[str, ...]
    missing_expected: tuple[str, ...]
    commands: tuple[CommandResult, ...]

    @property
    def output(self) -> str:
        return "\n".join(result.output for result in self.commands)


@dataclass(frozen=True, slots=True)
class ControlCheck:
    name: str
    ok: bool
    detail: str


@dataclass(frozen=True, slots=True)
class ControlReport:
    scenario_id: str
    checks: tuple[ControlCheck, ...]

    @property
    def ok(self) -> bool:
        return all(check.ok for check in self.checks)


def _is_ignored(relative: Path) -> bool:
    return bool(_IGNORED_PARTS & set(relative.parts)) or relative.suffix == ".pyc"


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _symlinks(root: Path) -> tuple[str, ...]:
    """Relative posix paths of every symlink under `root`, without following any."""
    found: list[str] = []
    for current, directories, files in os.walk(root, followlinks=False):
        base = Path(current)
        for name in (*directories, *files):
            if (base / name).is_symlink():
                found.append((base / name).relative_to(root).as_posix())
    return tuple(sorted(found))


def manifest(root: Path) -> dict[str, str]:
    """Map relative posix path to sha256 for every regular file under `root`.

    A symlink is never read: it maps to the literal digest `symlink`, so a link
    to a host file cannot pull that file into the grade.
    """
    result: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if _is_ignored(relative):
            continue
        if path.is_symlink():
            result[relative.as_posix()] = "symlink"
        elif path.is_file():
            result[relative.as_posix()] = _digest(path)
    return result


def fixture_manifest(directory: Path) -> dict[str, str]:
    """Like `manifest`, for a `.fixture`-suffixed directory (suffix stripped)."""
    return {logical: _digest(path) for logical, path in fixture_files(directory).items()}


def _write_overlay(directory: Path, destination: Path) -> None:
    for logical, source in fixture_files(directory).items():
        target = destination / logical
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)


def materialize(scenario: Scenario, destination: Path, *overlays: str) -> None:
    """Write `initial/`, then each named overlay, into an empty `destination`.

    This is the scenario's reset procedure: every run starts from a fresh copy.
    """
    unknown = [name for name in overlays if name not in OVERLAY_NAMES]
    if unknown:
        raise ValueError(f"unknown overlay {unknown}; expected one of {list(OVERLAY_NAMES)}")
    if destination.exists() and any(destination.iterdir()):
        raise ValueError(f"{destination}: materialize needs an empty or absent directory")
    destination.mkdir(parents=True, exist_ok=True)
    _write_overlay(scenario.fixture_dir("initial"), destination)
    for name in overlays:
        _write_overlay(scenario.fixture_dir(name), destination)


def changed_paths(
    scenario: Scenario, workdir: Path, ignore: frozenset[str] = frozenset()
) -> tuple[str, ...]:
    """Paths added, modified, or deleted in `workdir` relative to `initial/`.

    `ignore` names paths that are expected run artifacts, such as a plan file.
    """
    before = fixture_manifest(scenario.fixture_dir("initial"))
    after = manifest(workdir)
    return tuple(
        sorted(
            path
            for path in before.keys() | after.keys()
            if before.get(path) != after.get(path) and path not in ignore
        )
    )


def _matches(path: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def scope_violations(scenario: Scenario, changed: Sequence[str]) -> tuple[str, ...]:
    """Changed paths that are forbidden or fall outside the allowed scope."""
    return tuple(
        path
        for path in changed
        if _matches(path, scenario.forbidden_paths) or not _matches(path, scenario.allowed_paths)
    )


def missing_expected(scenario: Scenario, changed: Sequence[str]) -> tuple[str, ...]:
    """Expected-change globs that no changed path matches."""
    return tuple(
        pattern
        for pattern in scenario.expected_changed_paths
        if not any(fnmatch.fnmatchcase(path, pattern) for path in changed)
    )


def _environment(workdir: Path) -> dict[str, str]:
    env = {key: os.environ[key] for key in _ENV_ALLOWLIST if key in os.environ}
    env["PYTHONPATH"] = str(workdir)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def _run_command(argv: tuple[str, ...], workdir: Path, timeout: int) -> CommandResult:
    real = [sys.executable, *argv[1:]]
    try:
        completed = subprocess.run(
            real,
            cwd=workdir,
            env=_environment(workdir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return CommandResult(argv, -1, True, f"timed out after {timeout}s")
    combined = (completed.stdout or "") + (completed.stderr or "")
    return CommandResult(argv, completed.returncode, False, combined[-OUTPUT_LIMIT_CHARS:])


def run_validation(validation: Validation, workdir: Path) -> tuple[CommandResult, ...]:
    """Run every command in `validation` inside `workdir`, in order."""
    return tuple(
        _run_command(argv, workdir, validation.timeout_seconds) for argv in validation.commands
    )


def grade(scenario: Scenario, workdir: Path, ignore: frozenset[str] = frozenset()) -> GradeResult:
    """Grade `workdir` against `scenario`. `workdir` itself is left untouched.

    `ignore` excludes expected run artifacts from the changed-path diff.

    The scratch copy keeps symlinks as links (it never follows one). The scope
    verdict and the validation run both read that copy, so they see the same
    files even if a driver is still writing. A link anywhere in the copy is a
    scope violation and ends
    grading before hidden files or commands are added. Checking the copy, not
    the source, closes the window in which a still-running driver could add a
    link between a check and a copy.
    """
    with tempfile.TemporaryDirectory(prefix="routing-grade-") as scratch_name:
        scratch = Path(scratch_name) / "work"
        shutil.copytree(
            workdir,
            scratch,
            symlinks=True,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        changed = changed_paths(scenario, scratch, ignore)
        violations = scope_violations(scenario, changed)
        missing = missing_expected(scenario, changed)
        links = _symlinks(scratch)
        if links:
            found = tuple(f"symlink:{path}" for path in links)
            return GradeResult(Verdict.FAIL, changed, (*violations, *found), missing, ())
        _write_overlay(scenario.fixture_dir("hidden"), scratch)
        results = run_validation(scenario.validation, scratch)
    passed = not violations and not missing and all(result.passed for result in results)
    return GradeResult(
        Verdict.PASS if passed else Verdict.FAIL, changed, violations, missing, results
    )


def grade_overlay(scenario: Scenario, *overlays: str) -> GradeResult:
    """Materialize `initial/` plus `overlays` in a scratch directory and grade it."""
    with tempfile.TemporaryDirectory(prefix="routing-state-") as scratch_name:
        workdir = Path(scratch_name) / "work"
        materialize(scenario, workdir, *overlays)
        return grade(scenario, workdir)


def _self_check_passes(scenario: Scenario, overlay: str | None) -> bool:
    if scenario.self_check is None:
        raise RoutingCorpusError(f"{scenario.scenario_id}: no self_check defined")
    with tempfile.TemporaryDirectory(prefix="routing-self-") as scratch_name:
        workdir = Path(scratch_name) / "work"
        materialize(scenario, workdir, *([overlay] if overlay else []))
        return all(result.passed for result in run_validation(scenario.self_check, workdir))


def _reset_reproducible(scenario: Scenario) -> ControlCheck:
    with tempfile.TemporaryDirectory(prefix="routing-reset-") as scratch_name:
        first = Path(scratch_name) / "first"
        second = Path(scratch_name) / "second"
        materialize(scenario, first)
        materialize(scenario, second)
        ok = (
            manifest(first) == manifest(second) == fixture_manifest(scenario.fixture_dir("initial"))
        )
    return ControlCheck("reset_reproducible", ok, "two fresh copies match initial/")


def _plausible_checks(scenario: Scenario, bad: GradeResult) -> list[ControlCheck]:
    finding = scenario.reviewer_finding
    if finding is None:
        raise RoutingCorpusError(f"{scenario.scenario_id}: no reviewer_finding defined")
    return [
        ControlCheck(
            "known_bad_passes_self_check",
            _self_check_passes(scenario, "known_bad"),
            "the plausible-but-wrong state passes the driver-visible check",
        ),
        ControlCheck(
            "known_good_passes_self_check",
            _self_check_passes(scenario, "known_good"),
            "the known-good state passes the driver-visible check",
        ),
        ControlCheck(
            "known_bad_evidence_matches_finding",
            finding.evidence_marker in bad.output,
            f"grader output carries reviewer finding marker {finding.evidence_marker!r}",
        ),
    ]


def verify_controls(scenario: Scenario) -> ControlReport:
    """Prove the grader discriminates: known-good PASS, known-bad FAIL, baseline FAIL."""
    good = grade_overlay(scenario, "known_good")
    bad = grade_overlay(scenario, "known_bad")
    baseline = grade_overlay(scenario)
    checks = [
        ControlCheck(
            "known_good_passes", good.verdict is Verdict.PASS, f"verdict {good.verdict.value}"
        ),
        ControlCheck(
            "known_bad_fails", bad.verdict is Verdict.FAIL, f"verdict {bad.verdict.value}"
        ),
        ControlCheck(
            "baseline_fails", baseline.verdict is Verdict.FAIL, f"verdict {baseline.verdict.value}"
        ),
        _reset_reproducible(scenario),
    ]
    if scenario.category is Category.SCOPE_EXPANSION:
        checks.append(
            ControlCheck(
                "known_bad_flags_scope_violation",
                bool(bad.scope_violations),
                f"scope violations {list(bad.scope_violations)}",
            )
        )
    if scenario.category is Category.PLAUSIBLE_BUT_WRONG:
        checks += _plausible_checks(scenario, bad)
    return ControlReport(scenario.scenario_id, tuple(checks))
