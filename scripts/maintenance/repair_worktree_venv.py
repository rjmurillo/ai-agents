#!/usr/bin/env python3
"""Repair stale uv virtual-environment shebangs after moving a git worktree.

When ``uv`` creates ``.venv`` it writes each launcher script (``.venv/bin/*`` on
POSIX, ``.venv/Scripts/*`` on Windows) with an absolute-path shebang naming the
interpreter, for example ``#!/path/to/wt/.venv/bin/python``. Moving the worktree
does not rewrite those shebangs, so the first line still names the OLD path.
Direct calls such as ``.venv/bin/pytest`` then fail before Python starts with
"bad interpreter: No such file or directory". ``uv run python -m pytest`` keeps
working because uv resolves the environment again.

This tool scans the launcher directory, reads each script's first-line shebang,
and flags any absolute interpreter path that is NOT rooted at the current
worktree root. On a stale hit it either recreates the environment via
``uv sync --frozen --extra dev --reinstall`` (default) or, in ``--check`` mode,
prints one exact repair command and exits non-zero without mutating anything.

USAGE:
  # Recreate the environment if any shebang is stale (default):
  uv run python scripts/maintenance/repair_worktree_venv.py

  # Report only; print the repair command and exit non-zero on a stale hit:
  uv run python scripts/maintenance/repair_worktree_venv.py --check

  # Machine-readable output:
  uv run python scripts/maintenance/repair_worktree_venv.py --json

EXIT CODES (ADR-035):
  0 - No stale shebangs (or a default-mode repair cleared them)
  1 - Stale shebangs found in --check mode (repair needed, nothing mutated)
  2 - Configuration error: not inside a git worktree (or git unavailable)
  3 - External error: `uv sync` failed, or it returned success yet a default-mode
      repair left the shebangs stale (the external repair did not take effect)

See: ADR-035 Exit Code Standardization
Related: Issue #3170 (moving a worktree leaves the uv shebangs stale), #3097
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

_GIT_TIMEOUT_SECONDS = 30
_UV_SYNC_TIMEOUT_SECONDS = 600
_REPAIR_COMMAND = "uv sync --frozen --extra dev --reinstall"
_LAUNCHER_DIR_NAMES = ("bin", "Scripts")


@dataclass(frozen=True)
class StaleShebang:
    """A launcher whose shebang names an interpreter not under ``{root}/.venv``."""

    path: Path
    interpreter: str


@dataclass
class RepairReport:
    """The scan result for one worktree's virtual environment."""

    worktree_root: str
    venv_present: bool
    stale: list[StaleShebang] = field(default_factory=list)


def repair_command() -> str:
    """Return the exact command that recreates the environment."""
    return _REPAIR_COMMAND


def worktree_root() -> Path:
    """Return the current worktree's top-level directory via git."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=_GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"git rev-parse failed: {exc}") from exc
    if result.returncode != 0:
        raise RuntimeError(f"git rev-parse failed: {result.stderr.strip()}")
    return Path(result.stdout.strip())


def find_launcher_dir(venv: Path) -> Path | None:
    """Return the launcher directory (``bin`` or ``Scripts``) that exists."""
    for name in _LAUNCHER_DIR_NAMES:
        candidate = venv / name
        if candidate.is_dir():
            return candidate
    return None


def read_shebang(path: Path) -> str | None:
    """Return the first-line shebang, or None for binaries and unreadable files.

    Launcher directories mix text scripts with ELF binaries and symlinks. A
    binary's leading bytes are not valid text, and a broken symlink cannot be
    opened; both are skipped rather than treated as launchers.
    """
    try:
        with path.open("rb") as handle:
            first = handle.readline(4096)
    except OSError:
        return None
    if not first.startswith(b"#!"):
        return None
    try:
        return first.decode("utf-8").rstrip("\r\n")
    except UnicodeDecodeError:
        return None


def interpreter_of_shebang(shebang: str) -> str | None:
    """Return the absolute interpreter path a shebang names, else None.

    The ``env`` indirection form (``#!/usr/bin/env python``) resolves the
    interpreter through PATH, so it survives a move and is never stale.
    """
    if not shebang.startswith("#!"):
        return None
    tokens = shebang[len("#!") :].strip().split()
    if not tokens:
        return None
    interpreter = tokens[0]
    if Path(interpreter).name == "env":
        return None
    return interpreter


def is_stale(interpreter: str, root: Path) -> bool:
    """Return True when an absolute interpreter path is not under ``root/.venv``.

    A shebang is stale when the interpreter is not rooted at the current
    worktree's ``.venv`` directory. This catches both interpreters outside
    ``root`` entirely *and* interpreters under ``root`` but in an obsolete
    ``.venv`` layout (e.g., after moving from ``/data/wt`` to ``/data``, a
    shebang naming ``/data/wt/.venv/bin/python`` is still under ``/data`` but
    is no longer the correct ``/data/.venv`` location).

    Compares raw paths (no ``resolve``) so a symlinked root component does not
    normalize differently from uv's literal shebang and false-flag a correct
    environment. Relative interpreters are PATH-resolved and never stale.
    """
    interpreter_path = Path(interpreter)
    if not interpreter_path.is_absolute():
        return False
    expected_venv = root / ".venv"
    return not interpreter_path.is_relative_to(expected_venv)


def scan_launcher_dir(launcher_dir: Path, root: Path) -> list[StaleShebang]:
    """Return the stale launchers under ``launcher_dir`` for worktree ``root``."""
    stale: list[StaleShebang] = []
    for entry in sorted(launcher_dir.iterdir()):
        if not entry.is_file():
            continue
        shebang = read_shebang(entry)
        if shebang is None:
            continue
        interpreter = interpreter_of_shebang(shebang)
        if interpreter is None:
            continue
        if is_stale(interpreter, root):
            stale.append(StaleShebang(path=entry, interpreter=interpreter))
    return stale


def build_report(root: Path) -> RepairReport:
    """Scan ``root``'s ``.venv`` and build the repair plan (no mutation here)."""
    launcher_dir = find_launcher_dir(root / ".venv")
    if launcher_dir is None:
        return RepairReport(worktree_root=str(root), venv_present=False)
    stale = scan_launcher_dir(launcher_dir, root)
    return RepairReport(worktree_root=str(root), venv_present=True, stale=stale)


def run_repair(root: Path) -> None:
    """Recreate the environment via ``uv sync --frozen --extra dev --reinstall``.

    Raises on failure. The command has three parts and each is load-bearing:

    * ``--reinstall`` is what actually fixes the move. After a worktree move the
      packages are all present, so a plain ``uv sync`` (or ``--frozen`` alone)
      sees nothing to do and leaves the stale absolute-path launcher shebangs
      untouched. ``--reinstall`` recreates the entry-point launchers, rewriting
      the shebang to the current interpreter path.
    * ``--extra dev`` keeps the dev tooling (pytest, ruff, mypy) in the repaired
      ``.venv``. Reinstalling without it prunes the dev-only launchers, which are
      exactly the ones a developer moved the worktree to run.
    * ``--frozen`` reproduces the locked environment from ``uv.lock`` without
      re-resolving, matching the canonical setup (CONTRIBUTING.md) that the
      pre-push gate and CI use.

    uv's own progress output is captured and forwarded to stderr, never this
    process's stdout. The script reserves stdout for its own output (the human
    report or the ``--json`` payload), so uv chatter cannot prepend log lines and
    corrupt the JSON a ``--json`` consumer parses.
    """
    argv = _REPAIR_COMMAND.split()
    try:
        result = subprocess.run(
            argv,
            check=False,
            cwd=root,
            timeout=_UV_SYNC_TIMEOUT_SECONDS,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            encoding="utf-8",
            errors="replace",
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"{_REPAIR_COMMAND} in {root} failed: {exc}") from exc
    if result.stdout:
        print(result.stdout, file=sys.stderr, end="")
    if result.returncode != 0:
        raise RuntimeError(f"{_REPAIR_COMMAND} in {root} exited {result.returncode}")


def format_report(report: RepairReport, *, check: bool) -> str:
    """Human-readable summary of the scan or repair result."""
    if not report.venv_present:
        return f"venv repair: no .venv under {report.worktree_root}; nothing to check."
    if not report.stale:
        return f"venv repair: OK, all shebangs rooted at {report.worktree_root}."
    lines = [f"venv repair: {len(report.stale)} stale shebang(s) under {report.worktree_root}:"]
    for hit in report.stale:
        lines.append(f"    - {hit.path} -> {hit.interpreter}")
    if check:
        lines.append(f"  Repair with: {repair_command()}")
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Detect and repair stale uv venv shebangs after moving a worktree."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Report only: print the repair command and exit non-zero on a stale hit.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the report as JSON instead of human-readable text.",
    )
    return parser.parse_args(argv)


def _report_to_json(report: RepairReport) -> str:
    """Serialize the report, rendering Path fields as strings.

    When stale shebangs are present the payload also carries ``repair_command``
    so a machine consumer of ``--check --json`` gets the same actionable command
    the human ``--check`` path prints as ``Repair with: ...``. A clean report
    omits the field: there is nothing to repair.
    """
    payload = asdict(report)
    payload["stale"] = [
        {"path": str(hit.path), "interpreter": hit.interpreter} for hit in report.stale
    ]
    if report.stale:
        payload["repair_command"] = repair_command()
    return json.dumps(payload, indent=2)


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns an ADR-035 exit code."""
    args = parse_args(argv)
    try:
        root = worktree_root()
    except RuntimeError as exc:
        # worktree_root() fails when we are not inside a git worktree (or git is
        # unavailable): a usage/configuration error per ADR-035 -> exit 2.
        # Nothing was mutated.
        print(f"error: {exc}", file=sys.stderr)
        return 2

    report = build_report(root)
    if report.stale and not args.check:
        try:
            run_repair(root)
        except RuntimeError as exc:
            # run_repair() shells out to `uv sync`; a subprocess or tool failure
            # is an external-service error per ADR-035 -> exit 3, not a config
            # error. This lets automation distinguish "not in a git repo" (2)
            # from "the repair tool failed" (3).
            print(f"error: {exc}", file=sys.stderr)
            return 3
        report = build_report(root)  # Rescan to confirm repair

    if args.json:
        print(_report_to_json(report))
    else:
        print(format_report(report, check=args.check))
    if report.stale:
        # --check mode: staleness is the "repair needed" signal; nothing was
        # mutated, so surface it as exit 1 (validation: work remains).
        if args.check:
            return 1
        # Default mode: a repair ran (the only way to reach here with stale set)
        # and `uv sync` reported success, yet the rescan still finds stale
        # shebangs. The external repair did not take effect, so classify it with
        # the run_repair failure path as an external error -> exit 3.
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
