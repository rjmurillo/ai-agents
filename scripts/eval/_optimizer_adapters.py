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

# Named rather than repeated as a literal at each default, and not spelled as
# an index into the collection above. An index makes the order of a choice set
# load-bearing without saying so, and reordering it for help text would then
# silently change behaviour.
_DEFAULT_SKIP_POLICY = "fail"
_DEFAULT_REDUCER = "mean"
# Samples are repeated calls to one judge on one artifact, so a single
# erratic call is the shape being defended against and the median drops it
# outright. Runs are whole reports, where movement is spread rather than
# spiked, so `_DEFAULT_REDUCER` means them instead.
_DEFAULT_SAMPLE_REDUCER = "median"

_RULE_SCORE_KEYS = ("activation_score", "citation_score", "behavior_score")
# The judge is told "1-5 each" and `eval-rule-activation.py` clamps its own
# output to [0, 5]; the floor is 0 rather than 1 because `_clamp_score` maps a
# string, a None, or a negative number to 0, so 0 is a value the producer
# really emits and not just the bottom of the prompt's scale.
_MAX_RULE_SCORE = 5.0
# Each run is the fraction of a fixture's assertions that were satisfied.
_MAX_PASS_RATE = 1.0


class AdapterError(ValueError):
    """A scorer's output did not have the shape the adapter requires."""


def _as_float(value: object, context: str, *, lo: float, hi: float) -> float:
    """Coerce a score to float, refusing bools, non-numbers, and out-of-domain values.

    `isinstance(True, int)` is True in Python, so a bool would otherwise slip
    through as 1.0 or 0.0. A pass-rate list holding bools means the producer
    changed shape, and guessing at intent there hides the change.

    NaN and infinity are refused for a sharper reason: they quietly invert
    verdicts. Every comparison against NaN is False, so a NaN score makes a
    negative-case scenario pass; infinity clears any threshold, so it makes a
    fixture pass unconditionally. `json.loads` accepts the bare `NaN` and
    `Infinity` tokens, so neither is hypothetical.

    The bounds are the same argument one step further out. Both scales here
    are bounded and every producer says so, but a finite number outside the
    range does what infinity does, only quietly: it covers for a measurement
    that is missing. A rule scenario with no `behavior_score` and the other
    two at the legal maximum reduces below the bar and fails, which is the
    point. The same scenario with the other two at 6 passed. Callers pass
    their own domain rather than sharing a default, because the two scales
    differ and a shared default would be right for neither.

    The finiteness check is asked of floats only. `math.isfinite` converts its
    argument to float first, so an integer past 1.8e308 raises `OverflowError`
    there, and `OverflowError` is not one of the exceptions the CLI catches:
    the command printed a traceback and exited 1, which is this tool's REJECT
    verdict. An integer is never NaN and never infinite, so the question was
    only ever meaningful for floats. Skipping it for integers leaves them to
    the range check below, which compares an integer against a float exactly
    at any size, and leaves the final conversion safe because nothing that
    survives that check is large.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AdapterError(f"{context} must be numeric, got {value!r}")
    if isinstance(value, float) and not math.isfinite(value):
        raise AdapterError(f"{context} must be finite, got {value!r}")
    if not lo <= value <= hi:
        raise AdapterError(
            f"{context} must be between {lo} and {hi}, got {value!r}"
        )
    return float(value)


def agent_results(
    report: Mapping[str, Any],
    variant: str,
    *,
    reduce: str = _DEFAULT_REDUCER,
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
            not a mapping, a run value is not numeric or falls outside the
            [0, 1] a fraction can occupy, or `reduce` is unknown.
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
        if runs is None:
            # Variant never ran this fixture. Fail closed rather than
            # dropping the id.
            out[str(fixture_id)] = False
            continue
        if not isinstance(runs, Sequence) or isinstance(runs, str):
            raise AdapterError(
                f"fixture {fixture_id!r} variant {variant!r} must be a list "
                f"of scores, got {type(runs).__name__}"
            )
        if not runs:
            # Ran the fixture zero times. Same fail-closed path as never
            # having run it, but reached only after the value proved to be a
            # list, so `{}`, `""`, `0` and `False` are refused above rather
            # than scored as a measured loss.
            out[str(fixture_id)] = False
            continue
        values = [
            _as_float(
                v,
                f"fixture {fixture_id!r} variant {variant!r} run",
                lo=0.0,
                hi=_MAX_PASS_RATE,
            )
            for v in runs
        ]
        out[str(fixture_id)] = reducer(values) >= pass_threshold
    return out


def _rule_run_scores(
    scenarios: Sequence[Mapping[str, Any]],
    mechanism: str,
    *,
    reduce_samples: str = _DEFAULT_SAMPLE_REDUCER,
) -> dict[str, float | None]:
    """Score one run's scenarios, mapping each id to its judge mean or None.

    None means the run produced no evidence for that scenario: the mechanism
    never ran, ran and errored, or the judge itself failed. That is distinct
    from a low score, and keeping the two apart is what lets the multi-run
    reduction refuse a scenario that was measured in some runs and not others
    instead of averaging a hole.

    Both polarities read one normalized scale. `eval-rule-activation.py` builds
    the judge prompt so that 5 always means correct behavior, including for a
    negative case ("5 means the response correctly did NOT activate the rule").
    So a high score is a pass whether the rule was meant to fire or stay quiet,
    and this adapter must not invert.

    Two reductions stack here and they collapse different things. One run may
    score a scenario several times, one `score_samples` entry per judge call,
    and `reduce_samples` collapses those inside this run. `rule_results_multi`
    then collapses whole runs. Repeating the judge defends against one erratic
    call; repeating the run defends against a whole report landing on the far
    side of the bar. Neither subsumes the other, so both stay.

    Args:
        scenarios: Scored scenario records, each with `id`, `negative_case`,
            and `mechanisms[mechanism]["scores"]`.
        mechanism: Which mechanism column to read, typically `full`,
            `description`, or `baseline`.
        reduce_samples: How to collapse repeated judge samples for each score
            key. One of `mean`, `min`, `max`, `median`.

    Returns:
        Mapping from scenario id to its reduced judge mean, or None where this
        run produced no evidence for that scenario.

    Raises:
        AdapterError: A scenario is not an object, lacks an id, repeats an id,
            carries a malformed `mechanisms` or `scores` block, or holds a
            score that is not finite and numeric or falls outside the [0, 5]
            the judge is asked for and the producer clamps to.
    """
    if reduce_samples not in _REDUCERS:
        raise AdapterError(
            f"reduce_samples must be one of {sorted(_REDUCERS)}, "
            f"got {reduce_samples!r}"
        )
    reducer = _REDUCERS[reduce_samples]
    out: dict[str, float | None] = {}
    for scenario in scenarios:
        if not isinstance(scenario, Mapping):
            raise AdapterError(f"scenario must be an object, got {scenario!r}")
        raw_id = scenario.get("id")
        if not raw_id:
            raise AdapterError("scenario is missing an id")
        sid = str(raw_id)
        if sid in out:
            raise AdapterError(f"duplicate scenario id: {sid}")

        mechanisms = scenario.get("mechanisms", {})
        if not isinstance(mechanisms, Mapping):
            # An absent key keeps its fail-closed meaning of no evidence. A
            # present but malformed one is a broken input and says so, rather
            # than escaping as a bare AttributeError from inside a get chain.
            raise AdapterError(
                f"scenario {sid!r} has a malformed mechanisms block, "
                f"expected an object, got {mechanisms!r}"
            )
        mech_data = mechanisms.get(mechanism)
        if not isinstance(mech_data, Mapping) or "error" in mech_data:
            # Mechanism never ran, or ran and errored. Either way it produced
            # no evidence, and no evidence is not a pass.
            out[sid] = None
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
            out[sid] = None
            continue

        raw_samples = mech_data.get("score_samples")
        if raw_samples is None:
            samples: list[Mapping[str, Any]] = [raw_scores]
            missing = [key for key in _RULE_SCORE_KEYS if key not in raw_scores]
            if missing:
                # Defaulting an absent key to 0 put an unknown into the mean
                # beside two real measurements, which dilutes it rather than
                # refusing it. That reads as fail-closed only while the bar
                # sits above what the present maxima reach alone: two fives
                # and one absent key reduce to 3.33 and clear `--min-score
                # 3.0`. `eval-rule-activation.py` writes all three keys
                # unconditionally, so a mapping arriving here short of one did
                # not come from that producer intact. It is a claim about the
                # report, not about the candidate.
                raise AdapterError(
                    f"scenario {sid!r} is missing {len(missing)} of "
                    f"{len(_RULE_SCORE_KEYS)} rule scores: {', '.join(missing)}"
                )
        else:
            if (
                not isinstance(raw_samples, Sequence)
                or isinstance(raw_samples, (str, bytes))
                or not raw_samples
            ):
                raise AdapterError(
                    f"scenario {sid!r} score_samples must be a non-empty list"
                )
            samples = []
            judge_failed = False
            for index, sample in enumerate(raw_samples):
                if not isinstance(sample, Mapping):
                    raise AdapterError(
                        f"scenario {sid!r} score_samples[{index}] must be an object"
                    )
                if sample.get("judge_failed"):
                    # One broken call proves nothing, and reducing only the
                    # samples that survived would report a number gathered
                    # under conditions the report itself flagged as unsound.
                    judge_failed = True
                    break
                missing = [key for key in _RULE_SCORE_KEYS if key not in sample]
                if missing:
                    raise AdapterError(
                        f"scenario {sid!r} score_samples[{index}] missing "
                        f"{', '.join(missing)}"
                    )
                samples.append(sample)
            if judge_failed:
                out[sid] = None
                continue

        # Reduce per key across samples, then mean the three, so a judge that
        # is erratic on one dimension cannot be rescued by another dimension's
        # spread. Indexing is safe: both branches above refuse a missing key
        # rather than defaulting it, so there is no silent zero left here.
        triple = [
            reducer(
                [
                    _as_float(
                        sample[key],
                        f"scenario {sid!r} {key}",
                        lo=0.0,
                        hi=_MAX_RULE_SCORE,
                    )
                    for sample in samples
                ]
            )
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
        out[sid] = statistics.fmean(triple)
    return out


def rule_results(
    scenarios: Sequence[Mapping[str, Any]],
    mechanism: str,
    *,
    min_score: float = DEFAULT_MIN_ACTIVATION_SCORE,
    reduce: str = _DEFAULT_SAMPLE_REDUCER,
) -> dict[str, bool]:
    """Map one run's rule-activation scenarios to per-scenario pass or fail.

    Both polarities read one normalized scale. `eval-rule-activation.py` builds
    the judge prompt so that 5 always means correct behavior, including for a
    negative case ("5 means the response correctly did NOT activate the rule").
    So a high score is a pass whether the rule was meant to fire or stay quiet,
    and this adapter must not invert.

    What it does add is including negative cases at all. That evaluator's own
    verdict averages positive scenarios only and reads negative ones solely to
    count judge failures, so a rule that over-fires can pass there. Here it
    loses.

    One run of an LLM judge is a noisy measurement; see `rule_results_multi`
    for reducing several. This entry point is the single-run case and stays
    exact for it.

    Args:
        scenarios: Scored scenario records, each with `id`, `negative_case`,
            and `mechanisms[mechanism]["scores"]`.
        mechanism: Which mechanism column to read, typically `full`,
            `description`, or `baseline`.
        min_score: Mean of the three judge scores at or above which a scenario
            passes.
        reduce: How to collapse repeated judge samples for each score key. One
            of `mean`, `min`, `max`, `median`.

    Returns:
        Mapping from scenario id to pass or fail.

    Raises:
        AdapterError: A scenario is not an object, lacks an id, repeats an
            id, carries a malformed `mechanisms` or `scores` block, or holds a
            score that is not finite and numeric or falls outside the [0, 5]
            the judge is asked for and the producer clamps to.
    """
    return {
        sid: score is not None and score >= min_score
        for sid, score in _rule_run_scores(
            scenarios, mechanism, reduce_samples=reduce
        ).items()
    }


def rule_results_multi(
    runs: Sequence[Sequence[Mapping[str, Any]]],
    mechanism: str,
    *,
    min_score: float = DEFAULT_MIN_ACTIVATION_SCORE,
    reduce: str = _DEFAULT_REDUCER,
    reduce_samples: str = _DEFAULT_SAMPLE_REDUCER,
) -> dict[str, bool]:
    """Reduce a rule scenario across repeated runs, then threshold once.

    The rule path is the only one of the three adapters with no noise defense:
    `pytest_results` is deterministic and `agent_results` already averages over
    runs. ADR-087 Open Requirement 6 measured what that costs rather than
    assuming it. Scoring identical rule text twice moved 13 of 24 tasks and 5
    of them across the pass threshold, with mean absolute movement of 0.49
    points on the five-point judge scale. The two held-out gains behind the
    live run's false accept were the two largest movements in that benchmark.

    A run here is a whole report, one per invocation of
    `eval-rule-activation.py`, because that is how the ADR's own paired
    measurement was gathered and it needs no change to the producer.

    The reduction is over scores, not over verdicts, so it matches
    `agent_results`: collapse the runs to one number, then apply the bar once.
    Thresholding per run and voting would discard the distance from the bar,
    which is the only thing that says whether a disagreement was close.

    Args:
        runs: One scenario sequence per run. Every run must score the same
            scenario ids.
        mechanism: Which mechanism column to read.
        min_score: Reduced value at or above which a scenario passes.
        reduce: How to collapse a scenario's runs. One of `mean`, `min`,
            `max`, `median`.
        reduce_samples: How to collapse repeated judge samples inside each run,
            applied before `reduce` collapses the runs.

    Returns:
        Mapping from scenario id to pass or fail.

    Raises:
        AdapterError: `reduce` is unknown, `runs` is empty, the runs do not
            agree on which scenarios they scored, a scenario has evidence in
            some runs but not others, or any run is malformed in the ways
            `rule_results` refuses.
    """
    if reduce not in _REDUCERS:
        raise AdapterError(
            f"reduce must be one of {sorted(_REDUCERS)}, got {reduce!r}"
        )
    if not runs:
        raise AdapterError("reducing rule scenarios needs at least one run, got 0")

    scored = [
        _rule_run_scores(run, mechanism, reduce_samples=reduce_samples)
        for run in runs
    ]
    expected = set(scored[0])
    for index, run_scores in enumerate(scored[1:], start=2):
        if set(run_scores) != expected:
            differing = sorted(expected.symmetric_difference(run_scores))
            raise AdapterError(
                f"every run must score the same scenarios; run {index} of "
                f"{len(scored)} differs on: {', '.join(differing)}"
            )

    reducer = _REDUCERS[reduce]
    out: dict[str, bool] = {}
    for sid in scored[0]:
        values = [run_scores[sid] for run_scores in scored]
        present = [value for value in values if value is not None]
        if not present:
            # Uniform absence keeps the single-run meaning: no evidence is not
            # a pass. This is the only shape a one-run call can reach, which is
            # what makes `rule_results_multi([s]) == rule_results(s)` hold.
            out[sid] = False
            continue
        if len(present) != len(values):
            # Scoring this False would be worse than useless. A judge error on
            # the incumbent's run reads as a failing scenario, so a candidate
            # that merely ran cleanly looks like a fail-to-pass improvement:
            # the spurious accept the gate exists to prevent, arriving through
            # the scorer. Dropping the bad run instead would reduce over a
            # different sample size per scenario without saying so. Neither is
            # a measurement.
            raise AdapterError(
                f"scenario {sid!r} has evidence in some runs but not others "
                f"({len(present)} of {len(values)}); "
                f"the runs it is missing from measured nothing about it"
            )
        out[sid] = reducer(present) >= min_score
    return out


def pytest_results(junit_xml: str, *, on_skip: str = _DEFAULT_SKIP_POLICY) -> dict[str, bool]:
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
            because dropping a task is not free. A conditionally skipped test
            changes the task-id set between runs while the split was drawn once
            from the full set, so a dropped id in the held-out group makes the
            gate charge a consultation and report `REJECT` at exit 1 with
            `compared: false`, and a dropped id outside it leaves the drift
            invisible.
            `exclude` drops only a testcase whose skip stands alone: one that
            also carries a failure or an error did demonstrate something and
            is scored as a failure under either policy.

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
        broken = (
            case.find("failure") is not None or case.find("error") is not None
        )
        # Both conditions, because `exclude` rests on a skipped test having
        # demonstrated nothing, and one that also carries a failure or an
        # error demonstrated exactly that. Stock pytest emits the pair when a
        # fixture teardown raises behind a skipped test, so dropping on the
        # skip alone let a broken teardown leave the denominator.
        if skipped and not broken and on_skip == "exclude":
            continue
        if node_id in out:
            raise AdapterError(f"duplicate test node id: {node_id}")
        out[node_id] = not (skipped or broken)
    return out
