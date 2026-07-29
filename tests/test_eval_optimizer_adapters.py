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

_EVAL_DIR = Path(__file__).resolve().parent.parent / "scripts" / "eval"
# Scope the mutation to the module load and remove it afterward so a sibling
# test cannot pick up an importable name it never asked for, and so repeated
# imports cannot stack duplicate entries.
_path_added = str(_EVAL_DIR) not in sys.path
try:
    if _path_added:
        sys.path.insert(0, str(_EVAL_DIR))

    from _optimizer_adapters import (  # noqa: E402
        DEFAULT_MIN_ACTIVATION_SCORE,
        AdapterError,
        agent_results,
        pytest_results,
        rule_results,
        rule_results_multi,
    )
finally:
    if _path_added and str(_EVAL_DIR) in sys.path:
        sys.path.remove(str(_EVAL_DIR))

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
        """Renamed contract: an absent block is refused like an incomplete one.

        This used to reduce to False. The adapter and the command-layer
        degraded scan now agree that a mapping the reduction cannot read in
        full is a claim about the report, so the CLI verdict for this input
        is unchanged and only the direct-adapter contract moved.
        """
        with pytest.raises(AdapterError, match="missing"):
            rule_results([{"id": "S1", "mechanisms": {"m": {}}}], "m")


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

    @pytest.mark.parametrize("runs", [0.9, {"score": 0.9}, "0.9"])
    def test_a_run_list_that_is_not_a_list_is_refused(self, runs):
        """A bare score, a dict, and a string all iterate or index wrongly.

        A string is the trap: it is a Sequence, so a bare `isinstance` check
        admits it and then `mean` over its characters raises somewhere far
        from the malformed file. Refusing here names the fixture.
        """
        report = _report({"C001": {"agent": runs}})
        with pytest.raises(AdapterError, match="must be a list of scores"):
            agent_results(report, "agent")

    def test_an_empty_run_list_is_refused(self):
        """Empty means no completed measurement was taken."""
        report = _report({"C001": {"agent": []}})
        with pytest.raises(AdapterError, match="no completed runs"):
            agent_results(report, "agent")

    @pytest.mark.parametrize("runs", [{}, "", 0, 0.0, False])
    def test_a_falsy_run_list_that_is_not_a_list_is_still_refused(self, runs):
        """Emptiness was tested before type, so falsy junk scored instead of refusing.

        The sibling refusal test above parametrizes only truthy malformed
        values, which is why this hid. `{}`, `""`, `0`, `0.0` and `False` are
        not "the variant never ran this fixture"; they are a malformed file.
        Scoring them `False` reads as a measured loss, so a corrupt incumbent
        becomes candidate improvement the gate then certifies.

        `None` and `[]` are covered by the two tests either side of this one.
        """
        report = _report({"C001": {"agent": runs}})
        with pytest.raises(AdapterError, match="must be a list of scores"):
            agent_results(report, "agent")

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

    def test_missing_variant_for_a_fixture_is_refused(self):
        """A fixture the variant never ran on must not vanish from the split."""
        report = _report({"C001": {"baseline": [1.0]}})
        with pytest.raises(AdapterError, match="no completed runs"):
            agent_results(report, "agent")

    def test_empty_run_list_is_not_a_measurement(self):
        report = _report({"C001": {"agent": []}})
        with pytest.raises(AdapterError, match="no completed runs"):
            agent_results(report, "agent")

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
        """Renamed contract: an empty mapping is refused, not scored as zero."""
        scenarios = [{"id": "S1", "negative_case": False, "mechanisms": {"full": {"scores": {}}}}]
        with pytest.raises(AdapterError, match="missing"):
            rule_results(scenarios, "full")

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

    def test_errored_case_is_refused(self):
        xml = _junit(
            '<testcase classname="tests.test_a" name="test_x">'
            '<error message="fixture blew up"/></testcase>'
        )
        with pytest.raises(AdapterError, match="errored"):
            pytest_results(xml)

    def test_skipped_case_is_refused(self):
        """A skipped test demonstrated nothing, so it cannot count as a pass."""
        xml = _junit(
            '<testcase classname="tests.test_a" name="test_x">'
            '<skipped message="needs network"/></testcase>'
        )
        with pytest.raises(AdapterError, match="skipped"):
            pytest_results(xml)

    def test_skipped_case_is_refused_under_exclude(self):
        xml = _junit(
            '<testcase classname="tests.test_a" name="test_x">'
            '<skipped message="needs network"/></testcase>'
            '<testcase classname="tests.test_a" name="test_y"/>'
        )
        with pytest.raises(AdapterError, match="skipped"):
            pytest_results(xml, on_skip="exclude")

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


class TestMalformedScenarioShapes:
    """Every level of the scenario shape has to fail as AdapterError.

    The `scores` block was hardened earlier in this branch but the two levels
    above it were not, so a malformed `mechanisms` value or a scenario that is
    not an object still escaped as a bare AttributeError from inside a
    dict.get chain. A raw AttributeError names neither the scenario nor the
    field, which is the whole reason AdapterError exists.
    """

    @pytest.mark.parametrize("mechanisms", [None, [], "x", 3])
    def test_a_non_mapping_mechanisms_block_is_an_adapter_error(self, mechanisms):
        with pytest.raises(AdapterError, match="mechanisms"):
            rule_results([{"id": "S1", "mechanisms": mechanisms}], "m")

    @pytest.mark.parametrize("scenario", [None, [], "x", 3])
    def test_a_non_mapping_scenario_is_an_adapter_error(self, scenario):
        with pytest.raises(AdapterError, match="scenario"):
            rule_results([scenario], "m")

    def test_an_absent_mechanisms_key_still_means_no_evidence(self):
        """Absent is not malformed. It keeps its fail-closed meaning."""
        assert rule_results([{"id": "S1"}], "m") == {"S1": False}

    def test_the_error_names_the_scenario(self):
        with pytest.raises(AdapterError, match="S7"):
            rule_results([{"id": "S7", "mechanisms": "bad"}], "m")


class TestASkipThatCarriesAFailureIsStillAFailure:
    """`exclude` dropped testcases that had already proved something.

    The policy exists because a skipped test demonstrated nothing, so counting
    it as a failure punishes a candidate for a test that never ran. That
    argument holds only for a testcase whose sole child is `<skipped>`. The
    early return did not check, so a testcase carrying both a skip and an
    error was dropped along with the error.

    The overlap is not hypothetical and not a reading of pytest's source. A
    fixture whose teardown raises, in front of a test that skips, makes stock
    pytest emit both children under one `<testcase>`:

        <testcase classname="test_probe" name="test_skips_then_teardown_errors">
          <skipped type="pytest.skip" message="conditionally skipped">...</skipped>
          <error message='failed on teardown with "RuntimeError: ..."'>...</error>
        </testcase>

    Under `exclude` that testcase left the mapping entirely, so a broken
    teardown never reached the gate and never counted against the candidate.
    This is the fail-open the module docstring says no adapter has: the
    denominator shrank and the score rose.
    """

    REAL = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<testsuites name="pytest tests"><testsuite name="pytest" errors="1" '
        'failures="0" skipped="2" tests="3">'
        '<testcase classname="test_probe" name="test_skips_then_teardown_errors">'
        '<skipped type="pytest.skip" message="conditionally skipped">skipped</skipped>'
        '<error message="failed on teardown">RuntimeError</error></testcase>'
        '<testcase classname="test_probe" name="test_plain_skip">'
        '<skipped type="pytest.skip" message="just skipped">skipped</skipped>'
        "</testcase></testsuite></testsuites>"
    )

    def _one(self, children):
        return _junit(f'<testcase classname="t" name="x">{children}</testcase>')

    def test_a_skip_carrying_an_error_is_refused(self):
        xml = self._one("<skipped/><error message='teardown'/>")
        with pytest.raises(AdapterError, match="skipped"):
            pytest_results(xml, on_skip="exclude")

    def test_a_skip_carrying_a_failure_is_refused(self):
        xml = self._one("<skipped/><failure message='assert'/>")
        with pytest.raises(AdapterError, match="skipped"):
            pytest_results(xml, on_skip="exclude")

    def test_a_plain_skip_is_refused_under_exclude(self):
        with pytest.raises(AdapterError, match="skipped"):
            pytest_results(self._one("<skipped/>"), on_skip="exclude")

    def test_a_plain_skip_is_refused_under_the_default_policy(self):
        with pytest.raises(AdapterError, match="skipped"):
            pytest_results(self._one("<skipped/>"), on_skip="fail")

    def test_a_skip_carrying_an_error_is_refused_under_the_default_policy(self):
        xml = self._one("<skipped/><error message='teardown'/>")
        with pytest.raises(AdapterError, match="skipped"):
            pytest_results(xml, on_skip="fail")

    def test_a_passing_test_is_still_kept_under_exclude(self):
        assert pytest_results(self._one(""), on_skip="exclude") == {"t::x": True}

    def test_an_error_without_a_skip_is_refused_under_exclude(self):
        xml = self._one("<error message='teardown'/>")
        with pytest.raises(AdapterError, match="errored"):
            pytest_results(xml, on_skip="exclude")

    def test_the_report_stock_pytest_actually_emits_is_refused(self):
        """The exact shape observed from a real `--junitxml` run."""
        with pytest.raises(AdapterError, match="skipped"):
            pytest_results(self.REAL, on_skip="exclude")

    def test_that_same_report_is_refused_under_the_default_policy(self):
        with pytest.raises(AdapterError, match="skipped"):
            pytest_results(self.REAL, on_skip="fail")


class TestAScoreOutsideItsDomainCannotCoverForAMissingOne:
    """The documented range is what makes a missing measurement fail closed.

    `_as_float` checked type and finiteness and stopped there. Both scales are
    bounded and say so: `eval-rule-activation.py` grades three dimensions 1-5,
    tells the judge "1-5 each" in the prompt, and clamps its own output to
    [0, 5]; the README repeats the range; `agent_results` documents each run
    as "the fraction of that fixture's assertions satisfied", which is [0, 1].
    Every producer agreed on a domain that the one reader never enforced, and
    a file can reach the adapter without passing through the producer that
    clamps.

    Inside the domain the fail-closed property looked like it already held. A
    rule scenario missing `behavior_score`, with the other two at the legal
    maximum of 5, reduces to 3.33 and fails against the 3.5 bar. That reading
    was too generous to the design: 3.33 clears `--min-score 3.0`, which is a
    legal value of a documented flag, so the property held at the default bar
    and nowhere below 3.34. Partial mappings are now refused outright rather
    than reduced, so what this class still proves is narrower and true: an
    out-of-range value must not be accepted at all. Measured before that fix,
    a scenario missing one key with the other two at 6 reduced to 4.0 and
    passed, and a scenario carrying nothing but `activation_score` at 11
    passed as well.

    So this is enforcement of a contract already written in three places, not
    a new one. It also removes the reduction's order dependence: the values
    large enough to make `fsum` overflow are outside every domain here.
    """

    def _scen(self, **scores):
        return [{"id": "S", "mechanisms": {"full": {"scores": scores}}}]

    def test_a_missing_score_cannot_be_covered_by_out_of_range_ones(self):
        with pytest.raises(AdapterError, match="S"):
            rule_results(self._scen(activation_score=6, citation_score=6), "full")

    def test_a_scenario_carrying_one_inflated_score_is_refused(self):
        with pytest.raises(AdapterError):
            rule_results(self._scen(activation_score=11), "full")

    def test_a_missing_score_still_fails_closed_inside_the_domain(self):
        """Renamed contract: the mapping is refused before the bar is applied.

        This asserted False, which was the right verdict reached by the wrong
        route. The bar only cleared it because 3.5 happens to sit above 3.33.
        """
        with pytest.raises(AdapterError, match="missing"):
            rule_results(self._scen(activation_score=5, citation_score=5), "full")

    def test_the_legal_maximum_still_passes(self):
        got = rule_results(
            self._scen(activation_score=5, citation_score=5, behavior_score=5), "full"
        )
        assert got == {"S": True}

    def test_the_legal_minimum_is_still_accepted(self):
        got = rule_results(
            self._scen(activation_score=0, citation_score=0, behavior_score=0), "full"
        )
        assert got == {"S": False}

    @pytest.mark.parametrize("bad", [5.5, 6, 100, -1, -0.5])
    def test_a_rule_score_outside_zero_to_five_is_an_adapter_error(self, bad):
        with pytest.raises(AdapterError, match="between"):
            rule_results(
                self._scen(activation_score=bad, citation_score=5, behavior_score=5),
                "full",
            )

    def test_the_rule_error_names_the_scenario_and_the_field(self):
        with pytest.raises(AdapterError, match="citation_score"):
            rule_results(
                self._scen(activation_score=5, citation_score=9, behavior_score=5),
                "full",
            )

    @pytest.mark.parametrize("bad", [1.5, 2, -0.5, 100])
    def test_an_agent_rate_outside_zero_to_one_is_an_adapter_error(self, bad):
        with pytest.raises(AdapterError, match="between"):
            agent_results(_report({"C001": {"agent": [bad]}}), "agent")

    def test_an_inflated_run_cannot_carry_a_failed_one(self):
        """The mean of 0.0 and 2.0 clears a threshold neither run reached."""
        with pytest.raises(AdapterError):
            agent_results(_report({"C001": {"agent": [0.0, 2.0]}}), "agent")

    @pytest.mark.parametrize("ok", [0.0, 0.5, 1.0])
    def test_an_agent_rate_inside_zero_to_one_is_accepted(self, ok):
        got = agent_results(_report({"C001": {"agent": [ok]}}), "agent")
        assert got == {"C001": ok >= 1.0}

    def test_the_agent_error_names_the_fixture(self):
        with pytest.raises(AdapterError, match="C007"):
            agent_results(_report({"C007": {"agent": [3.0]}}), "agent")

    @pytest.mark.parametrize(
        "triple",
        [(1e308, 1e308, -1e308), (1e308, -1e308, 1e308)],
    )
    def test_the_reduction_no_longer_depends_on_the_order_of_huge_values(self, triple):
        """One ordering raised OverflowError and the other returned a pass."""
        with pytest.raises(AdapterError):
            rule_results(
                self._scen(
                    activation_score=triple[0],
                    citation_score=triple[1],
                    behavior_score=triple[2],
                ),
                "full",
            )


class TestAnIntegerTooBigForAFloatIsOutOfRangeNotACrash:
    """The check that would have caught it ran one line too late.

    `_as_float` asks `math.isfinite` before it asks whether the value is in
    range. `math.isfinite` converts to float first, so an integer past
    1.8e308 raises `OverflowError`. That is not one of the three exceptions
    `main` catches, so the command prints a traceback and exits 1, and exit 1
    is this tool's REJECT verdict. A caller branching on the exit code reads a
    crash as a decision.

    The range check added the round before would have refused the same value
    with the right message, because Python compares an integer to a float
    exactly at any size: `10**400 <= 1.0` is False without converting
    anything. It was placed after the call that cannot survive the input.

    So the fix is to stop asking a question of integers that only floats can
    answer. An integer is never NaN and never infinite; only a float can be.
    Restricting the finiteness check to floats leaves every integer to the
    range check, which handles arbitrary size, and leaves the final `float()`
    safe because nothing that survives the range check is large.
    """

    def _scen(self, **scores):
        return [{"id": "S", "mechanisms": {"full": {"scores": scores}}}]

    # A float cannot hold this, and it is far outside both scales.
    HUGE = 10**400

    def test_a_huge_run_is_refused_as_out_of_range(self):
        with pytest.raises(AdapterError, match="between"):
            agent_results(_report({"C1": {"agent": [self.HUGE]}}), "agent")

    def test_a_huge_run_does_not_raise_overflow(self):
        with pytest.raises(AdapterError):
            agent_results(_report({"C1": {"agent": [self.HUGE]}}), "agent")

    def test_a_hugely_negative_run_is_refused_as_out_of_range(self):
        with pytest.raises(AdapterError, match="between"):
            agent_results(_report({"C1": {"agent": [-self.HUGE]}}), "agent")

    @pytest.mark.parametrize(
        "key", ["activation_score", "behavior_score", "citation_score"]
    )
    def test_a_huge_score_is_refused_in_every_rule_dimension(self, key):
        scores = {
            "activation_score": 5,
            "behavior_score": 5,
            "citation_score": 5,
        }
        scores[key] = self.HUGE
        with pytest.raises(AdapterError, match="between"):
            rule_results(self._scen(**scores), "full")

    def test_a_hugely_negative_rule_score_is_refused(self):
        with pytest.raises(AdapterError, match="between"):
            rule_results(
                self._scen(
                    activation_score=-self.HUGE,
                    behavior_score=5,
                    citation_score=5,
                ),
                "full",
            )

    def test_the_refusal_names_the_value_it_refused(self):
        with pytest.raises(AdapterError) as caught:
            agent_results(_report({"C1": {"agent": [self.HUGE]}}), "agent")
        assert str(self.HUGE) in str(caught.value)

    # --- the boundary between "converts" and "does not" -------------------

    def test_the_largest_convertible_integer_is_still_out_of_range(self):
        """One below the overflow boundary must reach the same verdict.

        Otherwise the fix would only move the crash, and a value that does
        convert would take a different path from one that does not.
        """
        biggest = int(sys.float_info.max)
        with pytest.raises(AdapterError, match="between"):
            agent_results(_report({"C1": {"agent": [biggest]}}), "agent")

    def test_an_integer_at_the_top_of_the_pass_rate_scale_is_accepted(self):
        assert agent_results(_report({"C1": {"agent": [1]}}), "agent") == {"C1": True}

    def test_an_integer_at_the_bottom_of_the_pass_rate_scale_is_accepted(self):
        assert agent_results(_report({"C1": {"agent": [0]}}), "agent") == {"C1": False}

    def test_an_integer_at_the_top_of_the_rule_scale_is_accepted(self):
        assert rule_results(
            self._scen(
                activation_score=5, behavior_score=5, citation_score=5
            ),
            "full",
        ) == {"S": True}

    def test_one_past_the_top_of_the_rule_scale_is_still_refused(self):
        with pytest.raises(AdapterError, match="between"):
            rule_results(
                self._scen(
                    activation_score=6, behavior_score=5, citation_score=5
                ),
                "full",
            )

    # --- controls: the checks this must not disturb -----------------------

    def test_nan_still_reports_finiteness_not_range(self):
        with pytest.raises(AdapterError, match="finite"):
            agent_results(_report({"C1": {"agent": [float("nan")]}}), "agent")

    def test_infinity_still_reports_finiteness_not_range(self):
        with pytest.raises(AdapterError, match="finite"):
            agent_results(_report({"C1": {"agent": [float("inf")]}}), "agent")

    def test_negative_infinity_still_reports_finiteness_not_range(self):
        with pytest.raises(AdapterError, match="finite"):
            agent_results(_report({"C1": {"agent": [float("-inf")]}}), "agent")

    def test_nan_in_a_rule_score_still_reports_finiteness(self):
        with pytest.raises(AdapterError, match="finite"):
            rule_results(
                self._scen(
                    activation_score=float("nan"),
                    behavior_score=5,
                    citation_score=5,
                ),
                "full",
            )

    def test_a_bool_is_still_refused_as_non_numeric(self):
        with pytest.raises(AdapterError, match="numeric"):
            agent_results(_report({"C1": {"agent": [True]}}), "agent")

    def test_an_ordinary_float_still_passes(self):
        assert agent_results(_report({"C1": {"agent": [0.5]}}), "agent") == {"C1": False}


class TestAPartialScoreMappingIsNotAMeasurement:
    """Absent keys defaulted to zero, so present maxima carried the absent one.

    Rule scoring reduces three dimensions. A missing key defaulted to 0 and
    then went into the mean with the two that were recorded, which dilutes an
    unknown instead of refusing it. That reads as fail-closed only while the
    bar sits above the value the present maxima can reach on their own: two
    fives and one absent key reduce to 3.33, which clears `--min-score 3.0`
    and misses the 3.5 default by luck rather than by design. One absent key
    passes any bar under 3.34, two absent keys pass any bar under 1.67, and
    both of those bars are legal values of a documented flag.

    `eval-rule-activation.py` writes all three keys unconditionally, each
    through `_clamp_score` (:218-220), so a mapping that reaches here missing
    one did not come from the canonical producer intact. That makes it a
    malformed input rather than a low-scoring scenario, and the difference
    matters at the exit code: a reject verdict is a claim about the candidate,
    and this is a claim about the report.

    Refusing rather than scoring 0 also keeps a systematic producer break
    visible. If a schema change dropped `behavior_score`, scoring the absence
    would mark every scenario failed and reject a candidate for a reason that
    has nothing to do with the candidate.
    """

    # Every nonempty proper subset of the three keys: three of size one, three
    # of size two. The empty subset is covered separately because it used to
    # be the only case the degraded scan caught, and the complete subset is
    # the control.
    PARTIAL = [
        {"activation_score": 5},
        {"citation_score": 5},
        {"behavior_score": 5},
        {"activation_score": 5, "citation_score": 5},
        {"activation_score": 5, "behavior_score": 5},
        {"citation_score": 5, "behavior_score": 5},
    ]

    def _scen(self, scores, sid="S"):
        return [{"id": sid, "mechanisms": {"full": {"scores": scores}}}]

    @pytest.mark.parametrize("scores", PARTIAL)
    def test_every_partial_combination_is_refused(self, scores):
        with pytest.raises(AdapterError, match="missing"):
            rule_results(self._scen(scores), "full")

    @pytest.mark.parametrize("scores", PARTIAL)
    def test_no_partial_combination_can_clear_a_low_bar(self, scores):
        """The bar that used to let two maxima cover a third measurement."""
        with pytest.raises(AdapterError):
            rule_results(self._scen(scores), "full", min_score=3.0)

    def test_an_empty_mapping_is_refused_as_missing_all_three(self):
        with pytest.raises(AdapterError, match="missing"):
            rule_results(self._scen({}), "full")

    def test_the_refusal_names_every_missing_key(self):
        with pytest.raises(AdapterError) as caught:
            rule_results(self._scen({"activation_score": 5}), "full")
        message = str(caught.value)
        assert "citation_score" in message
        assert "behavior_score" in message

    def test_the_refusal_does_not_name_a_key_that_is_present(self):
        with pytest.raises(AdapterError) as caught:
            rule_results(self._scen({"activation_score": 5}), "full")
        assert "activation_score" not in str(caught.value)

    def test_the_refusal_names_the_scenario(self):
        with pytest.raises(AdapterError, match="S7"):
            rule_results(self._scen({"citation_score": 5}, sid="S7"), "full")

    def test_a_complete_mapping_still_reduces(self):
        got = rule_results(
            self._scen(
                {"activation_score": 5, "citation_score": 5, "behavior_score": 5}
            ),
            "full",
        )
        assert got == {"S": True}

    def test_a_complete_mapping_can_still_fail(self):
        got = rule_results(
            self._scen(
                {"activation_score": 0, "citation_score": 0, "behavior_score": 0}
            ),
            "full",
        )
        assert got == {"S": False}

    def test_an_explicit_zero_is_a_measurement_and_is_kept(self):
        """A recorded 0 is evidence; an absent key is not. They must differ."""
        got = rule_results(
            self._scen(
                {"activation_score": 5, "citation_score": 5, "behavior_score": 0}
            ),
            "full",
            min_score=3.0,
        )
        assert got == {"S": True}

    def test_a_judge_failure_is_still_reported_before_completeness(self):
        """A broken judge names itself; it must not be reported as a bad shape."""
        got = rule_results(
            self._scen({"judge_failed": True}),
            "full",
        )
        assert got == {"S": False}

    def test_a_judge_failure_beside_partial_scores_is_still_a_judge_failure(self):
        got = rule_results(
            self._scen({"judge_failed": True, "activation_score": 5}),
            "full",
        )
        assert got == {"S": False}

    def test_a_malformed_scores_block_still_names_the_block(self):
        """Shape of the block precedes completeness of its keys."""
        with pytest.raises(AdapterError, match="malformed"):
            rule_results(self._scen(None), "full")


# ---------------------------------------------------------------------------
# rule_results_multi
# ---------------------------------------------------------------------------


class TestReducingARuleScenarioAcrossRepeatedRuns:
    """The rule path is the only one of three with no noise defense.

    `pytest_results` is deterministic and `agent_results` already averages over
    runs. `rule_results` reads one score block from one LLM judge and
    thresholds it, which ADR-087 Open Requirement 6 measured rather than
    assumed: scoring identical rule text twice moved 13 of 24 tasks and 5 of
    them across the pass threshold, with mean absolute movement of 0.49 points
    on a five-point scale. The two held-out gains that produced the live run's
    false accept were the two largest movements in that benchmark.

    So a single judge reading is not evidence about an edit, and the gate's
    no-regression clause inherits that. Reducing over repeated readings is what
    makes the reading mean something; nothing else here changes.

    The runs are whole reports, one per invocation of `eval-rule-activation.py`,
    because that is how the ADR's own paired measurement was gathered. It needs
    no change to the producer.
    """

    @staticmethod
    def _run(*triples: tuple) -> list:
        return [_scenario(f"S{i}", "full", t) for i, t in enumerate(triples, 1)]

    def test_one_run_matches_the_single_run_adapter_exactly(self):
        """The multi-run path must be a generalization, not a second opinion."""
        scenarios = self._run((4, 4, 4), (3, 3, 3))
        assert rule_results_multi([scenarios], "full") == rule_results(scenarios, "full")

    def test_the_mean_across_runs_decides_not_any_single_run(self):
        """3.0 then 4.0 means 3.5, which clears the inclusive floor.

        Neither run decides this alone: the first fails the bar and the second
        clears it. That is the whole point of reducing.
        """
        got = rule_results_multi(
            [self._run((3, 3, 3)), self._run((4, 4, 4))], "full"
        )
        assert got == {"S1": True}

    def test_a_lucky_run_no_longer_carries_a_scenario_on_its_own(self):
        """One 5.0 among three 3.0s reduces to 3.67 and passes; among five, 3.33.

        The single-run adapter would have returned True from the lucky run and
        False from any other, which is the coin flip the ADR names.
        """
        low = self._run((3, 3, 3))
        high = self._run((5, 5, 5))
        assert rule_results_multi([high, low, low], "full") == {"S1": True}
        assert rule_results_multi([high, low, low, low, low], "full") == {"S1": False}

    def test_min_reduces_to_the_worst_run(self):
        got = rule_results_multi(
            [self._run((5, 5, 5)), self._run((3, 3, 3))], "full", reduce="min"
        )
        assert got == {"S1": False}

    def test_max_reduces_to_the_best_run(self):
        got = rule_results_multi(
            [self._run((5, 5, 5)), self._run((3, 3, 3))], "full", reduce="max"
        )
        assert got == {"S1": True}

    def test_median_ignores_a_single_outlier(self):
        got = rule_results_multi(
            [self._run((0, 0, 0)), self._run((4, 4, 4)), self._run((4, 4, 4))],
            "full",
            reduce="median",
        )
        assert got == {"S1": True}

    def test_an_unknown_reducer_is_refused_by_name(self):
        with pytest.raises(AdapterError, match="reduce must be one of"):
            rule_results_multi([self._run((4, 4, 4))], "full", reduce="average")

    def test_no_runs_at_all_is_refused_rather_than_scored_as_empty(self):
        """An empty reduction has no answer, and {} would read as zero tasks."""
        with pytest.raises(AdapterError, match="at least one run"):
            rule_results_multi([], "full")

    def test_runs_that_disagree_on_which_scenarios_exist_are_refused(self):
        """Reducing across different task sets compares unlike things."""
        first = [_scenario("S1", "full", (4, 4, 4))]
        second = [_scenario("S2", "full", (4, 4, 4))]
        with pytest.raises(AdapterError, match="same scenarios"):
            rule_results_multi([first, second], "full")

    def test_the_refusal_names_the_scenarios_that_differ(self):
        first = [_scenario("S1", "full", (4, 4, 4))]
        second = [
            _scenario("S1", "full", (4, 4, 4)),
            _scenario("S9", "full", (4, 4, 4)),
        ]
        with pytest.raises(AdapterError, match="S9"):
            rule_results_multi([first, second], "full")

    def test_a_scenario_with_no_evidence_in_every_run_fails_closed(self):
        """Uniform absence keeps the single-run meaning: no evidence is not a pass."""
        blank = [{"id": "S1", "negative_case": False, "mechanisms": {}}]
        assert rule_results_multi([blank, blank], "full") == {"S1": False}

    def test_evidence_in_some_runs_but_not_others_is_refused(self):
        """This is the case that only exists once there is more than one run.

        Scoring it False would be worse than useless. A judge error on the
        incumbent's run reads as a failing scenario, so a candidate that merely
        ran cleanly looks like a fail-to-pass improvement. That is the spurious
        accept the gate exists to prevent, arriving through the scorer.
        Dropping the bad run instead would silently reduce over a different
        sample size per scenario. Neither is a measurement, so refuse.
        """
        scored = [_scenario("S1", "full", (4, 4, 4))]
        blank = [{"id": "S1", "negative_case": False, "mechanisms": {}}]
        with pytest.raises(AdapterError, match="some runs but not others"):
            rule_results_multi([scored, blank], "full")

    def test_a_judge_failure_in_one_run_is_refused_not_averaged(self):
        """A judge failure is a missing measurement, not a low score."""
        scored = [_scenario("S1", "full", (4, 4, 4))]
        broken = [_scenario("S1", "full", (5, 5, 5), judge_failed=True)]
        with pytest.raises(AdapterError, match="some runs but not others"):
            rule_results_multi([scored, broken], "full")

    def test_min_score_still_applies_after_the_reduction(self):
        got = rule_results_multi(
            [self._run((3, 3, 3)), self._run((4, 4, 4))], "full", min_score=3.6
        )
        assert got == {"S1": False}

    def test_a_malformed_scenario_in_a_later_run_is_still_refused(self):
        """The scan must not stop at the first run."""
        good = self._run((4, 4, 4))
        with pytest.raises(AdapterError, match="must be an object"):
            rule_results_multi([good, ["not a mapping"]], "full")

    def test_every_scenario_is_reduced_not_just_the_first(self):
        got = rule_results_multi(
            [self._run((5, 5, 5), (3, 3, 3)), self._run((5, 5, 5), (3, 3, 3))],
            "full",
        )
        assert got == {"S1": True, "S2": False}


# ---------------------------------------------------------------------------
# reduce_samples, the seam where the two rule reductions meet
# ---------------------------------------------------------------------------


def _sampled(sid: str, mech: str, *triples: tuple, **kw) -> dict:
    """A scenario whose mechanism carries several judge samples.

    `scores` stays populated because the producer writes it either way: it is
    the reduction the evaluator already published, and the adapter reads the
    raw samples instead so the two reductions cannot silently differ.
    """
    samples = [
        {
            "activation_score": t[0],
            "citation_score": t[1],
            "behavior_score": t[2],
        }
        for t in triples
    ]
    mech_block: dict = {"scores": dict(samples[0]), "score_samples": samples}
    mech_block.update(kw)
    return {"id": sid, "negative_case": False, "mechanisms": {mech: mech_block}}


class TestTwoReductionsStackWithoutSubsumingEachOther:
    """Repeated judge calls and repeated reports are different noise.

    `score_samples` holds several calls to one judge against one report, so a
    single erratic call is the shape it defends against and the median drops
    that call outright. A run is a whole report, where ADR-087 Open
    Requirement 6 measured movement spread across 13 of 24 tasks rather than
    spiked on one, so the run reduction means them instead.

    Neither collapses the other. Reducing samples cannot rescue a report that
    landed low as a whole, and reducing runs cannot see which call inside a
    report was the outlier. These tests pin that both axes stay live and stay
    independently selectable.
    """

    @staticmethod
    def _bar() -> float:
        return 3.5

    def test_samples_reduce_before_the_bar_is_applied(self):
        """Median of 5, 5, 0 is 5 and passes; their mean is 3.33 and fails."""
        run = [_sampled("S1", "full", (5, 5, 5), (5, 5, 5), (0, 0, 0))]
        assert rule_results(run, "full") == {"S1": True}
        assert rule_results(run, "full", reduce="mean") == {"S1": False}

    def test_the_sample_reducer_is_selectable_through_the_multi_run_path(self):
        """Same run, same run-reducer, opposite verdicts from samples alone."""
        runs = [[_sampled("S1", "full", (5, 5, 5), (5, 5, 5), (0, 0, 0))]]
        assert rule_results_multi(runs, "full") == {"S1": True}
        assert rule_results_multi(runs, "full", reduce_samples="mean") == {"S1": False}

    def test_both_reductions_apply_and_the_run_reducer_still_decides(self):
        """Samples collapse to 5 and 2; the runs then decide between them.

        Meaning the runs gives 3.5, which clears the inclusive floor. Taking
        their min gives 2.0, which does not. The sample reduction is identical
        in both, so only the run axis moved the verdict.
        """
        runs = [
            [_sampled("S1", "full", (5, 5, 5), (5, 5, 5), (0, 0, 0))],
            [_sampled("S1", "full", (2, 2, 2))],
        ]
        assert rule_results_multi(runs, "full") == {"S1": True}
        assert rule_results_multi(runs, "full", reduce="min") == {"S1": False}

    def test_one_sampled_run_still_matches_the_single_run_adapter(self):
        """The generalization property has to survive the second axis."""
        run = [_sampled("S1", "full", (5, 5, 5), (2, 2, 2), (4, 4, 4))]
        for reducer in ("mean", "min", "max", "median"):
            assert rule_results_multi(
                [run], "full", reduce_samples=reducer
            ) == rule_results(run, "full", reduce=reducer)

    def test_an_unknown_sample_reducer_names_the_parameter_it_came_from(self):
        """Two reducer parameters means the error has to say which one broke."""
        run = [_sampled("S1", "full", (4, 4, 4))]
        with pytest.raises(AdapterError, match="reduce_samples must be one of"):
            rule_results_multi([run], "full", reduce_samples="average")
        with pytest.raises(AdapterError, match="reduce must be one of"):
            rule_results_multi([run], "full", reduce="average")

    def test_a_failed_sample_makes_the_whole_run_no_evidence(self):
        """Reducing the survivors would report a number the report disowned.

        The run that carries the broken call has no evidence for the scenario,
        which is not the same as a low score. A scenario measured in one run
        and not another is the shape `rule_results_multi` already refuses, so
        the failure surfaces there rather than averaging a hole.
        """
        broken = [
            _sampled(
                "S1",
                "full",
                (5, 5, 5),
                (5, 5, 5),
            )
        ]
        samples = broken[0]["mechanisms"]["full"]["score_samples"]
        samples[1]["judge_failed"] = True
        assert rule_results(broken, "full") == {"S1": False}
        with pytest.raises(AdapterError, match="evidence"):
            rule_results_multi(
                [broken, [_sampled("S1", "full", (5, 5, 5))]], "full"
            )

    def test_a_sample_missing_a_score_is_refused_not_defaulted_to_zero(self):
        """The same refusal the unsampled path makes, at sample granularity."""
        run = [_sampled("S1", "full", (5, 5, 5), (5, 5, 5))]
        del run[0]["mechanisms"]["full"]["score_samples"][1]["behavior_score"]
        with pytest.raises(AdapterError, match=r"score_samples\[1\] missing"):
            rule_results_multi([run], "full")

    def test_an_empty_sample_list_is_refused_rather_than_read_as_unsampled(self):
        """An empty list is a producer that meant to write samples and did not."""
        run = [_sampled("S1", "full", (5, 5, 5))]
        run[0]["mechanisms"]["full"]["score_samples"] = []
        with pytest.raises(AdapterError, match="non-empty list"):
            rule_results_multi([run], "full")
