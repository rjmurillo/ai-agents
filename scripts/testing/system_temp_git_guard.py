"""Fail the pytest run loudly when the system temp directory holds a ``.git`` entry.

A stray ``<tempdir>/.git`` makes the temp directory read as a repository root.
Every test that discovers a git root from a path under it then resolves to the
temp directory instead of failing the "no repository here" branch, and sixteen
tests across six files failed that way on 2026-10-23 (issue #6889). The failure
names the tests, never the stray directory, so the cause costs an hour to find.

This plugin checks once before the first test and once after the last. A
stray at start stops the run before any test executes. A stray at end means
something created it during the run, so the exit status becomes a failure and
the report names the path and its contents. Under xdist only the controller
checks, because every worker would otherwise repeat the same report.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

ISSUE_REFERENCE = "issue #6889"
_ENTRY_LIMIT = 10


def system_temp_git_path() -> Path:
    """Return the ``.git`` path directly under the current system temp directory."""
    return Path(tempfile.gettempdir()) / ".git"


def describe_stray_git(stray: Path) -> str | None:
    """Return a failure message when ``stray`` exists, else ``None``.

    ``os.path.lexists`` also catches a dangling symlink, which ``Path.exists``
    reports as absent, so any entry named ``.git`` is reported whatever it
    points to.
    """
    if not os.path.lexists(stray):
        return None
    if stray.is_dir() and not stray.is_symlink():
        try:
            names = sorted(entry.name for entry in stray.iterdir())
        except OSError as error:
            return _message(stray, f"It is a directory that cannot be listed: {error}.")
        shown = ", ".join(names[:_ENTRY_LIMIT]) or "nothing"
        extra = len(names) - _ENTRY_LIMIT
        if extra > 0:
            shown = f"{shown}, and {extra} more"
        contents = f"It is a directory holding: {shown}."
    else:
        contents = "It is not a plain directory."
    return _message(stray, contents)


def _message(stray: Path, contents: str) -> str:
    return (
        f"{stray} exists. {contents} "
        f"A .git entry in the system temp directory makes {stray.parent} look like a "
        "repository root, which fails every test that discovers a git root from a "
        f"temp path ({ISSUE_REFERENCE}). Move it aside, for example "
        f"`mv {stray} ~/quarantine-tmp-dot-git`, and report the process that "
        "created it."
    )


def _is_xdist_worker(config: pytest.Config) -> bool:
    return hasattr(config, "workerinput")


def pytest_sessionstart(session: pytest.Session) -> None:
    if _is_xdist_worker(session.config):
        return
    message = describe_stray_git(system_temp_git_path())
    if message is not None:
        pytest.exit(f"Stray system temp .git before the run: {message}", returncode=4)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    if _is_xdist_worker(session.config):
        return
    message = describe_stray_git(system_temp_git_path())
    if message is None:
        return
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    text = f"Stray system temp .git appeared during the run: {message}"
    if reporter is not None:
        reporter.write_line(text, red=True)
    else:
        print(text)
    if exitstatus == pytest.ExitCode.OK:
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
