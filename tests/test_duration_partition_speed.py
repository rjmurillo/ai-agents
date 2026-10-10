"""Tests for the per-partition runner speed estimate."""

from __future__ import annotations

import pytest

from scripts.testing.duration_compare import compare
from scripts.testing.duration_partition_speed import partition_speeds
from tests.duration_partition_helpers import MODULES, history_of, leg
from tests.duration_test_helpers import DEFAULT_LIMITS


def test_a_partition_with_too_few_modules_has_no_speed_estimate() -> None:
    names = MODULES[:2]
    history = history_of({m: 20.0 for m in names})

    result = compare(leg({m: 32.0 for m in names}), history, DEFAULT_LIMITS)

    assert result.speeds == {}
    assert [r.name for r in result.modules] == names


def test_sub_second_modules_do_not_set_the_partition_speed() -> None:
    names = [f"tests/test_tiny{i}.py" for i in range(6)]
    history = history_of({m: 0.2 for m in names})

    result = compare(leg({m: 0.9 for m in names}), history, DEFAULT_LIMITS)

    assert result.speeds == {}


def test_partition_speed_is_the_median_ratio_of_substantial_modules() -> None:
    ratios = [1.2, 1.4, 1.6, 1.8, 2.0]
    current = leg({m: 10.0 * r for m, r in zip(MODULES, ratios, strict=False)})
    baselines = dict.fromkeys(MODULES[:5], 10.0)

    assert partition_speeds(current, baselines) == {"leg": pytest.approx(1.6)}


def test_each_partition_gets_its_own_speed() -> None:
    slow = [f"tests/test_s{i}.py" for i in range(5)]
    fast = [f"tests/test_f{i}.py" for i in range(5)]
    base = {m: 20.0 for m in [*slow, *fast]}
    now = {**{m: 30.0 for m in slow}, **{m: 20.0 for m in fast}}
    current = leg(now)
    current.module_partitions.update({m: "slow" for m in slow})
    current.module_partitions.update({m: "fast" for m in fast})

    result = compare(current, history_of(base), DEFAULT_LIMITS)

    assert result.speeds == {"fast": 1.0, "slow": pytest.approx(1.5)}
    assert result.modules == []


def test_a_module_without_a_partition_is_scaled_by_one() -> None:
    history = history_of({m: 20.0 for m in MODULES})
    current = leg({m: 32.0 for m in MODULES})
    current.module_partitions.pop(MODULES[0])

    result = compare(current, history, DEFAULT_LIMITS)

    assert [r.name for r in result.modules] == [MODULES[0]]
