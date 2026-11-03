#!/usr/bin/env python3
"""Blocking gate: vulture may report no dead code outside the baseline.

vulture runs with the ``[tool.vulture]`` table in ``pyproject.toml``. Each
finding is keyed as ``<path>: <message>``, with no line number, so an edit
elsewhere in a file does not churn the key. The findings must equal the
committed baseline in ``dead_code_baseline.txt`` next to this script.
It runs as the pre-push ``python-dead-code`` job, the ``Dead Code Detection``
gate in ``pre_pr.py``, and a step in the ``pytest`` workflow:

- A finding the baseline does not list fails the gate. Remove the dead code,
  or, for a false positive, use the name so vulture sees it.
- A baseline entry vulture no longer reports also fails the gate, so the
  baseline can only shrink. Delete the line in the same change that fixed it.

``tests/validation/test_check_dead_code.py`` pins the baseline length, so an
added line fails until a reviewer sees that constant move.

Exit codes (ADR-035):
    0 - Success (findings equal the baseline)
    1 - Logic error (new finding or stale baseline entry)
    2 - Config error (bad baseline or config, unreadable source, nothing scanned)
    3 - External error (vulture is not installed)
"""

from __future__ import annotations

import argparse
import importlib
import sys
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE_RELPATH = Path("scripts/validation/dead_code_baseline.txt")
KEY_SEPARATOR = ": "


class GateConfigError(RuntimeError):
    """Raised when the gate cannot trust its inputs."""


class VultureMissingError(RuntimeError):
    """Raised when the vulture package cannot be imported."""


@dataclass(frozen=True)
class ScanResult:
    """Finding keys plus the number of first-party modules vulture read."""

    keys: list[str]
    scanned_files: int


@dataclass(frozen=True)
class Comparison:
    """Findings outside the baseline and baseline entries with no finding."""

    new: list[str]
    stale: list[str]


def parse_baseline(text: str) -> list[str]:
    """Return baseline keys, skipping blank lines and ``#`` comments."""
    keys: list[str] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        path, sep, message = line.partition(KEY_SEPARATOR)
        if not sep or not path or not message:
            raise GateConfigError(f"baseline line {lineno} is not '<path>: <message>': {raw!r}")
        keys.append(line)
    return keys


def load_baseline(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
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


def _load_vulture() -> ModuleType:
    try:
        for name in ("vulture.config", "vulture.core"):
            importlib.import_module(name)
    except ImportError as exc:
        raise VultureMissingError("vulture is not installed; run `uv sync --extra dev`") from exc
    return sys.modules["vulture"]


def scan(repo_root: Path) -> ScanResult:
    """Run vulture with the repository's pyproject config."""
    vulture = _load_vulture()
    pyproject = repo_root / "pyproject.toml"
    if not pyproject.is_file():
        raise GateConfigError(f"pyproject.toml not found under {repo_root}")
    try:
        config = vulture.config.make_config(["--config", str(pyproject)])
    except vulture.config.InputError as exc:
        raise GateConfigError(f"invalid [tool.vulture] config: {exc}") from exc
    if not config["paths"]:
        raise GateConfigError("[tool.vulture] lists no paths")
    scan_roots = [repo_root / path for path in config["paths"]]
    missing = [str(path) for path in scan_roots if not path.exists()]
    if missing:
        # vulture answers a missing path with sys.exit, which would escape as
        # this gate's exit 1 and read as a finding, not a bad config.
        raise GateConfigError(f"[tool.vulture] paths do not exist: {missing}")

    scanned: list[Path] = []
    checker = vulture.core.Vulture(
        ignore_names=config["ignore_names"],
        ignore_decorators=config["ignore_decorators"],
    )
    vulture_scan = checker.scan

    def counting_scan(code: str, filename: str | Path = "") -> None:
        # scavenge() also scans vulture's bundled whitelists by relative path;
        # only the first-party modules count toward the examined total.
        if Path(filename).is_absolute():
            scanned.append(Path(filename))
        vulture_scan(code, filename=filename)

    checker.scan = counting_scan
    checker.scavenge([str(path) for path in scan_roots], exclude=config["exclude"])
    if checker.exit_code != vulture.core.ExitCode.NoDeadCode:
        raise GateConfigError("vulture could not parse or read a source file; see the error above")
    if not scanned:
        raise GateConfigError("vulture scanned zero Python files; check [tool.vulture] paths")

    keys = []
    for item in checker.get_unused_code(min_confidence=config["min_confidence"]):
        relative = Path(item.filename).resolve().relative_to(repo_root.resolve())
        keys.append(f"{relative.as_posix()}{KEY_SEPARATOR}{item.message}")
    return ScanResult(keys=keys, scanned_files=len(scanned))


def validate(repo_root: Path, baseline_path: Path) -> bool:
    """Return True when vulture's findings equal the baseline."""
    baseline = load_baseline(baseline_path)
    result = scan(repo_root)
    outcome = compare(result.keys, baseline)
    if not outcome.new and not outcome.stale:
        print(
            f"check_dead_code: OK. Scanned {result.scanned_files} Python file(s); "
            f"{len(result.keys)} finding(s), all in the baseline of {len(baseline)}."
        )
        return True
    for key in outcome.new:
        print(f"  new dead code: {key}", file=sys.stderr)
    for key in outcome.stale:
        print(f"  stale baseline entry: {key}", file=sys.stderr)
    print(
        f"\ncheck_dead_code: {len(outcome.new)} new finding(s) and "
        f"{len(outcome.stale)} stale baseline line(s) across "
        f"{result.scanned_files} scanned file(s). Remove new dead code; never add it "
        f"to the baseline. Delete each stale line from {baseline_path.name}.",
        file=sys.stderr,
    )
    return False


def validate_dead_code(repo_root: Path) -> bool:
    """pre_pr gate entry point. Fails closed when the scan cannot run."""
    try:
        return validate(repo_root, repo_root / BASELINE_RELPATH)
    except (GateConfigError, VultureMissingError) as exc:
        print(f"error: dead-code gate did not run: {exc}", file=sys.stderr)
        return False


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument(
        "--baseline", type=Path, default=None, help=f"default: <repo-root>/{BASELINE_RELPATH}"
    )
    args = parser.parse_args(argv)
    repo_root = args.repo_root.resolve()
    baseline = args.baseline if args.baseline is not None else repo_root / BASELINE_RELPATH
    try:
        return 0 if validate(repo_root, baseline) else 1
    except GateConfigError as exc:
        print(f"error: dead-code gate did not run: {exc}", file=sys.stderr)
        return 2
    except VultureMissingError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
