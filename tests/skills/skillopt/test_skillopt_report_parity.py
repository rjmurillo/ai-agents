"""skillopt's report helpers must agree with bootstrap_eval's for the same inputs."""

from __future__ import annotations

import sys
from pathlib import Path

import _skillopt_report as report_mod
import pytest

_SCRIPTS = (
    Path(__file__).resolve().parents[3] / ".claude" / "skills" / "skill-bootstrap" / "scripts"
)
sys.path.insert(0, str(_SCRIPTS))
try:
    import bootstrap_eval
finally:
    sys.path.remove(str(_SCRIPTS))

SAMPLES = [[], [3], [1, 2], [0.0, 1.0, 1.0, 0.0], [10, 20, 35, 5, 5], [0.1, 0.2, 0.3]]
VALUES = [0, 1, 2.5, -1, True, False, None, "3", float("nan"), float("inf"), 10**400]


@pytest.mark.parametrize("values", SAMPLES)
def test_spread_agrees(values):
    assert report_mod.spread(values) == bootstrap_eval.spread(values)


@pytest.mark.parametrize("integer", [False, True])
@pytest.mark.parametrize("value", VALUES, ids=repr)
def test_is_measurement_agrees(value, integer):
    assert report_mod.is_measurement(value, integer=integer) == bootstrap_eval.is_measurement(
        value, integer=integer
    )


def test_pass_rate_name_and_rounding_agree():
    assert "pass_rate" in bootstrap_eval.METRICS
    assert report_mod.ROUND_PLACES == bootstrap_eval.ROUND_PLACES


@pytest.mark.parametrize(
    ("base", "other"),
    [([], [1.0]), ([1.0], []), ([1 / 3], [2 / 3]), ([1, 0, 0], [1, 1, 0]), ([5, 7], [1, 2, 3])],
)
def test_mean_delta_agrees(base, other):
    assert report_mod.mean_delta(base, other) == bootstrap_eval.mean_delta(base, other)
