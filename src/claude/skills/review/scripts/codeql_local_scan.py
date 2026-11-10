"""Guarded local CodeQL scan: source 2 of the ADR-041 amendment 2026-11-09.

Rules file: ``.project-toolkit/analysis/adr-041-review-caller-rules.md``. The local
scan is a fallback for the time before a pull request exists. It runs only when
every guard holds. A failed guard returns ``SKIPPED (<guard>)`` and runs nothing:

1. The platform supports a process group kill (not Windows).
2. ``.codeql/`` and the CodeQL CLI exist. Absence is a skip, never inferred from an
   exit code. The wrapper exits 0 when ``.codeql/`` is missing, so exit 0 alone
   proves nothing.
3. The working tree is clean, and the database cache was built at the reviewed
   HEAD. The cache is keyed on HEAD and config only, so an uncommitted change
   makes a cached result stale.
4. The language set is explicit and non-empty. The caller maps the diff's file
   types to ``--languages``.
5. The documented wrapper runs with ``--operation quick --ci``, a 60 second limit,
   and an environment of ``PATH``, ``HOME``, ``LANG``, ``TMPDIR`` only. On timeout
   the whole process group is killed.
6. A SARIF file exists for each requested language and was written after the run
   started. With that evidence: exit 0 and zero results is ``CLEAN``; exit 1 and at
   least one result is ``FINDINGS`` (``--ci`` exits 1 on findings, ADR-035). Any
   mismatch is ``SKIPPED (exit and results disagree)``, because an uncaught error
   also exits 1. Exit 0 with the wrapper's ``[SKIP]`` marker, exit 2 or 3, any other
   exit code, a signal, or a timeout is ``SKIPPED``.

Stricter/looser/different than canonical
========================================
The wrapper is ``codeql-scan/scripts/invoke_codeql_scan.py``. Its ``quick``
operation maps to the delegate's ``--use-cache``. This module does not call the
delegate directly, so the wrapper's own checks still run. The wrapper's
``--languages`` choices are ``python`` and ``actions``; the caller passes only those.

Standard library only: this module ships in the plugin tree.
"""

from __future__ import annotations

import json
import os
import platform
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

LOCAL_TIMEOUT_SECONDS = 60
ENV_ALLOWLIST = ("PATH", "HOME", "LANG", "TMPDIR")
SKIP_MARKER = "[SKIP]"

_CLI_RELATIVE = Path(".codeql") / "cli" / "codeql"
_CACHE_METADATA = Path(".codeql") / "db" / ".cache-metadata.json"
_RESULTS_DIR = Path(".codeql") / "results"
_WRAPPER_ARGS = ("--operation", "quick", "--ci", "--languages")


@dataclass(frozen=True)
class LocalScanOutcome:
    """Result of the guarded local scan.

    ``outcome`` is ``CLEAN``, ``FINDINGS``, or ``SKIPPED``. ``reason`` is set for
    ``SKIPPED`` and is a fixed string. ``results`` holds the raw SARIF results for
    ``FINDINGS`` only.
    """

    outcome: str
    reason: str = ""
    languages: tuple[str, ...] = ()
    results: list[Any] = field(default_factory=list)


def _skipped(reason: str, languages: tuple[str, ...] = ()) -> LocalScanOutcome:
    return LocalScanOutcome("SKIPPED", reason=reason, languages=languages)


def scan_environment(source: dict[str, str] | None = None) -> dict[str, str]:
    """Return the allowlisted environment for the wrapper process.

    Only ``PATH``, ``HOME``, ``LANG``, and ``TMPDIR`` pass, and only when set. No
    token, no ``CODEQL_*`` override, no ``PYTHONPATH`` reaches the branch-adjacent
    process.
    """
    env = os.environ if source is None else source
    return {name: env[name] for name in ENV_ALLOWLIST if name in env}


def precheck(repo_root: Path, wrapper: Path, head: str) -> str | None:
    """Return the failed guard's name, or None when every pre-run guard holds."""
    if platform.system() == "Windows":
        return "platform has no process group kill"
    if not (repo_root / ".codeql").is_dir():
        return ".codeql directory missing"
    cli = repo_root / _CLI_RELATIVE
    if not cli.is_file():
        return "CodeQL CLI not installed"
    if not wrapper.is_file():
        return "codeql-scan wrapper not found"
    if not _cache_built_at(repo_root / _CACHE_METADATA, head):
        return "database cache not built at HEAD"
    return None


def _cache_built_at(metadata_path: Path, head: str) -> bool:
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(metadata, dict) and metadata.get("git_head") == head


def _kill_group(process: subprocess.Popen[str]) -> None:
    """Kill the wrapper's whole process group and reap it."""
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        process.kill()
    process.communicate()


def run_wrapper(
    repo_root: Path, wrapper: Path, languages: tuple[str, ...]
) -> tuple[int | None, str]:
    """Run the wrapper in its own session. Return ``(exit_code, stderr)``.

    ``exit_code`` is None on timeout (the group is killed) or when the process
    cannot start. A negative code means a signal ended it.
    """
    command = [sys.executable, str(wrapper), *_WRAPPER_ARGS, *languages]
    try:
        process = subprocess.Popen(
            command,
            cwd=str(repo_root),
            env=scan_environment(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            start_new_session=True,
        )
    except OSError:
        return None, ""
    try:
        _, stderr = process.communicate(timeout=LOCAL_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        _kill_group(process)
        return None, ""
    return process.returncode, stderr or ""


def read_fresh_sarif(
    repo_root: Path, languages: tuple[str, ...], started_ns: int
) -> list[list[Any]] | None:
    """Return the results list of each language's SARIF, or None on any gap.

    A file counts only when it exists, was modified at or after ``started_ns``, and
    parses as SARIF with a ``runs`` list. One missing, stale, or unreadable file
    returns None: the evidence for "scanned" is incomplete.
    """
    per_language: list[list[Any]] = []
    for language in languages:
        results = _read_one_sarif(repo_root / _RESULTS_DIR / f"{language}.sarif", started_ns)
        if results is None:
            return None
        per_language.append(results)
    return per_language


def _read_one_sarif(path: Path, started_ns: int) -> list[Any] | None:
    try:
        if path.stat().st_mtime_ns < started_ns:
            return None
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    runs = document.get("runs") if isinstance(document, dict) else None
    if not isinstance(runs, list):
        return None
    results: list[Any] = []
    for run in runs:
        run_results = run.get("results") if isinstance(run, dict) else None
        results.extend(run_results if isinstance(run_results, list) else [])
    return results


def classify(
    exit_code: int | None,
    stderr: str,
    languages: tuple[str, ...],
    sarif_results: list[list[Any]] | None,
) -> LocalScanOutcome:
    """Map the wrapper exit code and SARIF evidence to an outcome."""
    if exit_code is None:
        return _skipped("scan timed out or did not start", languages)
    if exit_code < 0:
        return _skipped("scan ended by a signal", languages)
    if exit_code == 0 and SKIP_MARKER in stderr:
        return _skipped("wrapper skipped the scan", languages)
    if exit_code not in (0, 1):
        return _skipped(f"scan exited {exit_code}", languages)
    if sarif_results is None:
        return _skipped("no fresh SARIF for every language", languages)
    flat = [result for per_language in sarif_results for result in per_language]
    if exit_code == 0 and not flat:
        return LocalScanOutcome("CLEAN", languages=languages)
    if exit_code == 1 and flat:
        return LocalScanOutcome("FINDINGS", languages=languages, results=flat)
    return _skipped("exit and results disagree", languages)


def run_local_scan(
    repo_root: Path,
    wrapper: Path,
    head: str,
    tree_clean: bool,
    languages: list[str],
) -> LocalScanOutcome:
    """Run every guard, then the wrapper, and classify the outcome."""
    if not tree_clean:
        return _skipped("working tree not clean")
    failed = precheck(repo_root, wrapper, head)
    if failed is not None:
        return _skipped(failed)
    if not languages:
        return _skipped("no scannable languages")
    chosen = tuple(languages)
    started_ns = time.time_ns()
    exit_code, stderr = run_wrapper(repo_root, wrapper, chosen)
    sarif_results = read_fresh_sarif(repo_root, chosen, started_ns)
    return classify(exit_code, stderr, chosen, sarif_results)
