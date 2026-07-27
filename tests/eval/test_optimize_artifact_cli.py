"""Tests for scripts/eval/optimize-artifact.py (issue #3422).

The CLI is the surface an optimizing agent drives. Its job is to make the
held-out discipline mechanical: the agent proposes edits, the CLI decides
whether they survive, and the agent cannot reach the accept decision without
going through a split it did not choose.

The safety property worth testing hardest is that `gate` scores both sides
itself from the split's `sel` group. If the gate took bare numbers, the
easiest mistake in the whole loop would be handing it optimize-set scores,
which is precisely the overfitting the gate exists to stop.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_EVAL_DIR = Path(__file__).resolve().parents[2] / "scripts" / "eval"
# Scope the sys.path mutation to the module load and remove it afterward so it
# does not leak into other tests (mirrors tests/eval/test_variance_control.py).
_path_added = str(_EVAL_DIR) not in sys.path
try:
    if _path_added:
        sys.path.insert(0, str(_EVAL_DIR))
    _SCRIPT = _EVAL_DIR / "optimize-artifact.py"
    _spec = importlib.util.spec_from_file_location("optimize_artifact", _SCRIPT)
    assert _spec is not None and _spec.loader is not None
    oa = importlib.util.module_from_spec(_spec)
    sys.modules["optimize_artifact"] = oa
    _spec.loader.exec_module(oa)
finally:
    if _path_added and str(_EVAL_DIR) in sys.path:
        sys.path.remove(str(_EVAL_DIR))


EXIT_OK = 0
EXIT_LOGIC = 1
EXIT_CONFIG = 2


def _run(capsys, *argv: str | Path) -> tuple[int, dict]:
    """Invoke the CLI and return (exit code, parsed stdout JSON)."""
    code = oa.main([str(a) for a in argv])
    out = capsys.readouterr().out.strip()
    return code, (json.loads(out) if out else {})


def _split(capsys, tmp_path, *args, name="split.json"):
    """Run `split` and return the full record from the file the gate reads.

    Stdout deliberately redacts held-out membership, so any test that needs
    the whole split has to read it the way the gate does.
    """
    path = tmp_path / name
    code, stdout = _run(capsys, "split", *args, "--out", path)
    if code != EXIT_OK:
        return code, stdout
    return code, json.loads(path.read_text(encoding="utf-8"))


def _boom(*_args, **_kwargs):
    raise OSError("disk full")


def _write(tmp_path: Path, name: str, payload: object) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _results(passing: int, failing: int) -> dict:
    out = {f"p{i}": True for i in range(passing)}
    out.update({f"f{i}": False for i in range(failing)})
    return out


# ---------------------------------------------------------------------------
# extract
# ---------------------------------------------------------------------------


class TestExtract:
    def test_agent_report(self, tmp_path, capsys):
        report = _write(
            tmp_path,
            "report.json",
            {"per_fixture_pass_rates": {"C1": {"agent": [1.0]}, "C2": {"agent": [0.0]}}},
        )
        code, out = _run(capsys, "extract", "--kind", "agent", "--input", report)
        assert code == EXIT_OK
        assert out == {"C1": True, "C2": False}

    def test_agent_report_honors_variant_and_threshold(self, tmp_path, capsys):
        report = _write(
            tmp_path,
            "report.json",
            {"per_fixture_pass_rates": {"C1": {"baseline": [0.6]}}},
        )
        code, out = _run(
            capsys,
            "extract",
            "--kind",
            "agent",
            "--input",
            report,
            "--variant",
            "baseline",
            "--pass-threshold",
            "0.5",
        )
        assert code == EXIT_OK
        assert out == {"C1": True}

    def test_rule_scenarios(self, tmp_path, capsys):
        scenarios = _write(
            tmp_path,
            "scen.json",
            [
                {
                    "id": "S1",
                    "negative_case": False,
                    "mechanisms": {
                        "full": {
                            "scores": {
                                "activation_score": 5,
                                "citation_score": 5,
                                "behavior_score": 5,
                            }
                        }
                    },
                }
            ],
        )
        code, out = _run(capsys, "extract", "--kind", "rule", "--input", scenarios)
        assert code == EXIT_OK
        assert out == {"S1": True}

    def test_rule_scenarios_accept_a_wrapped_object(self, tmp_path, capsys):
        """A bare scenario list may also arrive wrapped in a 'scenarios' key."""
        scenarios = _write(
            tmp_path,
            "scen.json",
            {
                "scenarios": [
                    {
                        "id": "S1",
                        "negative_case": False,
                        "mechanisms": {"full": {"scores": {"activation_score": 5}}},
                    }
                ]
            },
        )
        code, out = _run(capsys, "extract", "--kind", "rule", "--input", scenarios)
        assert code == EXIT_OK
        assert out == {"S1": False}

    def test_hook_junit(self, tmp_path, capsys):
        junit = tmp_path / "j.xml"
        junit.write_text(
            "<testsuites><testsuite>"
            "<testcase classname='tests.test_a' name='test_x'/>"
            "<testcase classname='tests.test_a' name='test_y'><failure/></testcase>"
            "</testsuite></testsuites>",
            encoding="utf-8",
        )
        code, out = _run(capsys, "extract", "--kind", "hook", "--input", junit)
        assert code == EXIT_OK
        assert out == {"tests.test_a::test_x": True, "tests.test_a::test_y": False}

    def test_missing_input_is_a_config_error(self, tmp_path, capsys):
        code, _ = _run(capsys, "extract", "--kind", "agent", "--input", tmp_path / "nope.json")
        assert code == EXIT_CONFIG

    def test_malformed_json_is_a_config_error(self, tmp_path, capsys):
        bad = tmp_path / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        code, _ = _run(capsys, "extract", "--kind", "agent", "--input", bad)
        assert code == EXIT_CONFIG

    def test_adapter_rejection_is_a_config_error(self, tmp_path, capsys):
        report = _write(tmp_path, "report.json", {"wrong": "shape"})
        code, _ = _run(capsys, "extract", "--kind", "agent", "--input", report)
        assert code == EXIT_CONFIG

    def test_non_object_agent_report_is_a_config_error(self, tmp_path, capsys):
        report = _write(tmp_path, "report.json", ["not", "an", "object"])
        code, _ = _run(capsys, "extract", "--kind", "agent", "--input", report)
        assert code == EXIT_CONFIG

    def test_non_array_rule_input_is_a_config_error(self, tmp_path, capsys):
        scenarios = _write(tmp_path, "scen.json", {"scenarios": "not a list"})
        code, _ = _run(capsys, "extract", "--kind", "rule", "--input", scenarios)
        assert code == EXIT_CONFIG


class TestExtractRealRuleEnvelope:
    """The shape eval-rule-activation.py --output actually writes.

    Verified against a live run over tests/evals/rule-scenarios/*.json: the
    file is {"rules": {<rule-name>: {"rule_path", "scenarios", "summary"}}}.
    Scenario ids restart at S1 inside every rule, so 24 real scenarios carry
    only 4 distinct ids and must be namespaced before they can be task ids.
    """

    @staticmethod
    def _scenario(sid: str, score: int) -> dict:
        return {
            "id": sid,
            "negative_case": False,
            "mechanisms": {
                "full": {
                    "scores": {
                        "activation_score": score,
                        "citation_score": score,
                        "behavior_score": score,
                    }
                }
            },
        }

    def _envelope(self) -> dict:
        return {
            "rules": {
                "clean-architecture": {
                    "rule_path": ".claude/rules/clean-architecture.md",
                    "scenarios": [self._scenario("S1", 5), self._scenario("S2", 1)],
                    "summary": {"verdict": "PASS"},
                },
                "refactoring": {
                    "rule_path": ".claude/rules/refactoring.md",
                    "scenarios": [self._scenario("S1", 1)],
                    "summary": {"verdict": "PASS"},
                },
            }
        }

    def test_accepts_the_rules_envelope(self, tmp_path, capsys):
        path = _write(tmp_path, "rules.json", self._envelope())
        code, out = _run(capsys, "extract", "--kind", "rule", "--input", path)
        assert code == EXIT_OK
        assert len(out) == 3

    def test_namespaces_scenario_ids_by_rule(self, tmp_path, capsys):
        path = _write(tmp_path, "rules.json", self._envelope())
        _, out = _run(capsys, "extract", "--kind", "rule", "--input", path)
        assert out == {
            "clean-architecture::S1": True,
            "clean-architecture::S2": False,
            "refactoring::S1": False,
        }

    def test_a_single_rule_is_namespaced_too(self, tmp_path, capsys):
        """Namespacing must not depend on how many rules the file holds.

        If it did, adding a second rule would rewrite every existing task id
        and move the split fingerprint, which the gate refuses to compare.
        """
        envelope = {"rules": {"refactoring": {"scenarios": [self._scenario("S1", 5)]}}}
        path = _write(tmp_path, "rules.json", envelope)
        _, out = _run(capsys, "extract", "--kind", "rule", "--input", path)
        assert out == {"refactoring::S1": True}

    def test_a_non_mapping_rules_value_is_a_config_error(self, tmp_path, capsys):
        path = _write(tmp_path, "rules.json", {"rules": ["not", "a", "mapping"]})
        code, _ = _run(capsys, "extract", "--kind", "rule", "--input", path)
        assert code == EXIT_CONFIG

    def test_a_rule_entry_without_scenarios_is_a_config_error(self, tmp_path, capsys):
        """Fail closed. Skipping the rule would shrink the denominator."""
        path = _write(tmp_path, "rules.json", {"rules": {"refactoring": {"summary": {}}}})
        code, _ = _run(capsys, "extract", "--kind", "rule", "--input", path)
        assert code == EXIT_CONFIG

    def test_a_non_mapping_rule_entry_is_a_config_error(self, tmp_path, capsys):
        path = _write(tmp_path, "rules.json", {"rules": {"refactoring": "oops"}})
        code, _ = _run(capsys, "extract", "--kind", "rule", "--input", path)
        assert code == EXIT_CONFIG

    def test_an_empty_rules_envelope_is_a_config_error(self, tmp_path, capsys):
        path = _write(tmp_path, "rules.json", {"rules": {}})
        code, _ = _run(capsys, "extract", "--kind", "rule", "--input", path)
        assert code == EXIT_CONFIG


# ---------------------------------------------------------------------------
# split
# ---------------------------------------------------------------------------


class TestSplit:
    def test_partitions_every_task(self, tmp_path, capsys):
        results = _write(tmp_path, "r.json", _results(6, 4))
        code, out = _split(capsys, tmp_path, "--results", results, "--seed", "s1")
        assert code == EXIT_OK
        assert sorted(out["opt"] + out["sel"] + out["test"]) == sorted(_results(6, 4))
        assert out["fingerprint"]

    def test_is_deterministic_for_a_seed(self, tmp_path, capsys):
        results = _write(tmp_path, "r.json", _results(6, 4))
        _, first = _split(capsys, tmp_path, "--results", results, "--seed", "s1")
        _, second = _split(capsys, tmp_path, "--results", results, "--seed", "s1")
        assert first == second

    def test_seed_changes_the_split(self, tmp_path, capsys):
        results = _write(tmp_path, "r.json", _results(6, 4))
        _, first = _split(capsys, tmp_path, "--results", results, "--seed", "s1")
        _, second = _split(capsys, tmp_path, "--results", results, "--seed", "s2")
        assert first["fingerprint"] != second["fingerprint"]

    def test_reads_a_plain_task_id_list(self, tmp_path, capsys):
        tasks = tmp_path / "ids.txt"
        tasks.write_text("\n".join(f"t{i}" for i in range(10)) + "\n", encoding="utf-8")
        code, out = _split(capsys, tmp_path, "--tasks", tasks, "--seed", "s1")
        assert code == EXIT_OK
        assert len(out["opt"] + out["sel"] + out["test"]) == 10

    def test_blank_lines_in_a_task_list_are_ignored(self, tmp_path, capsys):
        tasks = tmp_path / "ids.txt"
        tasks.write_text("t0\n\n  \nt1\nt2\nt3\nt4\nt5\nt6\nt7\n", encoding="utf-8")
        code, out = _split(capsys, tmp_path, "--tasks", tasks, "--seed", "s1")
        assert code == EXIT_OK
        assert len(out["opt"] + out["sel"] + out["test"]) == 8

    def test_too_few_tasks_is_a_config_error(self, tmp_path, capsys):
        results = _write(tmp_path, "r.json", _results(2, 0))
        code, _ = _split(capsys, tmp_path, "--results", results, "--seed", "s1")
        assert code == EXIT_CONFIG

    def test_requires_a_task_source(self, capsys):
        with pytest.raises(SystemExit):
            oa.main(["split", "--seed", "s1", "--out", "x.json"])

    def test_rejects_both_task_sources(self, tmp_path, capsys):
        results = _write(tmp_path, "r.json", _results(6, 4))
        with pytest.raises(SystemExit):
            oa.main(
                ["split", "--results", str(results), "--tasks", "x", "--seed", "s",
                 "--out", "x.json"]
            )


# ---------------------------------------------------------------------------
# budget
# ---------------------------------------------------------------------------


class TestBudget:
    def test_first_step_gets_the_maximum(self, capsys):
        code, out = _run(capsys, "budget", "--step", "0", "--total", "10")
        assert code == EXIT_OK
        assert out["budget"] == 5

    def test_last_step_gets_the_minimum(self, capsys):
        code, out = _run(capsys, "budget", "--step", "10", "--total", "10")
        assert code == EXIT_OK
        assert out["budget"] == 1

    def test_decays_monotonically(self, capsys):
        seen = [
            _run(capsys, "budget", "--step", str(s), "--total", "8")[1]["budget"]
            for s in range(9)
        ]
        assert seen == sorted(seen, reverse=True)

    def test_custom_bounds(self, capsys):
        code, out = _run(
            capsys, "budget", "--step", "0", "--total", "4", "--max-edits", "9", "--min-edits", "2"
        )
        assert code == EXIT_OK
        assert out["budget"] == 9

    def test_invalid_bounds_are_a_config_error(self, capsys):
        code, _ = _run(
            capsys, "budget", "--step", "0", "--total", "4", "--max-edits", "1", "--min-edits", "3"
        )
        assert code == EXIT_CONFIG

    def test_zero_total_is_a_config_error(self, capsys):
        code, _ = _run(capsys, "budget", "--step", "0", "--total", "0")
        assert code == EXIT_CONFIG


# ---------------------------------------------------------------------------
# score
# ---------------------------------------------------------------------------


class TestScore:
    def _split_file(self, tmp_path, capsys, results_path) -> Path:
        _split(capsys, tmp_path, "--results", results_path, "--seed", "s1")
        return tmp_path / "split.json"

    def test_scores_the_optimize_group_by_default(self, tmp_path, capsys):
        """This test used to assert a default of `sel`, which was the hole.

        A free-standing unmetered score on the held-out group hands the
        optimizer the answer the gate is supposed to charge a consultation
        for. `opt` is the only group this command will read.
        """
        results = _write(tmp_path, "r.json", _results(10, 0))
        split = self._split_file(tmp_path, capsys, results)
        code, out = _run(capsys, "score", "--results", results, "--split", split)
        assert code == EXIT_OK
        assert out["score"] == 1.0
        assert out["group"] == "opt"
        assert out["n"] > 0

    def test_scores_a_named_group(self, tmp_path, capsys):
        results = _write(tmp_path, "r.json", _results(0, 10))
        split = self._split_file(tmp_path, capsys, results)
        code, out = _run(capsys, "score", "--results", results, "--split", split, "--group", "opt")
        assert code == EXIT_OK
        assert out["score"] == 0.0

    def test_missing_result_is_a_config_error(self, tmp_path, capsys):
        results = _write(tmp_path, "r.json", _results(10, 0))
        split = self._split_file(tmp_path, capsys, results)
        truncated = _write(tmp_path, "trunc.json", {"p0": True})
        code, _ = _run(capsys, "score", "--results", truncated, "--split", split)
        assert code == EXIT_CONFIG

    def test_unknown_group_is_rejected(self, tmp_path, capsys):
        results = _write(tmp_path, "r.json", _results(10, 0))
        split = self._split_file(tmp_path, capsys, results)
        with pytest.raises(SystemExit):
            oa.main(["score", "--results", str(results), "--split", str(split), "--group", "nope"])


# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------


class TestApply:
    def test_appends_in_place(self, tmp_path, capsys):
        target = tmp_path / "a.md"
        target.write_text("line one\n", encoding="utf-8")
        patches = _write(tmp_path, "p.json", [{"op": "append", "text": "line two"}])
        code, out = _run(capsys, "apply", "--file", target, "--patches", patches, "--budget", "1")
        assert code == EXIT_OK
        assert target.read_text(encoding="utf-8") == "line one\nline two\n"
        assert out["applied"] == 1

    def test_dry_run_leaves_the_file_alone(self, tmp_path, capsys):
        target = tmp_path / "a.md"
        target.write_text("line one\n", encoding="utf-8")
        patches = _write(tmp_path, "p.json", [{"op": "append", "text": "line two"}])
        code, out = _run(
            capsys, "apply", "--file", target, "--patches", patches, "--budget", "1", "--dry-run"
        )
        assert code == EXIT_OK
        assert target.read_text(encoding="utf-8") == "line one\n"
        assert "line two" in out["result"]

    def test_over_budget_is_a_logic_error(self, tmp_path, capsys):
        target = tmp_path / "a.md"
        target.write_text("line one\n", encoding="utf-8")
        patches = _write(
            tmp_path,
            "p.json",
            [{"op": "append", "text": "a"}, {"op": "append", "text": "b"}],
        )
        code, _ = _run(capsys, "apply", "--file", target, "--patches", patches, "--budget", "1")
        assert code == EXIT_LOGIC
        assert target.read_text(encoding="utf-8") == "line one\n"

    def test_protected_section_edit_is_a_logic_error(self, tmp_path, capsys):
        target = tmp_path / "a.md"
        target.write_text(
            "<!-- SLOW_UPDATE_START -->\nrails\n<!-- SLOW_UPDATE_END -->\ntail\n",
            encoding="utf-8",
        )
        patches = _write(tmp_path, "p.json", [{"op": "delete", "anchor": "rails"}])
        code, _ = _run(capsys, "apply", "--file", target, "--patches", patches, "--budget", "1")
        assert code == EXIT_LOGIC
        assert "rails" in target.read_text(encoding="utf-8")

    def test_unknown_anchor_is_a_logic_error(self, tmp_path, capsys):
        target = tmp_path / "a.md"
        target.write_text("line one\n", encoding="utf-8")
        patches = _write(
            tmp_path, "p.json", [{"op": "insert_after", "anchor": "ghost", "text": "x"}]
        )
        code, _ = _run(capsys, "apply", "--file", target, "--patches", patches, "--budget", "1")
        assert code == EXIT_LOGIC

    def test_malformed_patch_shape_is_a_config_error(self, tmp_path, capsys):
        target = tmp_path / "a.md"
        target.write_text("line one\n", encoding="utf-8")
        patches = _write(tmp_path, "p.json", [{"text": "no op key"}])
        code, _ = _run(capsys, "apply", "--file", target, "--patches", patches, "--budget", "1")
        assert code == EXIT_CONFIG

    def test_patches_must_be_a_list(self, tmp_path, capsys):
        target = tmp_path / "a.md"
        target.write_text("line one\n", encoding="utf-8")
        patches = _write(tmp_path, "p.json", {"op": "append", "text": "x"})
        code, _ = _run(capsys, "apply", "--file", target, "--patches", patches, "--budget", "1")
        assert code == EXIT_CONFIG

    def test_missing_target_is_a_config_error(self, tmp_path, capsys):
        patches = _write(tmp_path, "p.json", [{"op": "append", "text": "x"}])
        code, _ = _run(
            capsys, "apply", "--file", tmp_path / "ghost.md", "--patches", patches, "--budget", "1"
        )
        assert code == EXIT_CONFIG


# ---------------------------------------------------------------------------
# gate
# ---------------------------------------------------------------------------


class TestGateHoldsOutOnly:
    """The gate must read sel and nothing else.

    The PR claimed gating on the optimize group was impossible to express, but
    --group was wired straight through to the scorer, so `gate --group opt`
    scored the visible group and reported a verdict. The flag is gone; sel is
    the only group a gate can read.
    """

    def _setup(self, tmp_path, capsys, incumbent: dict, candidate: dict):
        inc = _write(tmp_path, "inc.json", incumbent)
        cand = _write(tmp_path, "cand.json", candidate)
        _, split = _split(capsys, tmp_path, "--results", inc, "--seed", "s1")
        return inc, cand, _write(tmp_path, "split.json", split)

    def test_the_group_flag_is_gone(self, tmp_path, capsys):
        inc, cand, split_path = self._setup(
            tmp_path,
            capsys,
            {f"t{i}": False for i in range(10)},
            {f"t{i}": True for i in range(10)},
        )
        with pytest.raises(SystemExit):
            _run(
                capsys,
                "gate",
                "--incumbent",
                inc,
                "--candidate",
                cand,
                "--split",
                split_path,
                "--group",
                "opt",
            )

    def test_the_verdict_names_the_group_it_read(self, tmp_path, capsys):
        inc, cand, split_path = self._setup(
            tmp_path,
            capsys,
            {f"t{i}": False for i in range(10)},
            {f"t{i}": True for i in range(10)},
        )
        _, out = _run(
            capsys, "gate", "--incumbent", inc, "--candidate", cand, "--split", split_path
        )
        assert out["group"] == "sel"


class TestGateRefusalCostsNothing:
    """A refused comparison must not report the held-out scores.

    Scoring ran before the guards, so a call refused for an exhausted budget
    still printed both sel scores. That hands over the number the budget exists
    to ration, and it is free: the caller is told not to advance its counter.
    """

    def _setup(self, tmp_path, capsys):
        inc = _write(tmp_path, "inc.json", {f"t{i}": False for i in range(10)})
        cand = _write(tmp_path, "cand.json", {f"t{i}": True for i in range(10)})
        _, split = _split(capsys, tmp_path, "--results", inc, "--seed", "s1")
        return inc, cand, _write(tmp_path, "split.json", split), split

    def test_an_exhausted_budget_withholds_the_scores(self, tmp_path, capsys):
        inc, cand, split_path, _ = self._setup(tmp_path, capsys)
        code, out = _run(
            capsys,
            "gate",
            "--incumbent",
            inc,
            "--candidate",
            cand,
            "--split",
            split_path,
            "--consultations",
            "3",
            "--max-consultations",
            "3",
        )
        assert code == EXIT_LOGIC
        assert out["compared"] is False
        assert "candidate" not in out
        assert "incumbent" not in out

    def test_a_moved_fingerprint_withholds_the_scores(self, tmp_path, capsys):
        inc, cand, split_path, _ = self._setup(tmp_path, capsys)
        code, out = _run(
            capsys,
            "gate",
            "--incumbent",
            inc,
            "--candidate",
            cand,
            "--split",
            split_path,
            "--incumbent-fingerprint",
            "stale",
        )
        assert code == EXIT_LOGIC
        assert out["compared"] is False
        assert "candidate" not in out

    def test_a_refusal_still_reports_the_decision_and_reason(self, tmp_path, capsys):
        inc, cand, split_path, _ = self._setup(tmp_path, capsys)
        _, out = _run(
            capsys,
            "gate",
            "--incumbent",
            inc,
            "--candidate",
            cand,
            "--split",
            split_path,
            "--incumbent-fingerprint",
            "stale",
        )
        assert out["decision"] == "REJECT"
        assert "fingerprint" in out["reason"]

    def test_a_permitted_call_still_reports_the_scores(self, tmp_path, capsys):
        inc, cand, split_path, _ = self._setup(tmp_path, capsys)
        _, out = _run(
            capsys, "gate", "--incumbent", inc, "--candidate", cand, "--split", split_path
        )
        assert out["compared"] is True
        assert out["candidate"] == 1.0
        assert out["incumbent"] == 0.0


class TestGateReportsPairedEvidence:
    """Every compared verdict carries the discordant counts and an exact p."""

    def _gate(self, tmp_path, capsys, incumbent: dict, candidate: dict):
        inc = _write(tmp_path, "inc.json", incumbent)
        cand = _write(tmp_path, "cand.json", candidate)
        _, split = _split(capsys, tmp_path, "--results", inc, "--seed", "s1")
        split_path = _write(tmp_path, "split.json", split)
        return _run(
            capsys, "gate", "--incumbent", inc, "--candidate", cand, "--split", split_path
        )

    def test_a_clean_win_reports_gains_and_no_losses(self, tmp_path, capsys):
        _, out = self._gate(
            tmp_path,
            capsys,
            {f"t{i}": False for i in range(10)},
            {f"t{i}": True for i in range(10)},
        )
        assert out["discordant_gain"] == 4
        assert out["discordant_loss"] == 0
        assert out["p_value"] == pytest.approx(0.0625)

    def test_no_movement_reports_a_p_of_one(self, tmp_path, capsys):
        same = {f"t{i}": True for i in range(10)}
        _, out = self._gate(tmp_path, capsys, same, dict(same))
        assert out["discordant_gain"] == 0
        assert out["discordant_loss"] == 0
        assert out["p_value"] == 1.0

    def test_a_refusal_reports_no_paired_evidence(self, tmp_path, capsys):
        inc = _write(tmp_path, "inc.json", {f"t{i}": False for i in range(10)})
        cand = _write(tmp_path, "cand.json", {f"t{i}": True for i in range(10)})
        _, split = _split(capsys, tmp_path, "--results", inc, "--seed", "s1")
        split_path = _write(tmp_path, "split.json", split)
        _, out = _run(
            capsys,
            "gate",
            "--incumbent",
            inc,
            "--candidate",
            cand,
            "--split",
            split_path,
            "--incumbent-fingerprint",
            "stale",
        )
        assert "p_value" not in out


class TestGate:
    def _setup(self, tmp_path, capsys, incumbent: dict, candidate: dict):
        inc = _write(tmp_path, "inc.json", incumbent)
        cand = _write(tmp_path, "cand.json", candidate)
        _, split = _split(capsys, tmp_path, "--results", inc, "--seed", "s1")
        return inc, cand, _write(tmp_path, "split.json", split), split

    def test_accepts_a_strict_improvement(self, tmp_path, capsys):
        inc, cand, split_path, split = self._setup(
            tmp_path,
            capsys,
            {f"t{i}": False for i in range(10)},
            {f"t{i}": True for i in range(10)},
        )
        code, out = _run(
            capsys, "gate", "--incumbent", inc, "--candidate", cand, "--split", split_path
        )
        assert code == EXIT_OK
        assert out["decision"] == "ACCEPT"
        assert out["candidate"] > out["incumbent"]

    def test_rejects_a_tie(self, tmp_path, capsys):
        same = {f"t{i}": True for i in range(10)}
        inc, cand, split_path, _ = self._setup(tmp_path, capsys, same, dict(same))
        code, out = _run(
            capsys, "gate", "--incumbent", inc, "--candidate", cand, "--split", split_path
        )
        assert code == EXIT_LOGIC
        assert out["decision"] == "REJECT"
        assert "tie" in out["reason"]

    def test_rejects_a_regression(self, tmp_path, capsys):
        inc, cand, split_path, _ = self._setup(
            tmp_path,
            capsys,
            {f"t{i}": True for i in range(10)},
            {f"t{i}": False for i in range(10)},
        )
        code, out = _run(
            capsys, "gate", "--incumbent", inc, "--candidate", cand, "--split", split_path
        )
        assert code == EXIT_LOGIC
        assert "regress" in out["reason"]

    def test_scores_the_held_out_group_not_the_optimize_group(self, tmp_path, capsys):
        """The candidate wins only on opt tasks, so the gate must reject it."""
        inc = _write(tmp_path, "inc.json", {f"t{i}": False for i in range(10)})
        _, split = _split(capsys, tmp_path, "--results", inc, "--seed", "s1")
        split_path = _write(tmp_path, "split.json", split)
        candidate = {t: True for t in split["opt"]}
        candidate.update({t: False for t in split["sel"] + split["test"]})
        cand = _write(tmp_path, "cand.json", candidate)
        code, out = _run(
            capsys, "gate", "--incumbent", inc, "--candidate", cand, "--split", split_path
        )
        assert code == EXIT_LOGIC
        assert out["candidate"] == 0.0

    def test_refuses_when_the_split_moved(self, tmp_path, capsys):
        inc, cand, split_path, split = self._setup(
            tmp_path,
            capsys,
            {f"t{i}": False for i in range(10)},
            {f"t{i}": True for i in range(10)},
        )
        code, out = _run(
            capsys,
            "gate",
            "--incumbent",
            inc,
            "--candidate",
            cand,
            "--split",
            split_path,
            "--incumbent-fingerprint",
            "stale-fingerprint",
        )
        assert code == EXIT_LOGIC
        assert "fingerprint" in out["reason"]

    def test_accepts_when_the_fingerprint_matches(self, tmp_path, capsys):
        inc, cand, split_path, split = self._setup(
            tmp_path,
            capsys,
            {f"t{i}": False for i in range(10)},
            {f"t{i}": True for i in range(10)},
        )
        code, out = _run(
            capsys,
            "gate",
            "--incumbent",
            inc,
            "--candidate",
            cand,
            "--split",
            split_path,
            "--incumbent-fingerprint",
            split["fingerprint"],
        )
        assert code == EXIT_OK
        assert out["decision"] == "ACCEPT"

    def test_refuses_once_consultations_are_exhausted(self, tmp_path, capsys):
        inc, cand, split_path, _ = self._setup(
            tmp_path,
            capsys,
            {f"t{i}": False for i in range(10)},
            {f"t{i}": True for i in range(10)},
        )
        code, out = _run(
            capsys,
            "gate",
            "--incumbent",
            inc,
            "--candidate",
            cand,
            "--split",
            split_path,
            "--consultations",
            "5",
            "--max-consultations",
            "5",
        )
        assert code == EXIT_LOGIC
        assert "exhaust" in out["reason"]

    def test_reports_the_incremented_consultation_count(self, tmp_path, capsys):
        inc, cand, split_path, _ = self._setup(
            tmp_path,
            capsys,
            {f"t{i}": False for i in range(10)},
            {f"t{i}": True for i in range(10)},
        )
        code, out = _run(
            capsys,
            "gate",
            "--incumbent",
            inc,
            "--candidate",
            cand,
            "--split",
            split_path,
            "--consultations",
            "2",
        )
        assert code == EXIT_OK
        assert out["sel_consultations"] == 3

    def test_a_fingerprint_refusal_does_not_burn_a_consultation(self, tmp_path, capsys):
        inc, cand, split_path, _ = self._setup(
            tmp_path,
            capsys,
            {f"t{i}": False for i in range(10)},
            {f"t{i}": True for i in range(10)},
        )
        code, out = _run(
            capsys,
            "gate",
            "--incumbent",
            inc,
            "--candidate",
            cand,
            "--split",
            split_path,
            "--consultations",
            "2",
            "--incumbent-fingerprint",
            "stale",
        )
        assert code == EXIT_LOGIC
        assert out["sel_consultations"] == 2
        assert out["compared"] is False

    def test_missing_candidate_result_is_a_config_error(self, tmp_path, capsys):
        inc, _, split_path, _ = self._setup(
            tmp_path,
            capsys,
            {f"t{i}": False for i in range(10)},
            {f"t{i}": True for i in range(10)},
        )
        truncated = _write(tmp_path, "trunc.json", {"t0": True})
        code, _out = _run(
            capsys, "gate", "--incumbent", inc, "--candidate", truncated, "--split", split_path
        )
        assert code == EXIT_CONFIG

    def test_malformed_split_is_a_config_error(self, tmp_path, capsys):
        inc = _write(tmp_path, "inc.json", {f"t{i}": False for i in range(10)})
        bad_split = _write(tmp_path, "split.json", {"opt": ["t0"]})
        code, _ = _run(
            capsys, "gate", "--incumbent", inc, "--candidate", inc, "--split", bad_split
        )
        assert code == EXIT_CONFIG


# ---------------------------------------------------------------------------
# buffer
# ---------------------------------------------------------------------------


class TestBuffer:
    def test_novel_patch_passes_the_check(self, tmp_path, capsys):
        buffer = _write(tmp_path, "b.json", [])
        patches = _write(tmp_path, "p.json", [{"op": "append", "text": "x"}])
        code, out = _run(capsys, "buffer-check", "--buffer", buffer, "--patches", patches)
        assert code == EXIT_OK
        assert out["seen"] is False

    def test_missing_buffer_file_is_treated_as_empty(self, tmp_path, capsys):
        patches = _write(tmp_path, "p.json", [{"op": "append", "text": "x"}])
        code, out = _run(
            capsys, "buffer-check", "--buffer", tmp_path / "none.json", "--patches", patches
        )
        assert code == EXIT_OK
        assert out["seen"] is False

    def test_add_then_check_reports_seen(self, tmp_path, capsys):
        buffer = tmp_path / "b.json"
        patches = _write(tmp_path, "p.json", [{"op": "append", "text": "x"}])
        code, _ = _run(
            capsys, "buffer-add", "--buffer", buffer, "--patches", patches, "--reason", "regressed"
        )
        assert code == EXIT_OK
        code, out = _run(capsys, "buffer-check", "--buffer", buffer, "--patches", patches)
        assert code == EXIT_LOGIC
        assert out["seen"] is True

    def test_a_reflowed_patch_is_a_different_edit(self, tmp_path, capsys):
        """Whitespace is content: a newline in patch text splits one line into two.

        Treating the reflow as the same edit let one rejection permanently ban
        an edit that was never tried, and the buffer has no expiry.
        """
        buffer = tmp_path / "b.json"
        original = _write(tmp_path, "p.json", [{"op": "append", "text": "alpha beta"}])
        reflowed = _write(tmp_path, "p2.json", [{"op": "append", "text": "alpha   \n beta"}])
        _run(capsys, "buffer-add", "--buffer", buffer, "--patches", original, "--reason", "no")
        code, out = _run(capsys, "buffer-check", "--buffer", buffer, "--patches", reflowed)
        assert code == EXIT_OK
        assert out["seen"] is False

    def test_only_line_endings_are_normalized(self, tmp_path, capsys):
        buffer = tmp_path / "b.json"
        original = _write(tmp_path, "p.json", [{"op": "append", "text": "alpha\r\nbeta"}])
        same = _write(tmp_path, "p2.json", [{"op": "append", "text": "alpha\nbeta"}])
        _run(capsys, "buffer-add", "--buffer", buffer, "--patches", original, "--reason", "no")
        code, out = _run(capsys, "buffer-check", "--buffer", buffer, "--patches", same)
        assert code == EXIT_LOGIC
        assert out["seen"] is True

    def test_add_records_the_reason_and_fingerprint(self, tmp_path, capsys):
        buffer = tmp_path / "b.json"
        patches = _write(tmp_path, "p.json", [{"op": "append", "text": "x"}])
        _run(
            capsys, "buffer-add", "--buffer", buffer, "--patches", patches, "--reason", "regressed"
        )
        entries = json.loads(buffer.read_text(encoding="utf-8"))
        assert len(entries) == 1
        assert entries[0]["reason"] == "regressed"
        assert entries[0]["fingerprint"]
        assert entries[0]["patches"] == [{"op": "append", "anchor": None, "text": "x"}]

    def test_add_appends_rather_than_replacing(self, tmp_path, capsys):
        buffer = tmp_path / "b.json"
        first = _write(tmp_path, "p1.json", [{"op": "append", "text": "x"}])
        second = _write(tmp_path, "p2.json", [{"op": "append", "text": "y"}])
        _run(capsys, "buffer-add", "--buffer", buffer, "--patches", first, "--reason", "a")
        _run(capsys, "buffer-add", "--buffer", buffer, "--patches", second, "--reason", "b")
        assert len(json.loads(buffer.read_text(encoding="utf-8"))) == 2

    def test_add_is_idempotent_for_the_same_patch(self, tmp_path, capsys):
        buffer = tmp_path / "b.json"
        patches = _write(tmp_path, "p.json", [{"op": "append", "text": "x"}])
        _run(capsys, "buffer-add", "--buffer", buffer, "--patches", patches, "--reason", "a")
        _run(capsys, "buffer-add", "--buffer", buffer, "--patches", patches, "--reason", "a")
        assert len(json.loads(buffer.read_text(encoding="utf-8"))) == 1

    def test_corrupt_buffer_is_a_config_error(self, tmp_path, capsys):
        buffer = tmp_path / "b.json"
        buffer.write_text("{oops", encoding="utf-8")
        patches = _write(tmp_path, "p.json", [{"op": "append", "text": "x"}])
        code, _ = _run(capsys, "buffer-check", "--buffer", buffer, "--patches", patches)
        assert code == EXIT_CONFIG


# ---------------------------------------------------------------------------
# dispatch
# ---------------------------------------------------------------------------


class TestDispatch:
    def test_no_subcommand_exits_nonzero(self, capsys):
        assert oa.main([]) != EXIT_OK

    def test_unknown_subcommand_exits(self, capsys):
        with pytest.raises(SystemExit):
            oa.main(["frobnicate"])


# ---------------------------------------------------------------------------
# malformed inputs
# ---------------------------------------------------------------------------


class TestMalformedInputs:
    def test_unreadable_json_path_is_a_config_error(self, tmp_path, capsys):
        """A directory where a file belongs raises OSError, not FileNotFoundError."""
        code, _ = _run(capsys, "extract", "--kind", "agent", "--input", tmp_path)
        assert code == EXIT_CONFIG

    def test_unreadable_text_path_is_a_config_error(self, tmp_path, capsys):
        code, _ = _run(capsys, "extract", "--kind", "hook", "--input", tmp_path)
        assert code == EXIT_CONFIG

    def test_results_must_be_an_object(self, tmp_path, capsys):
        results = _write(tmp_path, "r.json", ["t0", "t1"])
        code, _ = _split(capsys, tmp_path, "--results", results, "--seed", "s1")
        assert code == EXIT_CONFIG

    def test_results_must_be_boolean_valued(self, tmp_path, capsys):
        results = _write(tmp_path, "r.json", {"t0": 1, "t1": "yes"})
        code, _ = _split(capsys, tmp_path, "--results", results, "--seed", "s1")
        assert code == EXIT_CONFIG

    def test_empty_patch_array_is_a_config_error(self, tmp_path, capsys):
        target = tmp_path / "a.md"
        target.write_text("line one\n", encoding="utf-8")
        patches = _write(tmp_path, "p.json", [])
        code, _ = _run(capsys, "apply", "--file", target, "--patches", patches, "--budget", "1")
        assert code == EXIT_CONFIG

    def test_split_must_be_an_object(self, tmp_path, capsys):
        results = _write(tmp_path, "r.json", _results(10, 0))
        split = _write(tmp_path, "split.json", ["opt", "sel", "test"])
        code, _ = _run(capsys, "score", "--results", results, "--split", split)
        assert code == EXIT_CONFIG

    def test_negative_consultations_is_a_config_error(self, tmp_path, capsys):
        results = _write(tmp_path, "r.json", _results(10, 0))
        _, split = _split(capsys, tmp_path, "--results", results, "--seed", "s1")
        split_path = _write(tmp_path, "split.json", split)
        code, _ = _run(
            capsys,
            "gate",
            "--incumbent",
            results,
            "--candidate",
            results,
            "--split",
            split_path,
            "--consultations",
            "-1",
        )
        assert code == EXIT_CONFIG

    def test_buffer_must_be_an_array(self, tmp_path, capsys):
        buffer = _write(tmp_path, "b.json", {"not": "a list"})
        patches = _write(tmp_path, "p.json", [{"op": "append", "text": "x"}])
        code, _ = _run(capsys, "buffer-check", "--buffer", buffer, "--patches", patches)
        assert code == EXIT_CONFIG


class TestSplitFileIsSelfValidating:
    """A split file has to prove its own integrity, with no flag to remember.

    Two adversarial reviewers plus both PR bots flagged the same hole
    independently: the only drift check compared the split file's stored
    fingerprint against a --incumbent-fingerprint the caller supplied, so a
    caller who omitted the flag got no check at all, and the stored value was
    trusted even when the group membership beside it had been edited. A
    guarantee that is opt-in is not a guarantee. The gate now recomputes the
    fingerprint from the split file's own contents on every call.
    """

    def _setup(self, tmp_path, capsys):
        inc = _write(tmp_path, "inc.json", {f"t{i}": False for i in range(10)})
        cand = _write(tmp_path, "cand.json", {f"t{i}": True for i in range(10)})
        _, split = _split(capsys, tmp_path, "--results", inc, "--seed", "s1")
        return inc, cand, split

    def test_an_untampered_split_gates_normally(self, tmp_path, capsys):
        inc, cand, split = self._setup(tmp_path, capsys)
        path = _write(tmp_path, "split.json", split)
        code, out = _run(capsys, "gate", "--incumbent", inc, "--candidate", cand,
                         "--split", path)
        assert code == 0
        assert out["decision"] == "ACCEPT"

    def test_a_task_moved_between_groups_is_refused(self, tmp_path, capsys):
        """The union is unchanged, so only recomputation catches this."""
        inc, cand, split = self._setup(tmp_path, capsys)
        moved = split["opt"][0]
        split["opt"] = [t for t in split["opt"] if t != moved]
        split["sel"] = [*split["sel"], moved]
        path = _write(tmp_path, "split.json", split)
        code, out = _run(capsys, "gate", "--incumbent", inc, "--candidate", cand,
                         "--split", path)
        assert code == 0
        assert out["decision"] == "REJECT"
        assert "fingerprint" in out["reason"]
        assert "score" not in out and "candidate" not in out

    def test_an_added_task_is_refused(self, tmp_path, capsys):
        inc, cand, split = self._setup(tmp_path, capsys)
        split["sel"] = [*split["sel"], "smuggled"]
        path = _write(tmp_path, "split.json", split)
        code, out = _run(capsys, "gate", "--incumbent", inc, "--candidate", cand,
                         "--split", path)
        assert out["decision"] == "REJECT"
        assert "fingerprint" in out["reason"]

    def test_an_edited_fingerprint_is_refused(self, tmp_path, capsys):
        inc, cand, split = self._setup(tmp_path, capsys)
        split["fingerprint"] = "0" * 64
        path = _write(tmp_path, "split.json", split)
        code, out = _run(capsys, "gate", "--incumbent", inc, "--candidate", cand,
                         "--split", path)
        assert out["decision"] == "REJECT"

    def test_an_edited_seed_is_refused(self, tmp_path, capsys):
        inc, cand, split = self._setup(tmp_path, capsys)
        split["seed"] = "s2"
        path = _write(tmp_path, "split.json", split)
        code, out = _run(capsys, "gate", "--incumbent", inc, "--candidate", cand,
                         "--split", path)
        assert out["decision"] == "REJECT"

    def test_a_refused_split_costs_no_consultation(self, tmp_path, capsys):
        inc, cand, split = self._setup(tmp_path, capsys)
        split["sel"] = [*split["sel"], "smuggled"]
        path = _write(tmp_path, "split.json", split)
        _, out = _run(capsys, "gate", "--incumbent", inc, "--candidate", cand,
                      "--split", path, "--consultations", "0",
                      "--max-consultations", "3")
        assert out["consultations"] == 0

    def test_a_split_file_without_ratios_is_refused(self, tmp_path, capsys):
        """Older split files cannot be verified, so they cannot be trusted."""
        inc, cand, split = self._setup(tmp_path, capsys)
        del split["sel_ratio"]
        path = _write(tmp_path, "split.json", split)
        code, _ = _run(capsys, "gate", "--incumbent", inc, "--candidate", cand,
                       "--split", path)
        assert code == EXIT_CONFIG

    def test_a_non_numeric_ratio_is_a_config_error(self, tmp_path, capsys):
        """The keys are present, so only the redraw catches the bad value."""
        inc, cand, split = self._setup(tmp_path, capsys)
        split["sel_ratio"] = "half"
        path = _write(tmp_path, "split.json", split)
        code, _ = _run(capsys, "gate", "--incumbent", inc, "--candidate", cand,
                       "--split", path)
        assert code == EXIT_CONFIG

    def test_split_writes_the_ratios_it_used(self, tmp_path, capsys):
        inc = _write(tmp_path, "inc.json", {f"t{i}": False for i in range(10)})
        _, split = _split(capsys, tmp_path, "--results", inc, "--seed", "s1",
                        "--sel-ratio", "0.4", "--test-ratio", "0.2")
        assert split["sel_ratio"] == 0.4
        assert split["test_ratio"] == 0.2


class TestMalformedInputsAreConfigErrors:
    """Broken input files must name themselves, not raise a traceback.

    Every one of these was found by CodeRabbit on PR #3430 and reproduced
    before being fixed. The CLI is driven by an unattended loop, so a
    traceback is not a diagnostic anyone reads; it is a crash the loop cannot
    branch on.
    """

    def test_a_non_utf8_artifact_is_a_config_error(self, tmp_path, capsys):
        """UnicodeDecodeError subclasses ValueError, so the OSError arm missed it."""
        target = tmp_path / "artifact.md"
        target.write_bytes(b"valid ascii \xff\xfe then garbage")
        patches = _write(tmp_path, "p.json", [{"op": "append", "text": "x"}])
        code, out = _run(capsys, "apply", "--file", target, "--patches", patches,
                         "--budget", "1")
        assert code == EXIT_CONFIG
        assert "artifact.md" in out["error"]

    def test_a_buffer_of_non_objects_is_a_config_error(self, tmp_path, capsys):
        buf = _write(tmp_path, "buf.json", [1, 2])
        patches = _write(tmp_path, "p.json", [{"op": "append", "text": "x"}])
        code, _ = _run(capsys, "buffer-check", "--buffer", buf, "--patches", patches)
        assert code == EXIT_CONFIG


class TestApplyWritesAtomically:
    """A half-written artifact is worse than a refused edit.

    `apply` overwrites the artifact the loop is optimizing. A direct
    write_text truncates first, so an interrupt or a full disk mid-write
    leaves the artifact destroyed and the loop with nothing to fall back to.
    """

    def _setup(self, tmp_path):
        target = tmp_path / "artifact.md"
        target.write_text("original\n", encoding="utf-8")
        patches = _write(tmp_path, "p.json", [{"op": "append", "text": "added"}])
        return target, patches

    def test_a_normal_apply_still_writes(self, tmp_path, capsys):
        target, patches = self._setup(tmp_path)
        code, out = _run(capsys, "apply", "--file", target, "--patches", patches,
                         "--budget", "1")
        assert code == 0 and out["written"] is True
        assert "added" in target.read_text(encoding="utf-8")

    def test_a_failed_replace_leaves_the_original_intact(
        self, tmp_path, capsys, monkeypatch
    ):
        target, patches = self._setup(tmp_path)
        monkeypatch.setattr(oa.os, "replace", _boom)
        code, out = _run(capsys, "apply", "--file", target, "--patches", patches,
                         "--budget", "1")
        assert code == EXIT_CONFIG
        assert target.read_text(encoding="utf-8") == "original\n"

    def test_a_failed_replace_leaves_no_temp_file(
        self, tmp_path, capsys, monkeypatch
    ):
        target, patches = self._setup(tmp_path)
        monkeypatch.setattr(oa.os, "replace", _boom)
        _run(capsys, "apply", "--file", target, "--patches", patches, "--budget", "1")
        assert sorted(p.name for p in tmp_path.iterdir()) == ["artifact.md", "p.json"]


class TestHeldOutGroupsAreNotReadable:
    """The optimizer-facing surface must not hand back what the gate withholds.

    An adversarial review (gpt-5.6-sol, 2026-07-26) found the withholding was
    nominal: `split` printed every selection and test id, and `score` defaulted
    to the selection group and accepted the test group, unmetered. An agent
    could read the held-out answers for free and never touch the consultation
    budget. A hash around openly published data is not withholding.
    """

    def _tasks(self, tmp_path):
        return _write(tmp_path, "res.json", {f"t{i}": True for i in range(10)})

    def test_split_prints_optimize_ids_but_not_held_out_ids(self, tmp_path, capsys):
        out_path = tmp_path / "split.json"
        code, out = _run(capsys, "split", "--results", self._tasks(tmp_path),
                         "--seed", "s", "--out", out_path)
        assert code == 0
        assert out["opt"], "the optimizer needs to know what it may work on"
        assert "sel" not in out and "test" not in out

    def test_split_reports_held_out_sizes_without_membership(self, tmp_path, capsys):
        out_path = tmp_path / "split.json"
        _, out = _run(capsys, "split", "--results", self._tasks(tmp_path),
                      "--seed", "s", "--out", out_path)
        assert out["n_sel"] == 4 and out["n_test"] == 0

    def test_the_full_split_still_reaches_the_gate_through_the_file(
        self, tmp_path, capsys
    ):
        out_path = tmp_path / "split.json"
        _run(capsys, "split", "--results", self._tasks(tmp_path), "--seed", "s",
             "--out", out_path)
        written = json.loads(out_path.read_text(encoding="utf-8"))
        assert len(written["sel"]) == 4
        assert written["fingerprint"]

    def test_score_refuses_the_selection_group(self, tmp_path, capsys):
        out_path = tmp_path / "split.json"
        _run(capsys, "split", "--results", self._tasks(tmp_path), "--seed", "s",
             "--out", out_path)
        with pytest.raises(SystemExit):
            _run(capsys, "score", "--results", self._tasks(tmp_path),
                 "--split", out_path, "--group", "sel")

    def test_score_refuses_the_test_group(self, tmp_path, capsys):
        out_path = tmp_path / "split.json"
        _run(capsys, "split", "--results", self._tasks(tmp_path), "--seed", "s",
             "--out", out_path)
        with pytest.raises(SystemExit):
            _run(capsys, "score", "--results", self._tasks(tmp_path),
                 "--split", out_path, "--group", "test")

    def test_score_still_reads_the_optimize_group(self, tmp_path, capsys):
        out_path = tmp_path / "split.json"
        _run(capsys, "split", "--results", self._tasks(tmp_path), "--seed", "s",
             "--out", out_path)
        code, out = _run(capsys, "score", "--results", self._tasks(tmp_path),
                         "--split", out_path)
        assert code == 0 and out["group"] == "opt" and out["score"] == 1.0
