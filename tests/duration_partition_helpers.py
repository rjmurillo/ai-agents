"""Snapshot builders for the partition speed tests."""

from __future__ import annotations

from scripts.testing.duration_schema import ModuleEntry, ids_digest
from scripts.testing.duration_snapshot import Snapshot


def module_entry(seconds: float, name: str) -> ModuleEntry:
    return {"seconds": seconds, "tests": 1, "ids": ids_digest([f"{name}::t"])}


def leg(seconds: dict[str, float], partition: str = "leg") -> Snapshot:
    """A snapshot whose modules all ran in one partition."""
    return Snapshot(
        sha="now", recorded_at="2026-10-10T00:00:00+00:00",
        partitions={partition: {"tests": len(seconds), "wall_seconds": 1.0}},
        modules={n: module_entry(s, n) for n, s in seconds.items()},
        module_partitions={n: partition for n in seconds},
    )


def history_of(baseline: dict[str, float], samples: int = 3) -> list[Snapshot]:
    return [leg(baseline) for _ in range(samples)]


MODULES = [f"tests/test_m{i}.py" for i in range(6)]
