"""Shared builders for the test duration trend tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from scripts.testing.duration_compare import Thresholds
from scripts.testing.duration_schema import ids_digest
from scripts.testing.duration_snapshot import Snapshot

NOW = datetime(2026, 10, 7, tzinfo=UTC)
DEFAULT_LIMITS = Thresholds(module_ratio=1.5, module_min_delta=10.0,
                            suite_ratio=1.25, suite_min_delta=60.0)


def write_junit(tmp_path: Path, name: str, cases: dict[str, list[float]], wall: float) -> Path:
    """Write a pytest-shaped JUnit report: module dotted path -> test durations."""
    rows = [
        f'<testcase classname="{classname}" name="t{index}" time="{seconds}" />'
        for classname, durations in cases.items()
        for index, seconds in enumerate(durations)
    ]
    path = tmp_path / f"{name}.xml"
    path.write_text(
        '<?xml version="1.0" encoding="utf-8"?><testsuites>'
        f'<testsuite name="pytest" time="{wall}">{"".join(rows)}</testsuite></testsuites>',
        encoding="utf-8",
    )
    return path


def alpha_ids(tests: int) -> str:
    """The digest ``write_junit`` produces for ``tests`` cases in tests.test_alpha."""
    return ids_digest(f"tests/test_alpha.py::t{i}" for i in range(tests))


def write_history(tmp_path: Path, module_seconds: list[float], tests: int = 2) -> Path:
    """Write a history whose snapshots each ran tests t0..t{tests-1} in tests/test_alpha.py."""
    snapshots = [
        Snapshot(
            sha=f"sha{i}",
            recorded_at="2026-10-01T00:00:00+00:00",
            partitions={"pytest-results": {"tests": tests, "wall_seconds": s}},
            modules={"tests/test_alpha.py": {"seconds": s, "tests": tests,
                                             "ids": alpha_ids(tests)}},
        ).to_dict()
        for i, s in enumerate(module_seconds)
    ]
    path = tmp_path / "history.json"
    path.write_text(json.dumps({"schema": 1, "snapshots": snapshots}), encoding="utf-8")
    return path
