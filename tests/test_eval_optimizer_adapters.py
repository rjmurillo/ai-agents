"""Tests for `scripts/eval/_optimizer_adapters.py`.

The adapters are the reason the held-out gate generalizes past skills. Each
one turns a different existing scorer's output into the single `{task_id:
bool}` mapping `_optimizer_core.score` consumes, so agents, rules, and hooks
all reach the same gate.

Every adapter fails closed: an unreadable, errored, or missing outcome scores
as a failure rather than being dropped, because a dropped task silently
shrinks the denominator and inflates the score.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "eval"))

from _optimizer_adapters import (  # noqa: E402
    DEFAULT_MIN_ACTIVATION_SCORE,
    AdapterError,
    agent_results,
    pytest_results,
    rule_results,
)

# ---------------------------------------------------------------------------
# agent_results
# ---------------------------------------------------------------------------


def _report(rates: dict) -> dict:
    return {"per_fixture_pass_rates": rates}


class TestNonFiniteScores:
    """NaN and infinity must not be read as outcomes.

    Adversarial review found both slipping through: NaN made a scenario pass
    because every comparison against it is False, and infinity made a fixture
    pass unconditionally. Both arrive from real producers, since JSON's own
    parser accepts the bare tokens, and either one silently rewrites a verdict
    the gate is supposed to be measuring.
    """

    def test_nan_in_an_agent_rate_is_refused(self):
        with pytest.raises(AdapterError, match="finite"):
            agent_results(_report({"C001": {"agent": [float("nan")]}}), "agent")

    def test_infinity_in_an_agent_rate_is_refused(self):
        with pytest.raises(AdapterError, match="finite"):
            agent_results(_report({"C001": {"agent": [float("inf")]}}), "agent")

    def test_negative_infinity_is_refused(self):
        with pytest.raises(AdapterError, match="finite"):
            agent_results(_report({"C001": {"agent": [float("-inf")]}}), "agent")

    def test_nan_parsed_from_real_json_is_refused(self):
        """json.loads accepts the bare NaN token, so this is a live path."""
        report = json.loads('{"per_fixture_pass_rates": {"C001": {"agent": [NaN]}}}')
        with pytest.raises(AdapterError, match="finite"):
            agent_results(report, "agent")

    def test_infinity_does_not_pass_a_fixture(self):
        """Before the fix, inf >= any threshold, so the fixture passed."""
        with pytest.raises(AdapterError):
            agent_results(_report({"C001": {"agent": [float("inf")]}}), "agent")

    def test_nan_in_a_rule_score_is_refused(self):
        scenarios = [
            {
                "id": "S1",
                "mechanisms": {
                    "m": {
                        "scores": {
                            "activation_score": float("nan"),
                            "citation_score": 5,
                            "behavior_score": 5,
                        }
                    }
                },
            }
        ]
        with pytest.raises(AdapterError, match="finite"):
            rule_results(scenarios, "m")

    def test_an_ordinary_finite_score_still_passes(self):
        assert agent_results(_report({"C001": {"agent": [1.0]}}), "agent") == {"C001": True}


class TestNullScoresBlock:
    """An explicit JSON null is not a missing key.

    dict.get returns the stored None rather than the default, so a scenario
    carrying "scores": null crashed with an uncaught AttributeError instead of
    a named adapter error.
    """

    def test_a_null_scores_block_is_refused(self):
        with pytest.raises(AdapterError, match="scores"):
            rule_results([{"id": "S1", "mechanisms": {"m": {"scores": None}}}], "m")

    def test_a_non_mapping_scores_block_is_refused(self):
        with pytest.raises(AdapterError, match="scores"):
            rule_results([{"id": "S1", "mechanisms": {"m": {"scores": [1, 2, 3]}}}], "m")

    def test_a_missing_scores_block_still_scores_zero(self):
        """Absent is different from malformed and keeps its existing meaning."""
        assert rule_results([{"id": "S1", "mechanisms": {"m": {}}}], "m") == {"S1": False}


class TestAgentResults:
    def test_reads_the_requested_variant(self):
        report = _report(
            {
                "C001": {"agent": [1.0, 1.0], "baseline": [0.0, 0.0]},
                "C002": {"agent": [0.0, 0.0], "baseline": [1.0, 1.0]},
            }
        )
        assert agent_results(report, "agent") == {"C001": True, "C002": False}
        assert agent_results(report, "baseline") == {"C001": False, "C002": True}

    def test_default_threshold_demands_every_run_clean(self):
        """A fixture that passed twice and half-passed once is not a pass."""
        report = _report({"C001": {"agent": [1.0, 0.5, 1.0]}})
        assert agent_results(report, "agent") == {"C001": False}

    def test_lower_threshold_admits_a_partial_fixture(self):
        report = _report({"C001": {"agent": [1.0, 0.5, 1.0]}})
        assert agent_results(report, "agent", pass_threshold=0.8) == {"C001": True}

    def test_threshold_is_inclusive(self):
        report = _report({"C001": {"agent": [0.5, 0.5]}})
        assert agent_results(report, "agent", pass_threshold=0.5) == {"C001": True}

    def test_min_reduction_punishes_one_bad_run(self):
        report = _report({"C001": {"agent": [1.0, 1.0, 0.0]}})
        assert agent_results(report, "agent", reduce="min", pass_threshold=1.0) == {
            "C001": False
        }

    def test_max_reduction_rewards_one_good_run(self):
        report = _report({"C001": {"agent": [0.0, 0.0, 1.0]}})
        assert agent_results(report, "agent", reduce="max", pass_threshold=1.0) == {
            "C001": True
        }

    def test_median_reduction_ignores_a_single_outlier(self):
        report = _report({"C001": {"agent": [1.0, 1.0, 0.0]}})
        assert agent_results(report, "agent", reduce="median", pass_threshold=1.0) == {
            "C001": True
        }

    def test_median_of_an_even_sample_averages_the_middle_pair(self):
        report = _report({"C001": {"agent": [0.0, 0.4, 0.6, 1.0]}})
        assert agent_results(report, "agent", reduce="median", pass_threshold=0.5) == {
            "C001": True
        }

    def test_missing_variant_for_a_fixture_scores_as_failure(self):
        """A fixture the variant never ran on must not vanish from the split."""
        report = _report({"C001": {"baseline": [1.0]}})
        assert agent_results(report, "agent") == {"C001": False}

    def test_empty_run_list_scores_as_failure(self):
        report = _report({"C001": {"agent": []}})
        assert agent_results(report, "agent") == {"C001": False}

    def test_empty_report_yields_empty_mapping(self):
        assert agent_results(_report({}), "agent") == {}

    def test_rejects_a_report_without_the_rates_key(self):
        with pytest.raises(AdapterError, match="per_fixture_pass_rates"):
            agent_results({}, "agent")

    def test_rejects_non_mapping_rates(self):
        with pytest.raises(AdapterError, match="must be a mapping"):
            agent_results({"per_fixture_pass_rates": [["C001", 1.0]]}, "agent")

    def test_rejects_an_unknown_reduction(self):
        report = _report({"C001": {"agent": [1.0]}})
        with pytest.raises(AdapterError, match="reduce"):
            agent_results(report, "agent", reduce="mode")

    def test_rejects_a_non_numeric_run_value(self):
        report = _report({"C001": {"agent": ["1.0"]}})
        with pytest.raises(AdapterError, match="numeric"):
            agent_results(report, "agent")

    def test_rejects_a_non_mapping_fixture_entry(self):
        with pytest.raises(AdapterError, match="mapping"):
            agent_results(_report({"C001": [1.0]}), "agent")

    def test_accepts_integer_run_values(self):
        report = _report({"C001": {"agent": [1, 1]}})
        assert agent_results(report, "agent") == {"C001": True}

    def test_rejects_a_boolean_run_value(self):
        """`True` is an int in Python; a pass-rate list of bools is a shape bug."""
        report = _report({"C001": {"agent": [True]}})
        with pytest.raises(AdapterError, match="numeric"):
            agent_results(report, "agent")


# ---------------------------------------------------------------------------
# rule_results
# ---------------------------------------------------------------------------


def _scenario(sid: str, mech: str, triple: tuple, *, negative: bool = False, **kw) -> dict:
    scores = {
        "activation_score": triple[0],
        "citation_score": triple[1],
        "behavior_score": triple[2],
    }
    scores.update(kw)
    return {
        "id": sid,
        "negative_case": negative,
        "mechanisms": {mech: {"scores": scores}},
    }


class TestRuleResults:
    def test_positive_scenario_passes_above_the_activation_floor(self):
        scenarios = [_scenario("S1", "full", (4, 4, 4))]
        assert rule_results(scenarios, "full") == {"S1": True}

    def test_positive_scenario_fails_below_the_activation_floor(self):
        scenarios = [_scenario("S1", "full", (3, 3, 3))]
        assert rule_results(scenarios, "full") == {"S1": False}

    def test_activation_floor_is_inclusive(self):
        scenarios = [_scenario("S1", "full", (3.5, 3.5, 3.5))]
        assert rule_results(scenarios, "full") == {"S1": True}

    def test_negative_scenario_passes_when_the_rule_stays_quiet(self):
        """The judge already normalizes a negative case, so do not invert.

        eval-rule-activation.py builds the judge prompt with "(negative case: 5
        means the response correctly did NOT activate the rule and gave generic
        advice instead)". A high score therefore already means correct
        behavior for both polarities. Inverting here would double-invert and
        punish exactly the rules that behave.
        """
        scenarios = [_scenario("S1", "full", (5, 5, 5), negative=True)]
        assert rule_results(scenarios, "full") == {"S1": True}

    def test_negative_scenario_fails_when_the_rule_fires_anyway(self):
        """A low negative-case score means the rule fired when it should not."""
        scenarios = [_scenario("S1", "full", (1, 1, 1), negative=True)]
        assert rule_results(scenarios, "full") == {"S1": False}

    def test_judge_failure_scores_as_failure(self):
        scenarios = [_scenario("S1", "full", (5, 5, 5), judge_failed=True)]
        assert rule_results(scenarios, "full") == {"S1": False}

    def test_judge_failure_also_fails_a_negative_case(self):
        """A broken judge proves nothing for either polarity."""
        scenarios = [_scenario("S1", "full", (5, 5, 5), negative=True, judge_failed=True)]
        assert rule_results(scenarios, "full") == {"S1": False}

    def test_negative_and_positive_use_the_same_threshold(self):
        """Both polarities read the same normalized scale, so one floor fits."""
        scenarios = [
            _scenario("POS", "full", (3.5, 3.5, 3.5)),
            _scenario("NEG", "full", (3.5, 3.5, 3.5), negative=True),
        ]
        assert rule_results(scenarios, "full") == {"POS": True, "NEG": True}

    def test_judge_prompt_still_normalizes_negative_cases(self):
        """Drift guard for the semantics this adapter depends on.

        If eval-rule-activation.py ever stops telling the judge that 5 is the
        correct-behavior end of the scale for negative cases, the no-inversion
        policy above becomes wrong and this test must fail loudly.
        """
        source = (
            Path(__file__).resolve().parents[1]
            / "scripts"
            / "eval"
            / "eval-rule-activation.py"
        ).read_text(encoding="utf-8")
        assert "negative case: 5 means the response correctly did NOT activate" in source

    def test_mechanism_error_scores_as_failure(self):
        scenarios = [_scenario("S1", "full", (5, 5, 5))]
        scenarios[0]["mechanisms"]["full"]["error"] = "rate limited"
        assert rule_results(scenarios, "full") == {"S1": False}

    def test_missing_mechanism_scores_as_failure(self):
        scenarios = [_scenario("S1", "description", (5, 5, 5))]
        assert rule_results(scenarios, "full") == {"S1": False}

    def test_missing_score_keys_count_as_zero(self):
        scenarios = [{"id": "S1", "negative_case": False, "mechanisms": {"full": {"scores": {}}}}]
        assert rule_results(scenarios, "full") == {"S1": False}

    def test_custom_floor_is_honored(self):
        scenarios = [_scenario("S1", "full", (3, 3, 3))]
        assert rule_results(scenarios, "full", min_score=3.0) == {"S1": True}

    def test_empty_scenarios_yield_empty_mapping(self):
        assert rule_results([], "full") == {}

    def test_rejects_a_scenario_without_an_id(self):
        with pytest.raises(AdapterError, match="id"):
            rule_results([{"negative_case": False, "mechanisms": {}}], "full")

    def test_rejects_duplicate_scenario_ids(self):
        scenarios = [_scenario("S1", "full", (4, 4, 4)), _scenario("S1", "full", (1, 1, 1))]
        with pytest.raises(AdapterError, match="duplicate"):
            rule_results(scenarios, "full")

    def test_rejects_a_non_numeric_score(self):
        scenarios = [_scenario("S1", "full", ("high", 4, 4))]
        with pytest.raises(AdapterError, match="numeric"):
            rule_results(scenarios, "full")

    def test_default_floor_tracks_the_rule_activation_scorer(self):
        """The floor is duplicated from a hyphenated CLI module; catch drift."""
        source = (
            Path(__file__).resolve().parent.parent
            / "scripts"
            / "eval"
            / "eval-rule-activation.py"
        ).read_text(encoding="utf-8")
        match = re.search(r"^MIN_ACTIVATION_SCORE\s*=\s*([0-9.]+)", source, re.MULTILINE)
        assert match, "MIN_ACTIVATION_SCORE not found in eval-rule-activation.py"
        assert float(match.group(1)) == DEFAULT_MIN_ACTIVATION_SCORE


# ---------------------------------------------------------------------------
# pytest_results
# ---------------------------------------------------------------------------


def _junit(cases: str, *, suite_attrs: str = "") -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        f"<testsuites><testsuite name='pytest'{suite_attrs}>{cases}</testsuite></testsuites>"
    )


class TestPytestResults:
    def test_passing_case_maps_to_true(self):
        xml = _junit('<testcase classname="tests.test_a" name="test_x"/>')
        assert pytest_results(xml) == {"tests.test_a::test_x": True}

    def test_failing_case_maps_to_false(self):
        xml = _junit(
            '<testcase classname="tests.test_a" name="test_x">'
            '<failure message="boom">trace</failure></testcase>'
        )
        assert pytest_results(xml) == {"tests.test_a::test_x": False}

    def test_errored_case_maps_to_false(self):
        xml = _junit(
            '<testcase classname="tests.test_a" name="test_x">'
            '<error message="fixture blew up"/></testcase>'
        )
        assert pytest_results(xml) == {"tests.test_a::test_x": False}

    def test_skipped_case_fails_by_default(self):
        """A skipped test demonstrated nothing, so it cannot count as a pass."""
        xml = _junit(
            '<testcase classname="tests.test_a" name="test_x">'
            '<skipped message="needs network"/></testcase>'
        )
        assert pytest_results(xml) == {"tests.test_a::test_x": False}

    def test_skipped_case_can_be_excluded(self):
        xml = _junit(
            '<testcase classname="tests.test_a" name="test_x">'
            '<skipped message="needs network"/></testcase>'
            '<testcase classname="tests.test_a" name="test_y"/>'
        )
        assert pytest_results(xml, on_skip="exclude") == {"tests.test_a::test_y": True}

    def test_parameterized_ids_stay_distinct(self):
        xml = _junit(
            '<testcase classname="tests.test_a" name="test_x[1]"/>'
            '<testcase classname="tests.test_a" name="test_x[2]">'
            "<failure/></testcase>"
        )
        assert pytest_results(xml) == {
            "tests.test_a::test_x[1]": True,
            "tests.test_a::test_x[2]": False,
        }

    def test_reads_multiple_suites(self):
        xml = (
            "<testsuites>"
            "<testsuite name='a'><testcase classname='tests.test_a' name='test_x'/></testsuite>"
            "<testsuite name='b'><testcase classname='tests.test_b' name='test_y'/></testsuite>"
            "</testsuites>"
        )
        assert pytest_results(xml) == {
            "tests.test_a::test_x": True,
            "tests.test_b::test_y": True,
        }

    def test_reads_a_bare_testsuite_root(self):
        xml = (
            "<testsuite name='pytest'>"
            "<testcase classname='tests.test_a' name='test_x'/></testsuite>"
        )
        assert pytest_results(xml) == {"tests.test_a::test_x": True}

    def test_case_without_classname_uses_the_name_alone(self):
        xml = _junit('<testcase name="test_x"/>')
        assert pytest_results(xml) == {"test_x": True}

    def test_empty_suite_yields_empty_mapping(self):
        assert pytest_results(_junit("")) == {}

    def test_rejects_malformed_xml(self):
        with pytest.raises(AdapterError, match="parse"):
            pytest_results("<testsuite><testcase")

    def test_rejects_a_case_without_a_name(self):
        with pytest.raises(AdapterError, match="name"):
            pytest_results(_junit('<testcase classname="tests.test_a"/>'))

    def test_rejects_duplicate_node_ids(self):
        """Duplicate ids would silently collapse two tests into one gate signal."""
        xml = _junit(
            '<testcase classname="tests.test_a" name="test_x"/>'
            '<testcase classname="tests.test_a" name="test_x"><failure/></testcase>'
        )
        with pytest.raises(AdapterError, match="duplicate"):
            pytest_results(xml)

    def test_rejects_an_unknown_skip_policy(self):
        with pytest.raises(AdapterError, match="on_skip"):
            pytest_results(_junit(""), on_skip="ignore")
