#!/usr/bin/env python3
"""Gate: the HOL AI plugin scanner scores this repository at least 80.

hashgraph-online/awesome-ai-plugins lists a plugin only after its centralized
source scan completes with a normalized score of 80 or more (its
SCANNER_GUIDE.md). That scan clones the default branch and scores the whole
tree, so one new file anywhere can drop the listing below the bar. This gate
runs the same scanner version locally, before a push, and
``.github/workflows/plugin-scanner.yml`` runs the pinned action in CI.

What is scanned: the tree of a named ref (``HEAD`` by default), read into a
throwaway index and written out with ``git checkout-index``, which produces the
files and symlinks a fresh clone has. A directory walk of the checkout would
also score untracked files, caches, and virtualenvs that a clone never has, so
the same commit could pass here and fail in the catalog
(.claude/rules/ci-scripts.md item 9). ``git archive`` is not used: it drops
``export-ignore`` paths such as ``.gitignore`` and ``.gitattributes``, which
the catalog's clone keeps.

Which scanner: ``build/plugin-scanner/uv.lock`` pins ``plugin-scanner`` by hash
to the version the CI action verifies, and ``uv run --frozen`` installs exactly
that. Repository scanner config (``.plugin-scanner.toml``) is deleted from the
exported tree before the scan: run directly, the scanner would apply it, but
the catalog runs with ``trust_repository_policy`` false, so a suppression
would raise only the local score.

Every step shares ``TOTAL_BUDGET_SECONDS``, below the lefthook cap, so a slow
run ends with exit 3 and a reason instead of a lefthook kill. The scanner runs
in its own process group, and a timeout kills the whole group.

Review trigger: when awesome-ai-plugins changes its pinned action commit,
scanner version, or threshold, update the action pin in
``.github/workflows/plugin-scanner.yml``, the version in
``build/plugin-scanner/pyproject.toml`` (then ``uv lock``), and re-measure.

CLI::

    uv run --frozen python scripts/validation/check_plugin_scanner_score.py \
        [--ref HEAD] [--min-score 80]

Exit codes (ADR-035):
    0 - Score at or above the minimum (prints score and examined packages)
    1 - Score below the minimum (prints each check that lost points)
    2 - Config error (not in a git work tree, bad ref, bad argument)
    3 - External error (scanner missing, crashed, timed out, or wrote no report).
        The first run downloads the pinned scanner from PyPI, so an offline
        machine with no cached install fails here; reconnect, or run
        ``uv sync --project build/plugin-scanner --frozen`` once while online.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

DEFAULT_MIN_SCORE = 80
# One deadline covers every step, so the script reports its own exit 3 before
# the 3m lefthook cap kills it (.claude/rules/ci-scripts.md item 19).
TOTAL_BUDGET_SECONDS = 165
GIT_TIMEOUT_SECONDS = 30
# How long a timed-out child's pipes are drained after the kill.
DRAIN_SECONDS = 5
SCANNER_PROJECT = Path("build") / "plugin-scanner"
# The scanner auto-discovers these in the scanned tree when run directly. The
# catalog's action does not trust them, so they are removed before scanning.
REPOSITORY_CONFIG_FILES = (".plugin-scanner.toml", ".codex-plugin-scanner.toml")

_OK = 0
_BELOW = 1
_CONFIG_ERROR = 2
_EXTERNAL_ERROR = 3


class GateError(Exception):
    """A failure that stops the gate before a score exists."""

    def __init__(self, message: str, exit_code: int) -> None:
        super().__init__(message)
        self.exit_code = exit_code


class Deadline:
    """Seconds left of one budget shared by every subprocess."""

    def __init__(self, seconds: float) -> None:
        self._end = time.monotonic() + seconds

    def remaining(self, cap: float | None = None) -> float:
        left = self._end - time.monotonic()
        if left <= 0:
            raise GateError(f"the {TOTAL_BUDGET_SECONDS}s budget ran out", _EXTERNAL_ERROR)
        return left if cap is None else min(left, cap)


def _run(
    args: list[str], cwd: Path, timeout: float, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[bytes]:
    """Run ``args``; on timeout kill its whole process group, not only the child.

    ``subprocess.run`` kills only the direct child, which here is ``uv``; the
    scanner it started would keep running after the gate gave up.
    """
    posix = os.name == "posix"
    with subprocess.Popen(
        args,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=posix,
    ) as proc:
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                if posix:
                    os.killpg(proc.pid, signal.SIGKILL)
                else:
                    proc.kill()
            except ProcessLookupError:
                pass  # the group exited between the timeout and the kill
            # A descendant that left the group (setsid) can hold the pipes
            # open forever; drain briefly, then let the context manager close
            # them and reap the killed child.
            try:
                proc.communicate(timeout=DRAIN_SECONDS)
            except subprocess.TimeoutExpired:
                pass
            raise
    return subprocess.CompletedProcess(args, proc.returncode, stdout, stderr)


def _repo_root(deadline: Deadline) -> Path:
    """Return the work tree root, after confirming cwd is inside it."""
    try:
        result = _run(
            ["git", "rev-parse", "--show-toplevel"],
            Path.cwd(),
            deadline.remaining(GIT_TIMEOUT_SECONDS),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GateError(f"cannot run git: {exc}", _CONFIG_ERROR) from exc
    if result.returncode != 0:
        raise GateError("not inside a git work tree", _CONFIG_ERROR)
    root = Path(result.stdout.decode("utf-8").strip()).resolve()
    if not Path.cwd().resolve().is_relative_to(root):
        raise GateError(f"cwd is outside the resolved work tree {root}", _CONFIG_ERROR)
    return root


def export_ref(repo_root: Path, ref: str, destination: Path, deadline: Deadline) -> None:
    """Write the tree of ``ref`` into ``destination`` as a clone would.

    A private ``GIT_INDEX_FILE`` keeps the real index untouched. Repository
    scanner config is then deleted from the copy (see REPOSITORY_CONFIG_FILES).
    """
    with tempfile.TemporaryDirectory(prefix="plugin-scanner-index-") as index_dir:
        env = {**os.environ, "GIT_INDEX_FILE": str(Path(index_dir) / "index")}
        try:
            read = _run(
                ["git", "read-tree", "--end-of-options", ref],
                repo_root,
                deadline.remaining(GIT_TIMEOUT_SECONDS),
                env,
            )
            if read.returncode != 0:
                detail = read.stderr.decode("utf-8", errors="replace").strip()
                raise GateError(f"cannot export ref {ref!r}: {detail}", _CONFIG_ERROR)
            prefix = f"{destination}{os.sep}"
            write = _run(
                ["git", "checkout-index", "--all", "--force", f"--prefix={prefix}"],
                repo_root,
                deadline.remaining(GIT_TIMEOUT_SECONDS),
                env,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise GateError(f"exporting {ref} failed: {exc}", _EXTERNAL_ERROR) from exc
        if write.returncode != 0:
            detail = write.stderr.decode("utf-8", errors="replace").strip()
            raise GateError(f"cannot write the tree of {ref!r}: {detail}", _EXTERNAL_ERROR)
    for name in REPOSITORY_CONFIG_FILES:
        (destination / name).unlink(missing_ok=True)


def _uv(repo_root: Path, *args: str) -> list[str]:
    return ["uv", *args, "--project", str(repo_root / SCANNER_PROJECT), "--frozen", "--quiet"]


def _tail(stream: bytes) -> str:
    return stream.decode("utf-8", errors="replace").strip()[-2000:]


def run_scanner(repo_root: Path, tree: Path, report: Path, deadline: Deadline) -> None:
    """Install the pinned scanner, run it over ``tree``, and write its JSON report.

    The install is its own step so a slow first download reads as an install
    failure, not as a slow scan.
    """
    scan = [
        *_uv(repo_root, "run", "--no-sync"),
        "plugin-scanner",
        "scan",
        str(tree),
        "--format",
        "json",
        "--output",
        str(report),
        "--fail-on-severity",
        "none",
    ]
    for step, args in (("install", _uv(repo_root, "sync")), ("scan", scan)):
        try:
            result = _run(args, repo_root, deadline.remaining())
        except FileNotFoundError as exc:
            msg = "uv is not installed; see build/plugin-scanner"
            raise GateError(msg, _EXTERNAL_ERROR) from exc
        except subprocess.TimeoutExpired as exc:
            msg = f"scanner {step} exceeded the {TOTAL_BUDGET_SECONDS}s budget"
            raise GateError(msg, _EXTERNAL_ERROR) from exc
        except OSError as exc:
            raise GateError(f"cannot start scanner {step}: {exc}", _EXTERNAL_ERROR) from exc
        if step == "install" and result.returncode != 0:
            msg = f"scanner install failed (exit {result.returncode}): {_tail(result.stderr)}"
            raise GateError(msg, _EXTERNAL_ERROR)
    if not report.is_file():
        msg = f"scanner wrote no report (exit {result.returncode}): {_tail(result.stderr)}"
        raise GateError(msg, _EXTERNAL_ERROR)
    if result.returncode != 0:
        print(
            f"plugin-scanner: scanner exited {result.returncode} but wrote a report: "
            f"{_tail(result.stderr)}",
            file=sys.stderr,
        )


def summarize(report: dict[str, object]) -> tuple[int, int, list[str]]:
    """Return ``(score, packages examined, lines naming each check that lost points)``."""
    score = report.get("score")
    if not isinstance(score, int):
        raise GateError(f"report has no integer score (got {score!r})", _EXTERNAL_ERROR)
    packages = report.get("packages")
    examined = len(packages) if isinstance(packages, list) else 0
    lost: list[str] = []
    categories = report.get("categories")
    for category in categories if isinstance(categories, list) else []:
        if not isinstance(category, dict):
            continue
        for check in category.get("checks") or []:
            if not isinstance(check, dict):
                continue
            points, max_points = check.get("points", 0), check.get("maxPoints", 0)
            if isinstance(points, int) and isinstance(max_points, int) and points < max_points:
                lost.append(
                    f"  -{max_points - points:<2} {category.get('name')}: "
                    f"{check.get('name')} ({check.get('message')})"
                )
    return score, examined, lost


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ref", default="HEAD", help="git ref whose tree is scanned")
    parser.add_argument("--min-score", type=int, default=DEFAULT_MIN_SCORE)
    args = parser.parse_args(argv)
    if not 1 <= args.min_score <= 100:
        parser.error(f"--min-score must be 1 to 100 (got {args.min_score})")
    return args


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parse_args(argv)
    except SystemExit as exc:
        return _CONFIG_ERROR if exc.code else _OK
    started = time.monotonic()
    deadline = Deadline(TOTAL_BUDGET_SECONDS)
    try:
        repo_root = _repo_root(deadline)
        with tempfile.TemporaryDirectory(prefix="plugin-scanner-") as work:
            tree = Path(work) / "tree"
            report_path = Path(work) / "report.json"
            export_ref(repo_root, args.ref, tree, deadline)
            run_scanner(repo_root, tree, report_path, deadline)
            try:
                report = json.loads(report_path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise GateError(f"unreadable scanner report: {exc}", _EXTERNAL_ERROR) from exc
            if not isinstance(report, dict):
                raise GateError("scanner report is not a JSON object", _EXTERNAL_ERROR)
            score, examined, lost = summarize(report)
    except GateError as exc:
        print(f"plugin-scanner: {exc}", file=sys.stderr)
        return exc.exit_code

    elapsed = time.monotonic() - started
    print(
        f"plugin-scanner: score={score} min={args.min_score} margin={score - args.min_score} "
        f"ref={args.ref} packages={examined} elapsed={elapsed:.1f}s"
    )
    # Printed on a pass too: with a thin margin, the next lost check is a red
    # gate, so the reader should see what already costs points.
    stream = sys.stdout if score >= args.min_score else sys.stderr
    if lost:
        print("Checks that lost points:", file=stream)
    for line in lost:
        print(line, file=stream)
    if score >= args.min_score:
        return _OK
    print(
        f"plugin-scanner: score {score} is below {args.min_score}; the "
        "awesome-ai-plugins listing requires 80 (SCANNER_GUIDE.md).",
        file=sys.stderr,
    )
    return _BELOW


if __name__ == "__main__":
    sys.exit(main())
