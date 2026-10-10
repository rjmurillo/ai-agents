"""Tests for judging modules against their partition's runner speed."""

from __future__ import annotations

import pytest

from scripts.testing.duration_compare import compare
from scripts.testing.duration_partition_speed import SPEED_CAP, partition_speeds
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


def test_a_fast_partition_never_tightens_the_thresholds() -> None:
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


def test_a_1_5x_slow_runner_passes() -> None:
    history = _history({m: 20.0 for m in _MODULES})

    result = compare(_leg({m: 30.0 for m in _MODULES}), history, DEFAULT_LIMITS)

    assert result.modules == []


def test_a_3x_partition_slowdown_is_a_regression_not_masked() -> None:
    history = _history({m: 20.0 for m in _MODULES})

    result = compare(_leg({m: 60.0 for m in _MODULES}), history, DEFAULT_LIMITS)

    names = {r.name for r in result.modules}
    assert "partition leg" in names
    assert set(_MODULES) <= names
    assert result.speeds == {"leg": pytest.approx(3.0)}


def test_the_cap_bounds_the_scaling_not_the_reported_speed() -> None:
    history = _history({m: 20.0 for m in _MODULES})
    seconds = SPEED_CAP * 20.0 * 1.0
    just_over = {m: seconds * 1.05 for m in _MODULES}

    result = compare(_leg(just_over), history, DEFAULT_LIMITS)

    assert "partition leg" in {r.name for r in result.modules}


def test_a_module_missing_from_the_current_run_does_not_count() -> None:
    history = _history({m: 20.0 for m in _MODULES})
    history.append(_leg({"tests/test_gone.py": 500.0}))
    current = _leg({m: 32.0 for m in _MODULES[:5]})

    result = compare(current, history, DEFAULT_LIMITS)

    assert result.comparable == 5
    assert result.modules == []


def test_a_module_without_a_partition_is_scaled_by_one() -> None:
    history = _history({m: 20.0 for m in _MODULES})
    current = _leg({m: 32.0 for m in _MODULES})
    current.module_partitions.pop(_MODULES[0])

    result = compare(current, history, DEFAULT_LIMITS)

    assert [r.name for r in result.modules] == [_MODULES[0]]


def test_each_partition_gets_its_own_speed() -> None:
    slow = [f"tests/test_s{i}.py" for i in range(5)]
    fast = [f"tests/test_f{i}.py" for i in range(5)]
    base = {m: 20.0 for m in [*slow, *fast]}
    now = {**{m: 30.0 for m in slow}, **{m: 20.0 for m in fast}}
    current = _leg(now)
    current.module_partitions.update({m: "slow" for m in slow})
    current.module_partitions.update({m: "fast" for m in fast})

    result = compare(current, _history(base), DEFAULT_LIMITS)

    assert result.speeds == {"fast": 1.0, "slow": pytest.approx(1.5)}
    assert result.modules == []
