"""One run's test durations, read from pytest JUnit reports.

A snapshot holds wall seconds per partition (one JUnit file each) and test
seconds per module. ``duration_trend.py`` compares snapshots across runs.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from scripts.testing.slow_test_report import group_by_module, load_junit


@dataclass
class Snapshot:
    """One run's measured durations."""

    sha: str
    recorded_at: str
    partitions: dict[str, dict[str, float]] = field(default_factory=dict)
    modules: dict[str, dict[str, float]] = field(default_factory=dict)

    @property
    def total_seconds(self) -> float:
        return sum(m["seconds"] for m in self.modules.values())

    @property
    def total_tests(self) -> int:
        return int(sum(m["tests"] for m in self.modules.values()))

    def to_dict(self) -> dict[str, Any]:
        return {
            "sha": self.sha,
            "recorded_at": self.recorded_at,
            "partitions": self.partitions,
            "modules": self.modules,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Snapshot:
        return cls(
            sha=str(data["sha"]),
            recorded_at=str(data["recorded_at"]),
            partitions={str(k): dict(v) for k, v in data["partitions"].items()},
            modules={str(k): dict(v) for k, v in data["modules"].items()},
        )


def partition_wall_seconds(path: Path) -> float:
    """The wall time pytest recorded for the run, from the ``testsuite`` element.

    Call only after ``load_junit`` has read the same file: it refuses a report
    with a DTD or entity, which keeps this stdlib parse safe.
    """
    root = ET.fromstring(path.read_text(encoding="utf-8"))
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    return sum(float(s.get("time", "0") or 0.0) for s in suites)


def build_snapshot(paths: Sequence[Path], sha: str, now: datetime) -> Snapshot:
    """Read every JUnit report into one snapshot keyed by module."""
    snapshot = Snapshot(sha=sha, recorded_at=now.isoformat(timespec="seconds"))
    records = []
    for path in paths:
        loaded = load_junit(path)
        records.extend(loaded)
        snapshot.partitions[path.stem] = {
            "tests": len(loaded),
            "wall_seconds": round(partition_wall_seconds(path), 3),
        }
    for group in group_by_module(records, min_seconds=0.0):
        snapshot.modules[group.module] = {"seconds": round(group.seconds, 3), "tests": group.tests}
    return snapshot
