"""Tests for comparing a duration snapshot with the history median."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.testing.duration_compare import Thresholds, compare
from scripts.testing.duration_history import load_history
from scripts.testing.duration_schema import ModuleEntry, ids_digest
from scripts.testing.duration_snapshot import Snapshot, build_snapshot
from tests.duration_test_helpers import DEFAULT_LIMITS, NOW, write_history, write_junit


def _alpha(tmp_path: Path, seconds: list[float]) -> Snapshot:
    report = write_junit(tmp_path, "p", {"tests.test_alpha": seconds}, sum(seconds))
    return build_snapshot([report], "now", NOW)


def test_baseline_is_the_median_of_matching_snapshots(tmp_path: Path) -> None:
    history, _ = load_history(write_history(tmp_path, [10.0, 12.0, 50.0]))

    result = compare(_alpha(tmp_path, [5.0, 6.0]), history, DEFAULT_LIMITS)

    assert (result.comparable, result.baseline, result.seconds) == (1, 12.0, 11.0)
    assert result.modules == [] and result.suite is None


def test_a_snapshot_with_a_different_test_count_is_not_a_sample(tmp_path: Path) -> None:
    history, _ = load_history(write_history(tmp_path, [10.0], tests=3))

    result = compare(_alpha(tmp_path, [50.0, 50.0]), history, DEFAULT_LIMITS)

    assert result.comparable == 0
    assert result.modules == [] and result.suite is None


def test_a_module_over_both_thresholds_regresses(tmp_path: Path) -> None:
    history, _ = load_history(write_history(tmp_path, [10.0, 10.0]))

    result = compare(_alpha(tmp_path, [15.0, 15.0]), history, DEFAULT_LIMITS)

    assert [(r.name, r.seconds, r.baseline, r.samples) for r in result.modules] == [
        ("tests/test_alpha.py", 30.0, 10.0, 2)]


@pytest.mark.parametrize(
    ("baseline", "seconds", "why"),
    [(5.0, [4.0, 4.0], "1.6x but only 3s slower"),
     (100.0, [60.0, 60.0], "20s slower but only 1.2x")],
)
def test_crossing_one_threshold_alone_is_not_a_regression(
    tmp_path: Path, baseline: float, seconds: list[float], why: str
) -> None:
    history, _ = load_history(write_history(tmp_path, [baseline]))

    assert compare(_alpha(tmp_path, seconds), history, DEFAULT_LIMITS).modules == [], why


def test_a_module_without_a_baseline_stays_out_of_the_suite_sum(tmp_path: Path) -> None:
    history, _ = load_history(write_history(tmp_path, [10.0, 20.0]))
    report = write_junit(tmp_path, "p",
                         {"tests.test_alpha": [6.0, 6.0], "tests.test_new": [900.0]}, 912.0)

    result = compare(build_snapshot([report], "now", NOW), history, DEFAULT_LIMITS)

    assert (result.comparable, result.seconds, result.baseline) == (1, 12.0, 15.0)
    assert result.min_samples == 2
    assert result.suite is None


def test_the_suite_regresses_on_the_comparable_sum(tmp_path: Path) -> None:
    history, _ = load_history(write_history(tmp_path, [100.0]))
    lax_modules = Thresholds(module_ratio=10.0, module_min_delta=1000.0,
                             suite_ratio=1.25, suite_min_delta=60.0)

    result = compare(_alpha(tmp_path, [80.0, 90.0]), history, lax_modules)

    assert result.modules == []
    assert result.suite is not None
    assert (result.suite.seconds, result.suite.baseline) == (170.0, 100.0)


def test_a_replaced_test_with_the_same_count_is_not_compared(tmp_path: Path) -> None:
    """Two tests ran on main; a PR swaps t1 for a new test, so the count still matches."""
    history, _ = load_history(write_history(tmp_path, [10.0, 10.0]))
    report = tmp_path / "swap.xml"
    report.write_text(
        '<testsuites><testsuite time="60"><testcase classname="tests.test_alpha" name="t0" '
        'time="10" /><testcase classname="tests.test_alpha" name="t_new" time="50" />'
        "</testsuite></testsuites>", encoding="utf-8")

    result = compare(build_snapshot([report], "now", NOW), history, DEFAULT_LIMITS)

    assert result.comparable == 0
    assert result.modules == [] and result.suite is None


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
