"""Tests for scaling baselines by partition speed, up to the cap."""

from __future__ import annotations

import pytest

from scripts.testing.duration_compare import compare
from scripts.testing.duration_partition_speed import SPEED_CAP
from tests.duration_partition_helpers import MODULES, history_of, leg
from tests.duration_test_helpers import DEFAULT_LIMITS


def test_a_uniformly_slow_partition_is_runner_speed_not_a_regression() -> None:
    history = history_of({m: 20.0 for m in MODULES})

    result = compare(leg({m: 32.0 for m in MODULES}), history, DEFAULT_LIMITS)

    assert result.modules == []
    assert result.speeds == {"leg": pytest.approx(1.6)}


def test_a_module_slower_than_its_slow_partition_still_regresses() -> None:
    history = history_of({m: 20.0 for m in MODULES})
    current = {m: 32.0 for m in MODULES}
    current[MODULES[0]] = 90.0

    result = compare(leg(current), history, DEFAULT_LIMITS)

    assert [r.name for r in result.modules] == [MODULES[0]]


def test_a_fast_partition_never_tightens_the_thresholds() -> None:
    history = history_of({m: 20.0 for m in MODULES})
    current = {m: 10.0 for m in MODULES}
    current[MODULES[0]] = 32.0

    result = compare(leg(current), history, DEFAULT_LIMITS)

    assert result.speeds == {"leg": 1.0}
    assert [r.name for r in result.modules] == [MODULES[0]]


def test_a_1_5x_slow_runner_passes() -> None:
    history = history_of({m: 20.0 for m in MODULES})

    result = compare(leg({m: 30.0 for m in MODULES}), history, DEFAULT_LIMITS)

    assert result.modules == []


def test_a_3x_partition_slowdown_is_a_regression_not_masked() -> None:
    history = history_of({m: 20.0 for m in MODULES})

    result = compare(leg({m: 60.0 for m in MODULES}), history, DEFAULT_LIMITS)

    names = {r.name for r in result.modules}
    assert "partition leg" in names
    assert set(MODULES) <= names
    assert result.speeds == {"leg": pytest.approx(3.0)}


def test_the_cap_bounds_the_scaling_not_the_reported_speed() -> None:
    history = history_of({m: 20.0 for m in MODULES})
    seconds = SPEED_CAP * 20.0 * 1.0
    just_over = {m: seconds * 1.05 for m in MODULES}

    result = compare(leg(just_over), history, DEFAULT_LIMITS)

    assert "partition leg" in {r.name for r in result.modules}


def test_a_module_missing_from_the_current_run_does_not_count() -> None:
    history = history_of({m: 20.0 for m in MODULES})
    history.append(leg({"tests/test_gone.py": 500.0}))
    current = leg({m: 32.0 for m in MODULES[:5]})

    result = compare(current, history, DEFAULT_LIMITS)

    assert result.comparable == 5
    assert result.modules == []
