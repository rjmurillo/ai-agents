"""Tests for judging modules against their partition's runner speed."""

from __future__ import annotations

import pytest

from scripts.testing.duration_compare import compare
from scripts.testing.duration_partition_speed import partition_speeds
from scripts.testing.duration_schema import ModuleEntry, ids_digest
from scripts.testing.duration_snapshot import Snapshot
from tests.duration_test_helpers import DEFAULT_LIMITS


def _module(seconds: float, name: str) -> ModuleEntry:
    return {"seconds": seconds, "tests": 1, "ids": ids_digest([f"{name}::t"])}


def _leg(seconds: dict[str, float], partition: str = "leg") -> Snapshot:
    """A snapshot whose modules all ran in one partition."""
    return Snapshot(
        sha="now", recorded_at="2026-10-10T00:00:00+00:00",
        partitions={partition: {"tests": len(seconds), "wall_seconds": 1.0}},
        modules={n: _module(s, n) for n, s in seconds.items()},
        module_partitions={n: partition for n in seconds},
    )


def _history(baseline: dict[str, float], samples: int = 3) -> list[Snapshot]:
    return [_leg(baseline) for _ in range(samples)]


_MODULES = [f"tests/test_m{i}.py" for i in range(6)]


def test_a_uniformly_slow_partition_is_runner_speed_not_a_regression() -> None:
    history = _history({m: 20.0 for m in _MODULES})

    result = compare(_leg({m: 32.0 for m in _MODULES}), history, DEFAULT_LIMITS)

    assert result.modules == []
    assert result.speeds == {"leg": pytest.approx(1.6)}


def test_a_module_slower_than_its_slow_partition_still_regresses() -> None:
    history = _history({m: 20.0 for m in _MODULES})
    current = {m: 32.0 for m in _MODULES}
    current[_MODULES[0]] = 90.0

    result = compare(_leg(current), history, DEFAULT_LIMITS)

    assert [r.name for r in result.modules] == [_MODULES[0]]


def test_a_fast_partition_never_loosens_the_thresholds() -> None:
    history = _history({m: 20.0 for m in _MODULES})
    current = {m: 10.0 for m in _MODULES}
    current[_MODULES[0]] = 32.0

    result = compare(_leg(current), history, DEFAULT_LIMITS)

    assert result.speeds == {"leg": 1.0}
    assert [r.name for r in result.modules] == [_MODULES[0]]


def test_a_partition_with_too_few_modules_has_no_speed_estimate() -> None:
    names = _MODULES[:2]
    history = _history({m: 20.0 for m in names})

    result = compare(_leg({m: 32.0 for m in names}), history, DEFAULT_LIMITS)

    assert result.speeds == {}
    assert [r.name for r in result.modules] == names


def test_sub_second_modules_do_not_set_the_partition_speed() -> None:
    names = [f"tests/test_tiny{i}.py" for i in range(6)]
    history = _history({m: 0.2 for m in names})

    result = compare(_leg({m: 0.9 for m in names}), history, DEFAULT_LIMITS)

    assert result.speeds == {}


def test_partition_speed_is_the_median_ratio_of_substantial_modules() -> None:
    ratios = [1.2, 1.4, 1.6, 1.8, 2.0]
    current = _leg({m: 10.0 * r for m, r in zip(_MODULES, ratios, strict=False)})
    baselines = dict.fromkeys(_MODULES[:5], 10.0)

    assert partition_speeds(current, baselines) == {"leg": pytest.approx(1.6)}
