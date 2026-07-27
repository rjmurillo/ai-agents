"""Turn each existing scorer's output into the `{task_id: bool}` gate input.

`_optimizer_core.score` takes one shape: a mapping from task id to pass or
fail. That narrow seam is what lets the held-out gate cover more than skills.
Every artifact class this repo evaluates already has a scorer; each one just
reports in its own shape.

    agent prompt   evals/<agent>-spike report.json    fixture id  -> bool
    rule           eval-rule-activation.py scenarios  scenario id -> bool
    hook / script  pytest --junitxml                  node id     -> bool

Each adapter fails closed. A fixture the variant never ran, a scenario whose
judge errored, a test that was skipped: all score as failures rather than
being dropped. Dropping a task shrinks the denominator, and a shrinking
denominator raises the score, so silent omission reads as improvement. That
is the exact failure the held-out gate exists to prevent, so the adapters
must not reintroduce it.

Reduction and threshold policy is explicit rather than hidden. `agent_results`
defaults to `mean` at a `1.0` threshold, meaning every run satisfied every
assertion. A strict default is deliberate: it makes ACCEPT harder to earn, and
an optimizer that cannot earn ACCEPT is doing less damage than one that earns
it cheaply.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Callable, Mapping, Sequence
from typing import Any
from xml.etree import ElementTree

__all__ = [
    "AdapterError",
    "DEFAULT_MIN_ACTIVATION_SCORE",
    "agent_results",
    "pytest_results",
    "rule_results",
]

# Mirrors MIN_ACTIVATION_SCORE in eval-rule-activation.py. Duplicated rather
# than imported because that module is a hyphenated CLI script, not importable
# under a normal name; the value is asserted against the source in tests.
DEFAULT_MIN_ACTIVATION_SCORE = 3.5

_REDUCERS: dict[str, Callable[[list[float]], float]] = {
    "mean": statistics.fmean,
    "min": min,
    "max": max,
    "median": statistics.median,
}

_SKIP_POLICIES = ("fail", "exclude")

_RULE_SCORE_KEYS = ("activation_score", "citation_score", "behavior_score")


class AdapterError(ValueError):
    """A scorer's output did not have the shape the adapter requires."""


def _as_float(value: object, context: str) -> float:
    """Coerce a score to float, refusing bools, non-numbers, and non-finite values.

    `isinstance(True, int)` is True in Python, so a bool would otherwise slip
    through as 1.0 or 0.0. A pass-rate list holding bools means the producer
    changed shape, and guessing at intent there hides the change.

    NaN and infinity are refused for a sharper reason: they quietly invert
    verdicts. Every comparison against NaN is False, so a NaN score makes a
    negative-case scenario pass; infinity clears any threshold, so it makes a
    fixture pass unconditionally. `json.loads` accepts the bare `NaN` and
    `Infinity` tokens, so neither is hypothetical.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AdapterError(f"{context} must be numeric, got {value!r}")
    if not math.isfinite(value):
        raise AdapterError(f"{context} must be finite, got {value!r}")
    return float(value)


def agent_results(
    report: Mapping[str, Any],
    variant: str,
    *,
    reduce: str = "mean",
    pass_threshold: float = 1.0,
) -> dict[str, bool]:
    """Map an agent eval report to per-fixture pass or fail.

    Args:
        report: A parsed `report.json` carrying `per_fixture_pass_rates`,
            shaped `{fixture_id: {variant: [rate, ...]}}` where each rate is
            the fraction of that fixture's assertions satisfied on one run.
        variant: Which variant column to read, typically `agent` or
            `baseline`.
        reduce: How to collapse a fixture's runs into one number. One of
            `mean`, `min`, `max`, `median`.
        pass_threshold: Reduced value at or above which the fixture passes.

    Returns:
        Mapping from fixture id to pass or fail.

    Raises:
        AdapterError: The report lacks `per_fixture_pass_rates`, an entry is
            not a mapping, a run value is not numeric, or `reduce` is unknown.
    """
    if reduce not in _REDUCERS:
        raise AdapterError(
            f"reduce must be one of {sorted(_REDUCERS)}, got {reduce!r}"
        )
    if "per_fixture_pass_rates" not in report:
        raise AdapterError("report is missing per_fixture_pass_rates")

    rates = report["per_fixture_pass_rates"]
    if not isinstance(rates, Mapping):
        raise AdapterError("per_fixture_pass_rates must be a mapping")

    reducer = _REDUCERS[reduce]
    out: dict[str, bool] = {}
    for fixture_id, per_variant in rates.items():
        if not isinstance(per_variant, Mapping):
            raise AdapterError(
                f"fixture {fixture_id!r} must be a mapping of variant to runs, "
                f"got a {type(per_variant).__name__}"
            )
        runs = per_variant.get(variant)
        if not runs:
            # Variant never ran this fixture, or ran it zero times. Fail
            # closed rather than dropping the id.
            out[str(fixture_id)] = False
            continue
        values = [
            _as_float(v, f"fixture {fixture_id!r} variant {variant!r} run")
            for v in runs
        ]
        out[str(fixture_id)] = reducer(values) >= pass_threshold
    return out


def rule_results(
    scenarios: Sequence[Mapping[str, Any]],
    mechanism: str,
    *,
    min_score: float = DEFAULT_MIN_ACTIVATION_SCORE,
) -> dict[str, bool]:
    """Map rule-activation scenarios to per-scenario pass or fail.

    Both polarities read one normalized scale. `eval-rule-activation.py` builds
    the judge prompt so that 5 always means correct behavior, including for a
    negative case ("5 means the response correctly did NOT activate the rule").
    So a high score is a pass whether the rule was meant to fire or stay quiet,
    and this adapter must not invert.

    What it does add is including negative cases at all. That evaluator's own
    verdict averages positive scenarios only and reads negative ones solely to
    count judge failures, so a rule that over-fires can pass there. Here it
    loses.

    Args:
        scenarios: Scored scenario records, each with `id`, `negative_case`,
            and `mechanisms[mechanism]["scores"]`.
        mechanism: Which mechanism column to read, typically `full`,
            `description`, or `baseline`.
        min_score: Mean of the three judge scores at or above which a positive
            scenario passes.

    Returns:
        Mapping from scenario id to pass or fail.

    Raises:
        AdapterError: A scenario lacks an id, ids repeat, or a score is not
            numeric.
    """
    out: dict[str, bool] = {}
    for scenario in scenarios:
        raw_id = scenario.get("id")
        if not raw_id:
            raise AdapterError("scenario is missing an id")
        sid = str(raw_id)
        if sid in out:
            raise AdapterError(f"duplicate scenario id: {sid}")

        mech_data = scenario.get("mechanisms", {}).get(mechanism)
        if not isinstance(mech_data, Mapping) or "error" in mech_data:
            # Mechanism never ran, or ran and errored. Either way it produced
            # no evidence, and no evidence is not a pass.
            out[sid] = False
            continue

        raw_scores = mech_data.get("scores", {})
        if raw_scores is None or not isinstance(raw_scores, Mapping):
            # An explicit null is not a missing key: dict.get returns the stored
            # None rather than the default, so this used to crash on the next
            # attribute access instead of naming the malformed input.
            raise AdapterError(
                f"scenario {sid!r} has a malformed scores block, "
                f"expected an object, got {raw_scores!r}"
            )
        if raw_scores.get("judge_failed"):
            # A broken judge proves nothing, for either polarity.
            out[sid] = False
            continue

        triple = [
            _as_float(raw_scores.get(key, 0), f"scenario {sid!r} {key}")
            for key in _RULE_SCORE_KEYS
        ]
        # No inversion. eval-rule-activation.py tells the judge that 5 is the
        # correct-behavior end of the scale for negative cases too ("5 means
        # the response correctly did NOT activate the rule"), so the score
        # arrives already normalized. Inverting here would double-invert and
        # reward exactly the rules that fire when they should stay quiet. The
        # value this adapter adds is including negative cases in the task set
        # at all: eval-rule-activation.py's own verdict reads only positive
        # scenarios, using negative ones solely to count judge failures.
        out[sid] = statistics.fmean(triple) >= min_score
    return out


def pytest_results(junit_xml: str, *, on_skip: str = "fail") -> dict[str, bool]:
    """Map a pytest JUnit XML report to per-test pass or fail.

    Uses `--junitxml`, which is pytest core, so hook and script suites need no
    reporting plugin to reach the gate.

    Args:
        junit_xml: Contents of a pytest `--junitxml` file. Accepts either a
            `<testsuites>` root or a bare `<testsuite>` root; pytest emits the
            former, other runners emit the latter.
        on_skip: `fail` scores a skipped test as a failure, `exclude` drops it
            from the mapping. `fail` is the default because a skipped test
            demonstrated nothing. Prefer `exclude` only when skips are static,
            since a conditionally skipped test changes the task-id set between
            runs, which moves the split fingerprint and stops the gate.

    Returns:
        Mapping from `classname::name` node id to pass or fail.

    Raises:
        AdapterError: The XML will not parse, a case has no name, node ids
            repeat, or `on_skip` is unknown.
    """
    if on_skip not in _SKIP_POLICIES:
        raise AdapterError(
            f"on_skip must be one of {list(_SKIP_POLICIES)}, got {on_skip!r}"
        )
    try:
        root = ElementTree.fromstring(junit_xml)
    except ElementTree.ParseError as exc:
        raise AdapterError(f"could not parse JUnit XML: {exc}") from exc

    out: dict[str, bool] = {}
    for case in root.iter("testcase"):
        name = case.get("name")
        if not name:
            raise AdapterError("testcase is missing a name attribute")
        classname = case.get("classname")
        node_id = f"{classname}::{name}" if classname else name

        skipped = case.find("skipped") is not None
        if skipped and on_skip == "exclude":
            continue
        if node_id in out:
            raise AdapterError(f"duplicate test node id: {node_id}")
        failed = (
            skipped
            or case.find("failure") is not None
            or case.find("error") is not None
        )
        out[node_id] = not failed
    return out
