"""Shared fixtures for the flaky test report tests (scripts/ci/_flaky_*.py)."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.ci import _flaky_state as fs

FLAKY = "tests/test_a.py::test_flaky"
BROKEN = "tests/test_a.py::test_broken[a|b]"


def write_junit(path: Path, cases: list[str | None]) -> Path:
    """Write a JUnit report; each entry is None (pass), 'failure', or 'error'."""
    body = []
    for index, child in enumerate(cases):
        inner = f"<{child} message='x'/>" if child else ""
        body.append(f"<testcase classname='tests.test_a' name='t{index}'>{inner}</testcase>")
    path.write_text(
        f"<?xml version='1.0'?><testsuites><testsuite>{''.join(body)}</testsuite></testsuites>",
        encoding="utf-8",
    )
    return path


def write_lastfailed(path: Path, nodeids: list[str]) -> Path:
    """Write a pytest ``lastfailed`` cache file listing *nodeids*."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict.fromkeys(nodeids, True)), encoding="utf-8")
    return path


def rerun_cache(out_dir: Path) -> Path:
    """The rerun's own ``lastfailed`` path under *out_dir*."""
    return out_dir / fs.RERUN_CACHE_DIR / "v" / "cache" / "lastfailed"


def make_state(**overrides: object) -> dict[str, object]:
    """A valid rerun state where BROKEN failed again and FLAKY passed."""
    state: dict[str, object] = {
        "version": fs.STATE_VERSION,
        "status": fs.STATUS_RAN,
        "first_failures": [BROKEN, FLAKY],
        "max_tests": 25,
        "rerun_exit": 1,
        "rerun_failures": [BROKEN],
    }
    state.update(overrides)
    return state
