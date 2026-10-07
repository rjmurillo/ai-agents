"""One run's test durations, read from pytest JUnit reports.

A snapshot holds wall seconds per partition (one JUnit file each) and, per
test module, its seconds, its test count, and a digest of its test IDs.
``duration_trend.py`` compares snapshots across runs.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from scripts.testing.duration_schema import (
    ModuleEntry,
    PartitionEntry,
    ids_digest,
    parse_module,
    parse_partition,
)
from scripts.testing.slow_test_report import load_junit


@dataclass
class Snapshot:
    """One run's measured durations."""

    sha: str
    recorded_at: str
    partitions: dict[str, PartitionEntry] = field(default_factory=dict)
    modules: dict[str, ModuleEntry] = field(default_factory=dict)

    @property
    def total_seconds(self) -> float:
        return sum(m["seconds"] for m in self.modules.values())

    @property
    def total_tests(self) -> int:
        return sum(m["tests"] for m in self.modules.values())

    def to_dict(self) -> dict[str, Any]:
        return {"sha": self.sha, "recorded_at": self.recorded_at,
                "partitions": self.partitions, "modules": self.modules}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Snapshot:
        """Rebuild a snapshot, raising ``ValueError`` on any malformed field."""
        return cls(
            sha=str(data["sha"]),
            recorded_at=str(data["recorded_at"]),
            partitions={str(k): parse_partition(v) for k, v in data["partitions"].items()},
            modules={str(k): parse_module(v) for k, v in data["modules"].items()},
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
    seconds: dict[str, float] = defaultdict(float)
    nodeids: dict[str, list[str]] = defaultdict(list)
    for path in paths:
        records = load_junit(path)
        for record in records:
            seconds[record.module] += record.duration
            nodeids[record.module].append(record.nodeid)
        snapshot.partitions[path.stem] = {
            "tests": len(records), "wall_seconds": round(partition_wall_seconds(path), 3)}
    for module in sorted(seconds):
        snapshot.modules[module] = {"seconds": round(seconds[module], 3),
                                    "tests": len(nodeids[module]),
                                    "ids": ids_digest(nodeids[module])}
    return snapshot
