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
import os
import sys
import traceback
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


def _key_of(split_path):
    """The held-out key the gate will use for this split file."""
    return oa._holdout_key(json.loads(Path(split_path).read_text(encoding="utf-8")))


def _raise_boom(*_args, **_kwargs):
    """Stand-in for any failure between taking the lock and releasing it."""
    raise RuntimeError("boom")


@pytest.fixture(autouse=True)
def _isolated_ledger_root(tmp_path_factory, monkeypatch):
    """Point the consultation ledgers at this test's own directory.

    They are keyed by split fingerprint in one fixed root, which is what stops
    a caller buying a fresh budget by renaming the split. The same property
    means two tests that draw the same split share a ledger, so the root has to
    move per test rather than the key. It sits outside `tmp_path` because tests
    that assert on the contents of `tmp_path` should not see it.
    """
    monkeypatch.setenv("EVAL_LEDGER_DIR", str(tmp_path_factory.mktemp("ledgers")))


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


def _run_gate(capsys, tmp_path, *args, spent=None, cap=100):
    """Run `gate`, supplying the two arguments it now requires.

    The consultation count used to arrive on the command line, which meant a
    caller that passed zero every time had an unlimited budget. The cap and
    the incumbent fingerprint went the same way: both defaulted to a value
    that skipped the check. Tests that are not about those arguments get
    working defaults here; `spent` pre-seeds the derived ledger for tests that
    need the gate to believe consultations have already happened.
    """
    argv = list(args)
    if "--max-consultations" not in argv:
        argv += ["--max-consultations", str(cap)]
    effective = int(argv[argv.index("--max-consultations") + 1])
    split = _split_of(argv)
    if "--incumbent-fingerprint" not in argv and isinstance(split, dict):
        argv += ["--incumbent-fingerprint", str(split.get("fingerprint", "unknown"))]
    if spent is not None and isinstance(split, dict):
        key = oa._holdout_key(split)
        seeded = oa._ledger_path(key)
        seeded.parent.mkdir(parents=True, exist_ok=True)
        seeded.write_text(
            json.dumps({"consultations": spent, "holdout": key,
                        "max_consultations": effective}),
            encoding="utf-8",
        )
    return _run(capsys, "gate", *argv)


def _split_of(argv):
    """The split record behind `--split`, or None when it is unreadable.

    Config-error tests deliberately point `--split` at missing or malformed
    files, and the helper still has to run them.
    """
    if "--split" not in argv:
        return None
    try:
        return json.loads(Path(argv[argv.index("--split") + 1]).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None


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

    def test_rule_extract_refuses_errored_mechanism(self, tmp_path, capsys):
        scenarios = _write(
            tmp_path,
            "scen.json",
            [
                {
                    "id": "S1",
                    "negative_case": False,
                    "mechanisms": {
                        "full": {
                            "error": "model timeout",
                            "scores": {
                                "activation_score": 0,
                                "citation_score": 0,
                                "behavior_score": 0,
                            },
                        }
                    },
                }
            ],
        )
        code, out = _run(capsys, "extract", "--kind", "rule", "--input", scenarios)
        assert code == EXIT_CONFIG
        assert "degraded rule report" in out["error"]
        assert "S1" in out["error"]

    def test_rule_extract_clean_report_succeeds(self, tmp_path, capsys):
        scenarios = _write(
            tmp_path,
            "scen.json",
            [
                {
                    "id": "S2",
                    "negative_case": False,
                    "mechanisms": {
                        "full": {
                            "scores": {
                                "activation_score": 5,
                                "citation_score": 4,
                                "behavior_score": 5,
                            }
                        }
                    },
                }
            ],
        )
        code, out = _run(capsys, "extract", "--kind", "rule", "--input", scenarios)
        assert code == EXIT_OK
        assert out == {"S2": True}

    def test_rule_extract_refuses_judge_failure_verdict(self, tmp_path, capsys):
        envelope = {
            "rules": {
                "refactoring": {
                    "summary": {"verdict": "FAIL_JUDGE_ERRORS"},
                    "scenarios": [
                        {
                            "id": "S3",
                            "negative_case": False,
                            "mechanisms": {
                                "full": {
                                    "scores": {
                                        "activation_score": 0,
                                        "citation_score": 0,
                                        "behavior_score": 0,
                                        "judge_failed": True,
                                    }
                                }
                            },
                        }
                    ],
                }
            }
        }
        path = _write(tmp_path, "rules.json", envelope)
        code, out = _run(capsys, "extract", "--kind", "rule", "--input", path)
        assert code == EXIT_CONFIG
        assert "refactoring::S3" in out["error"]

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
            _run_gate(
                capsys,
                tmp_path,
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
        _, out = _run_gate(
            capsys, tmp_path, "--incumbent", inc, "--candidate", cand, "--split", split_path
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
        code, out = _run_gate(
            capsys,
            tmp_path,
            "--incumbent",
            inc,
            "--candidate",
            cand,
            "--split",
            split_path,
            "--max-consultations",
            "3",
            spent=3,
        )
        assert code == EXIT_LOGIC
        assert out["compared"] is False
        assert "candidate" not in out
        assert "incumbent" not in out

    def test_a_moved_fingerprint_withholds_the_scores(self, tmp_path, capsys):
        inc, cand, split_path, _ = self._setup(tmp_path, capsys)
        code, out = _run_gate(
            capsys,
            tmp_path,
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
        _, out = _run_gate(
            capsys,
            tmp_path,
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
        _, out = _run_gate(
            capsys, tmp_path, "--incumbent", inc, "--candidate", cand, "--split", split_path
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
        return _run_gate(
            capsys, tmp_path, "--incumbent", inc, "--candidate", cand, "--split", split_path
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
        _, out = _run_gate(
            capsys,
            tmp_path,
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
        code, out = _run_gate(
            capsys, tmp_path, "--incumbent", inc, "--candidate", cand, "--split", split_path
        )
        assert code == EXIT_OK
        assert out["decision"] == "ACCEPT"
        assert out["candidate"] > out["incumbent"]

    def test_rejects_a_tie(self, tmp_path, capsys):
        same = {f"t{i}": True for i in range(10)}
        inc, cand, split_path, _ = self._setup(tmp_path, capsys, same, dict(same))
        code, out = _run_gate(
            capsys, tmp_path, "--incumbent", inc, "--candidate", cand, "--split", split_path
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
        code, out = _run_gate(
            capsys, tmp_path, "--incumbent", inc, "--candidate", cand, "--split", split_path
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
        code, out = _run_gate(
            capsys, tmp_path, "--incumbent", inc, "--candidate", cand, "--split", split_path
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
        code, out = _run_gate(
            capsys,
            tmp_path,
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
        code, out = _run_gate(
            capsys,
            tmp_path,
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
        code, out = _run_gate(
            capsys,
            tmp_path,
            "--incumbent",
            inc,
            "--candidate",
            cand,
            "--split",
            split_path,
            "--max-consultations",
            "5",
            spent=5,
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
        code, out = _run_gate(
            capsys,
            tmp_path,
            "--incumbent",
            inc,
            "--candidate",
            cand,
            "--split",
            split_path,
            spent=2,
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
        code, out = _run_gate(
            capsys,
            tmp_path,
            "--incumbent",
            inc,
            "--candidate",
            cand,
            "--split",
            split_path,
            "--incumbent-fingerprint",
            "stale",
            spent=2,
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
        code, out = _run_gate(
            capsys, tmp_path, "--incumbent", inc, "--candidate", truncated, "--split", split_path
        )
        assert (code, out["decision"], out["compared"]) == (EXIT_LOGIC, "REJECT", False)

    def test_malformed_split_is_a_config_error(self, tmp_path, capsys):
        inc = _write(tmp_path, "inc.json", {f"t{i}": False for i in range(10)})
        bad_split = _write(tmp_path, "split.json", {"opt": ["t0"]})
        code, _ = _run_gate(
            capsys, tmp_path, "--incumbent", inc, "--candidate", inc, "--split", bad_split
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

    def test_a_negative_ledger_count_is_a_config_error(self, tmp_path, capsys):
        """This used to arrive as `--consultations -1` on the command line.

        The count moved into a ledger the gate writes, so the malformed input
        moved with it. A negative count is still refused rather than treated
        as zero.
        """
        results = _write(tmp_path, "r.json", _results(10, 0))
        _, split = _split(capsys, tmp_path, "--results", results, "--seed", "s1")
        split_path = _write(tmp_path, "split2.json", split)
        code, _ = _run_gate(
            capsys,
            tmp_path,
            "--incumbent",
            results,
            "--candidate",
            results,
            "--split",
            split_path,
            spent=-1,
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
        code, out = _run_gate(capsys, tmp_path, "--incumbent", inc, "--candidate", cand,
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
        code, out = _run_gate(capsys, tmp_path, "--incumbent", inc, "--candidate", cand,
                         "--split", path)
        assert code == EXIT_LOGIC
        assert out["decision"] == "REJECT"
        assert "fingerprint" in out["reason"]
        assert "score" not in out and "candidate" not in out

    def test_an_added_task_is_refused(self, tmp_path, capsys):
        inc, cand, split = self._setup(tmp_path, capsys)
        split["sel"] = [*split["sel"], "smuggled"]
        path = _write(tmp_path, "split.json", split)
        code, out = _run_gate(capsys, tmp_path, "--incumbent", inc, "--candidate", cand,
                         "--split", path)
        assert out["decision"] == "REJECT"
        assert "fingerprint" in out["reason"]

    def test_an_edited_fingerprint_is_refused(self, tmp_path, capsys):
        inc, cand, split = self._setup(tmp_path, capsys)
        split["fingerprint"] = "0" * 64
        path = _write(tmp_path, "split.json", split)
        code, out = _run_gate(capsys, tmp_path, "--incumbent", inc, "--candidate", cand,
                         "--split", path)
        assert out["decision"] == "REJECT"

    def test_an_edited_seed_is_refused(self, tmp_path, capsys):
        inc, cand, split = self._setup(tmp_path, capsys)
        split["seed"] = "s2"
        path = _write(tmp_path, "split.json", split)
        code, out = _run_gate(capsys, tmp_path, "--incumbent", inc, "--candidate", cand,
                         "--split", path)
        assert out["decision"] == "REJECT"

    def test_a_refused_split_costs_no_consultation(self, tmp_path, capsys):
        inc, cand, split = self._setup(tmp_path, capsys)
        split["sel"] = [*split["sel"], "smuggled"]
        path = _write(tmp_path, "split.json", split)
        _, out = _run_gate(capsys, tmp_path, "--incumbent", inc, "--candidate", cand,
                           "--split", path, "--max-consultations", "3")
        assert out["consultations"] == 0
        assert not (tmp_path / "ledger.json").exists()

    def test_a_split_file_without_ratios_is_refused(self, tmp_path, capsys):
        """Older split files cannot be verified, so they cannot be trusted."""
        inc, cand, split = self._setup(tmp_path, capsys)
        del split["sel_ratio"]
        path = _write(tmp_path, "split.json", split)
        code, _ = _run_gate(capsys, tmp_path, "--incumbent", inc, "--candidate", cand,
                       "--split", path)
        assert code == EXIT_CONFIG

    def test_a_non_numeric_ratio_is_a_config_error(self, tmp_path, capsys):
        """The keys are present, so only the redraw catches the bad value."""
        inc, cand, split = self._setup(tmp_path, capsys)
        split["sel_ratio"] = "half"
        path = _write(tmp_path, "split.json", split)
        code, _ = _run_gate(capsys, tmp_path, "--incumbent", inc, "--candidate", cand,
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


class TestConsultationLedgerIsHeldByTheGate:
    """A budget the caller passes in is not a budget.

    `--consultations` defaulted to 0 and arrived on the command line on every
    invocation, so a loop that simply never incremented it had an unlimited
    budget while appearing to respect a cap. An adversarial review
    (gpt-5.6-sol, 2026-07-26) reproduced ACCEPT twice under a cap of one by
    passing zero both times. The count now lives in a ledger the gate writes,
    bound to the split fingerprint so redrawing cannot reset it either.
    """

    def _fixture(self, tmp_path, capsys):
        inc = _write(tmp_path, "inc.json", {f"t{i}": i % 3 != 0 for i in range(12)})
        _run(capsys, "split", "--results", inc, "--seed", "s1",
             "--out", tmp_path / "split.json")
        cand = _write(tmp_path, "cand.json", {f"t{i}": True for i in range(12)})
        split = tmp_path / "split.json"
        record = json.loads(split.read_text(encoding="utf-8"))
        return inc, cand, split, oa._ledger_path(oa._holdout_key(record))

    def _gate(self, capsys, inc, cand, split, _ledger, cap=100):
        """The ledger path is derived, so tests receive it rather than choose it."""
        fingerprint = _split_of(["--split", str(split)]) or {}
        return _run(capsys, "gate", "--incumbent", inc, "--candidate", cand,
                    "--split", split, "--max-consultations", str(cap),
                    "--incumbent-fingerprint",
                    str(fingerprint.get("fingerprint", "unknown")))

    def test_a_compared_decision_writes_the_count(self, tmp_path, capsys):
        inc, cand, split, ledger = self._fixture(tmp_path, capsys)
        _, out = self._gate(capsys, inc, cand, split, ledger)
        assert out["sel_consultations"] == 1
        assert json.loads(ledger.read_text(encoding="utf-8"))["consultations"] == 1

    def test_the_cap_holds_across_separate_invocations(self, tmp_path, capsys):
        inc, cand, split, ledger = self._fixture(tmp_path, capsys)
        first, _ = self._gate(capsys, inc, cand, split, ledger, cap=1)
        assert first == EXIT_OK
        second, out = self._gate(capsys, inc, cand, split, ledger, cap=1)
        assert second == EXIT_LOGIC
        assert "exhaust" in out["reason"]

    def test_a_refused_decision_does_not_spend_budget(self, tmp_path, capsys):
        inc, cand, split, ledger = self._fixture(tmp_path, capsys)
        tampered = json.loads(split.read_text(encoding="utf-8"))
        tampered["sel"], tampered["opt"] = tampered["opt"], tampered["sel"]
        split.write_text(json.dumps(tampered), encoding="utf-8")
        self._gate(capsys, inc, cand, split, ledger)
        assert not ledger.exists()

    def test_a_ledger_from_a_different_split_is_refused(self, tmp_path, capsys):
        inc, cand, split, ledger = self._fixture(tmp_path, capsys)
        ledger.write_text(
            json.dumps({"consultations": 0, "fingerprint": "not-this-split",
                        "max_consultations": 100}),
            encoding="utf-8",
        )
        code, out = self._gate(capsys, inc, cand, split, ledger)
        assert code == EXIT_LOGIC
        assert "ledger" in out["reason"]
        assert "candidate" not in out

    @pytest.mark.parametrize("payload", [
        '{"consultations": "many"}',
        '{"consultations": true}',
        '["not", "an", "object"]',
    ])
    def test_a_malformed_ledger_is_a_config_error(self, tmp_path, capsys, payload):
        inc, cand, split, ledger = self._fixture(tmp_path, capsys)
        ledger.write_text(payload, encoding="utf-8")
        code, _ = self._gate(capsys, inc, cand, split, ledger)
        assert code == EXIT_CONFIG

    def test_a_first_run_needs_no_existing_ledger(self, tmp_path, capsys):
        inc, cand, split, ledger = self._fixture(tmp_path, capsys)
        code, _ = self._gate(capsys, inc, cand, split, ledger)
        assert code == EXIT_OK and ledger.exists()

    def test_a_negative_cap_is_a_config_error(self, tmp_path, capsys):
        """`gate()` rejects a nonsense cap; the CLI reports it rather than crashing."""
        inc, cand, split, ledger = self._fixture(tmp_path, capsys)
        code, out = self._gate(capsys, inc, cand, split, ledger, cap=-1)
        assert code == EXIT_CONFIG
        assert not ledger.exists()
        assert out["error"]

    def test_a_result_missing_a_held_out_task_refuses_without_naming_it(self, tmp_path, capsys):
        """The gate cannot score a held-out task the run never reported.

        Distinct from a truncated file: this one parses, covers every task the
        optimizer could see, and is short only on the group the optimizer is
        not allowed to look at. It refuses rather than producing a verdict, it
        does not say which task is missing, and it costs a consultation.
        """
        inc, cand, split, ledger = self._fixture(tmp_path, capsys)
        partition = json.loads(split.read_text(encoding="utf-8"))
        dropped = partition["sel"][0]
        short = {k: v for k, v in json.loads(Path(cand).read_text(encoding="utf-8")).items()
                 if k != dropped}
        short_path = _write(tmp_path, "short.json", short)
        code, out = self._gate(capsys, inc, short_path, split, ledger)
        assert (code, out["decision"], out["compared"]) == (EXIT_LOGIC, "REJECT", False)
        assert dropped not in json.dumps(out)
        assert ledger.exists()


class TestTheBudgetCapIsPinnedByTheLedger:
    """A cap the caller re-supplies every invocation is not a cap.

    The ledger fixed the count but left the limit on the command line, where
    `--max-consultations` defaulted to unlimited. A second adversarial review
    (gpt-5.6-sol, 2026-07-26) named the two remaining ways out: never pass the
    flag, or raise it once the budget bites. Both are the same defect the
    ledger was written to close, so the limit is now pinned the same way the
    count is.
    """

    def _fixture(self, tmp_path, capsys):
        inc = _write(tmp_path, "inc.json", {f"t{i}": i % 3 != 0 for i in range(12)})
        _run(capsys, "split", "--results", inc, "--seed", "s1",
             "--out", tmp_path / "split.json")
        cand = _write(tmp_path, "cand.json", {f"t{i}": True for i in range(12)})
        split = tmp_path / "split.json"
        fingerprint = json.loads(split.read_text(encoding="utf-8"))["fingerprint"]
        return inc, cand, split, fingerprint

    def _gate(self, capsys, inc, cand, split, fingerprint, cap):
        return _run(capsys, "gate", "--incumbent", inc, "--candidate", cand,
                    "--split", split, "--max-consultations", str(cap),
                    "--incumbent-fingerprint", fingerprint)

    def test_a_missing_cap_is_a_usage_error(self, tmp_path, capsys):
        """No default. An unlimited budget must be typed, not inherited."""
        inc, cand, split, fingerprint = self._fixture(tmp_path, capsys)
        with pytest.raises(SystemExit) as exc:
            _run(capsys, "gate", "--incumbent", inc, "--candidate", cand,
                 "--split", split, "--incumbent-fingerprint", fingerprint)
        assert exc.value.code == EXIT_CONFIG

    def test_the_first_gate_records_the_cap(self, tmp_path, capsys):
        inc, cand, split, fingerprint = self._fixture(tmp_path, capsys)
        code, _ = self._gate(capsys, inc, cand, split, fingerprint, 3)
        assert code == EXIT_OK
        key = oa._holdout_key(json.loads(split.read_text(encoding="utf-8")))
        ledger = json.loads(oa._ledger_path(key).read_text(encoding="utf-8"))
        assert ledger["max_consultations"] == 3

    def test_raising_the_cap_mid_run_is_refused(self, tmp_path, capsys):
        """The reproduced attack: gate under one, then ask for five."""
        inc, cand, split, fingerprint = self._fixture(tmp_path, capsys)
        assert self._gate(capsys, inc, cand, split, fingerprint, 1)[0] == EXIT_OK
        code, out = self._gate(capsys, inc, cand, split, fingerprint, 5)
        assert code == EXIT_LOGIC
        assert out["decision"] == "REJECT"
        assert out["compared"] is False
        assert "1" in out["reason"] and "5" in out["reason"]

    def test_lowering_the_cap_mid_run_is_refused(self, tmp_path, capsys):
        """Symmetric on purpose: any cap change means a different run."""
        inc, cand, split, fingerprint = self._fixture(tmp_path, capsys)
        assert self._gate(capsys, inc, cand, split, fingerprint, 4)[0] == EXIT_OK
        code, out = self._gate(capsys, inc, cand, split, fingerprint, 2)
        assert code == EXIT_LOGIC
        assert out["compared"] is False

    def test_the_same_cap_is_not_a_change(self, tmp_path, capsys):
        inc, cand, split, fingerprint = self._fixture(tmp_path, capsys)
        assert self._gate(capsys, inc, cand, split, fingerprint, 4)[0] == EXIT_OK
        code, out = self._gate(capsys, inc, cand, split, fingerprint, 4)
        assert code == EXIT_OK
        assert out["sel_consultations"] == 2

    @pytest.mark.parametrize("recorded", ["five", -1, None, True])
    def test_a_malformed_recorded_cap_is_a_config_error(self, tmp_path, capsys, recorded):
        inc, cand, split, fingerprint = self._fixture(tmp_path, capsys)
        key = oa._holdout_key(json.loads(split.read_text(encoding="utf-8")))
        seeded = oa._ledger_path(key)
        seeded.parent.mkdir(parents=True, exist_ok=True)
        seeded.write_text(
            json.dumps({"consultations": 0, "holdout": key,
                        "max_consultations": recorded}),
            encoding="utf-8",
        )
        code, _ = self._gate(capsys, inc, cand, split, fingerprint, 3)
        assert code == EXIT_CONFIG


class TestTheBudgetIsKeyedByTheSplitItself:
    """A ledger path derived from a caller-supplied path is still caller-supplied.

    `--ledger` was replaced by a path derived from `--split`, which moved the
    reset instead of closing it: a third adversarial review (gpt-5.6-sol,
    2026-07-26) pointed out that the caller still names the split, so copying
    `split.json` to `split2.json` produced an identical fingerprint with no
    ledger beside it, and the budget started over. The key is now the
    fingerprint in one fixed directory. Same split content, same budget,
    whatever the file is called. A fresh budget needs a fresh seed.
    """

    def _fixture(self, tmp_path, capsys, seed="s1"):
        inc = _write(tmp_path, "inc.json", {f"t{i}": i % 3 != 0 for i in range(12)})
        _run(capsys, "split", "--results", inc, "--seed", seed,
             "--out", tmp_path / "split.json")
        cand = _write(tmp_path, "cand.json", {f"t{i}": True for i in range(12)})
        split = tmp_path / "split.json"
        record = json.loads(split.read_text(encoding="utf-8"))
        return inc, cand, split, record["fingerprint"]

    def _gate(self, capsys, inc, cand, split, fingerprint, cap=3):
        return _run(capsys, "gate", "--incumbent", inc, "--candidate", cand,
                    "--split", split, "--max-consultations", str(cap),
                    "--incumbent-fingerprint", fingerprint)

    def test_the_ledger_is_written_under_the_state_root(self, tmp_path, capsys):
        inc, cand, split, fingerprint = self._fixture(tmp_path, capsys)
        self._gate(capsys, inc, cand, split, fingerprint)
        key = oa._holdout_key(json.loads(split.read_text(encoding="utf-8")))
        assert oa._ledger_path(key).exists()

    def test_a_copied_split_shares_the_budget(self, tmp_path, capsys):
        """The reported attack: copy the split, keep the fingerprint, reset the count."""
        inc, cand, split, fingerprint = self._fixture(tmp_path, capsys)
        _, first = self._gate(capsys, inc, cand, split, fingerprint)
        copy = tmp_path / "split-copy.json"
        copy.write_text(split.read_text(encoding="utf-8"), encoding="utf-8")
        _, second = self._gate(capsys, inc, cand, copy, fingerprint)
        assert (first["sel_consultations"], second["sel_consultations"]) == (1, 2)

    def test_a_renamed_split_shares_the_budget(self, tmp_path, capsys):
        inc, cand, split, fingerprint = self._fixture(tmp_path, capsys)
        self._gate(capsys, inc, cand, split, fingerprint)
        moved = tmp_path / "nested" / "renamed.json"
        moved.parent.mkdir()
        moved.write_text(split.read_text(encoding="utf-8"), encoding="utf-8")
        split.unlink()
        _, second = self._gate(capsys, inc, cand, moved, fingerprint)
        assert second["sel_consultations"] == 2

    def test_exhaustion_survives_the_copy(self, tmp_path, capsys):
        """The budget is only real if the copy cannot buy one more comparison."""
        inc, cand, split, fingerprint = self._fixture(tmp_path, capsys)
        self._gate(capsys, inc, cand, split, fingerprint, cap=1)
        copy = tmp_path / "elsewhere.json"
        copy.write_text(split.read_text(encoding="utf-8"), encoding="utf-8")
        code, out = self._gate(capsys, inc, cand, copy, fingerprint, cap=1)
        assert (code, out["compared"], out["decision"]) == (EXIT_LOGIC, False, "REJECT")

    def test_a_redrawn_split_gets_its_own_budget(self, tmp_path, capsys):
        """The honest reset is a new seed, which is a new held-out group."""
        inc, cand, split, fingerprint = self._fixture(tmp_path, capsys)
        self._gate(capsys, inc, cand, split, fingerprint, cap=1)
        other = tmp_path / "redrawn.json"
        _run(capsys, "split", "--results", inc, "--seed", "s2", "--out", other)
        redrawn = json.loads(other.read_text(encoding="utf-8"))["fingerprint"]
        assert redrawn != fingerprint
        _, out = self._gate(capsys, inc, cand, other, redrawn, cap=1)
        assert out["sel_consultations"] == 1

    def test_the_ledger_flag_is_gone(self, tmp_path, capsys):
        with pytest.raises(SystemExit) as exc:
            _run(capsys, "gate", "--ledger", tmp_path / "elsewhere.json")
        assert exc.value.code == EXIT_CONFIG

    def test_two_held_out_groups_never_share_a_file(self, tmp_path):
        assert oa._ledger_path("aaaa") != oa._ledger_path("bbbb")

    def test_two_ratios_that_select_the_same_tasks_share_the_budget(self, tmp_path, capsys):
        """The fifth reset: rounding makes distinct ratios select one group.

        A fourth adversarial review (gpt-5.6-sol, 2026-07-26) reproduced this
        against the fingerprint key. Ten tasks at 0.40 and at 0.41 both round to
        four held out and pick the same four, but the fingerprint covers the raw
        ratio, so the identical group got two budgets.
        """
        inc = _write(tmp_path, "inc.json", {f"t{i}": i % 3 != 0 for i in range(10)})
        cand = _write(tmp_path, "cand.json", {f"t{i}": True for i in range(10)})
        for name, ratio in (("a.json", "0.40"), ("b.json", "0.41")):
            _run(capsys, "split", "--results", inc, "--seed", "s1",
                 "--sel-ratio", ratio, "--out", tmp_path / name)
        first, second = (json.loads((tmp_path / n).read_text(encoding="utf-8"))
                         for n in ("a.json", "b.json"))
        assert first["fingerprint"] != second["fingerprint"]
        assert sorted(first["sel"]) == sorted(second["sel"])
        _, one = self._gate(capsys, inc, cand, tmp_path / "a.json", first["fingerprint"])
        _, two = self._gate(capsys, inc, cand, tmp_path / "b.json", second["fingerprint"])
        assert (one["sel_consultations"], two["sel_consultations"]) == (1, 2)

    def test_rank_order_does_not_change_the_key(self, tmp_path):
        """Two seeds that hold out the same set are selecting on the same set."""
        assert oa._holdout_key({"sel": ["b", "a"]}) == oa._holdout_key(
            {"sel": ["a", "b"]}
        )

    def test_a_different_membership_changes_the_key(self, tmp_path):
        assert oa._holdout_key({"sel": ["a", "b"]}) != oa._holdout_key(
            {"sel": ["a", "c"]}
        )

    def test_the_root_defaults_to_the_state_directory(self, monkeypatch, tmp_path):
        """Unset override falls back to XDG rather than the working directory."""
        monkeypatch.delenv("EVAL_LEDGER_DIR", raising=False)
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
        assert oa._ledger_root() == tmp_path / "state" / "ai-agents-eval" / "ledgers"

    def test_the_root_falls_back_to_home_without_xdg(self, monkeypatch, tmp_path):
        monkeypatch.delenv("EVAL_LEDGER_DIR", raising=False)
        monkeypatch.delenv("XDG_STATE_HOME", raising=False)
        monkeypatch.setattr(oa.Path, "home", classmethod(lambda cls: tmp_path))
        assert oa._ledger_root() == tmp_path / ".local" / "state" / "ai-agents-eval" / "ledgers"


class TestOneGateAtATimePerSplit:
    """Atomic writes keep a file whole; they do not make a sequence a transaction.

    The same review found that two gates started together both read the same
    count, both compare, and both write count + 1, so a concurrent pair spends
    one consultation between them. The read, the comparison, and the write now
    happen under an exclusive lock file keyed by the same fingerprint.
    """

    def _fixture(self, tmp_path, capsys):
        inc = _write(tmp_path, "inc.json", {f"t{i}": i % 3 != 0 for i in range(12)})
        _run(capsys, "split", "--results", inc, "--seed", "s1",
             "--out", tmp_path / "split.json")
        cand = _write(tmp_path, "cand.json", {f"t{i}": True for i in range(12)})
        split = tmp_path / "split.json"
        record = json.loads(split.read_text(encoding="utf-8"))
        return inc, cand, split, record["fingerprint"]

    def test_a_held_lock_refuses_the_second_gate(self, tmp_path, capsys):
        inc, cand, split, fingerprint = self._fixture(tmp_path, capsys)
        lock = oa._ledger_root() / f"{_key_of(split)}.lock"
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_text("999", encoding="utf-8")
        code, out = _run(capsys, "gate", "--incumbent", inc, "--candidate", cand,
                         "--split", split, "--max-consultations", "3",
                         "--incumbent-fingerprint", fingerprint)
        assert code == EXIT_CONFIG and "another gate holds" in out["error"]

    def test_the_lock_is_released_when_the_gate_returns(self, tmp_path, capsys):
        inc, cand, split, fingerprint = self._fixture(tmp_path, capsys)
        _run(capsys, "gate", "--incumbent", inc, "--candidate", cand,
             "--split", split, "--max-consultations", "3",
             "--incumbent-fingerprint", fingerprint)
        assert not (oa._ledger_root() / f"{_key_of(split)}.lock").exists()

    def test_the_lock_is_released_when_the_gate_raises(self, tmp_path, capsys, monkeypatch):
        """A lock held past a crash would wedge every later run."""
        inc, cand, split, fingerprint = self._fixture(tmp_path, capsys)
        monkeypatch.setattr(oa, "_gate_decision", _raise_boom)
        with pytest.raises(RuntimeError):
            _run(capsys, "gate", "--incumbent", inc, "--candidate", cand,
                 "--split", split, "--max-consultations", "3",
                 "--incumbent-fingerprint", fingerprint)
        assert not (oa._ledger_root() / f"{_key_of(split)}.lock").exists()

    def test_a_drifted_split_takes_no_lock(self, tmp_path, capsys):
        """The refusal that reads no ledger must not serialize against one."""
        inc, cand, split, fingerprint = self._fixture(tmp_path, capsys)
        record = json.loads(split.read_text(encoding="utf-8"))
        record["fingerprint"] = "tampered"
        split.write_text(json.dumps(record), encoding="utf-8")
        lock = oa._ledger_root() / f"{_key_of(split)}.lock"
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_text("999", encoding="utf-8")
        code, out = _run(capsys, "gate", "--incumbent", inc, "--candidate", cand,
                         "--split", split, "--max-consultations", "3",
                         "--incumbent-fingerprint", fingerprint)
        assert (code, out["decision"]) == (EXIT_LOGIC, "REJECT")


class TestTheGateNeverNamesAHeldOutTask:
    """An error message that lists what is missing lists the held-out group.

    `score` and `mcnemar_exact` both report which task ids they could not find,
    which is the right message everywhere except here: the ids they would name
    are the held-out ones. A fourth adversarial review (gpt-5.6-sol,
    2026-07-26) found that a candidate results file with no keys at all printed
    the whole membership in a single error, before the ledger advanced, so the
    reveal was also free. The gate now answers one bit and charges for it.
    """

    def _fixture(self, tmp_path, capsys):
        inc = _write(tmp_path, "inc.json", {f"t{i}": i % 3 != 0 for i in range(12)})
        _run(capsys, "split", "--results", inc, "--seed", "s1",
             "--out", tmp_path / "split.json")
        split = tmp_path / "split.json"
        record = json.loads(split.read_text(encoding="utf-8"))
        return inc, split, record

    def _gate(self, capsys, inc, cand, split, record, cap=5):
        return _run(capsys, "gate", "--incumbent", inc, "--candidate", cand,
                    "--split", split, "--max-consultations", str(cap),
                    "--incumbent-fingerprint", record["fingerprint"])

    def test_an_empty_candidate_reveals_no_membership(self, tmp_path, capsys):
        """The reported attack: ask for everything by supplying nothing."""
        inc, split, record = self._fixture(tmp_path, capsys)
        empty = _write(tmp_path, "empty.json", {})
        code, out = self._gate(capsys, inc, empty, split, record)
        assert (code, out["compared"]) == (EXIT_LOGIC, False)
        assert not any(task_id in json.dumps(out) for task_id in record["sel"])

    def test_the_refusal_costs_a_consultation(self, tmp_path, capsys):
        inc, split, record = self._fixture(tmp_path, capsys)
        empty = _write(tmp_path, "empty.json", {})
        _, out = self._gate(capsys, inc, empty, split, record)
        assert out["sel_consultations"] == 1

    def test_probing_exhausts_the_budget(self, tmp_path, capsys):
        """A membership oracle has to be expensive, not just quiet."""
        inc, split, record = self._fixture(tmp_path, capsys)
        empty = _write(tmp_path, "empty.json", {})
        for _ in range(2):
            self._gate(capsys, inc, empty, split, record, cap=2)
        code, out = self._gate(capsys, inc, empty, split, record, cap=2)
        assert (code, out["compared"]) == (EXIT_LOGIC, False)
        assert "exhausted" in out["reason"]

    def test_a_missing_incumbent_result_refuses_the_same_way(self, tmp_path, capsys):
        """Both sides are read against the held-out group, so both must redact."""
        inc, split, record = self._fixture(tmp_path, capsys)
        cand = _write(tmp_path, "cand.json", {f"t{i}": True for i in range(12)})
        short = _write(tmp_path, "short-inc.json",
                       {k: v for k, v in json.loads(Path(inc).read_text(encoding="utf-8")).items()
                        if k != record["sel"][0]})
        code, out = self._gate(capsys, short, cand, split, record)
        assert (code, out["compared"]) == (EXIT_LOGIC, False)
        assert record["sel"][0] not in json.dumps(out)

    def test_a_non_bool_result_is_refused_before_the_split_is_consulted(self, tmp_path, capsys):
        """`score` would name the offending task, and that id can be held out.

        It never gets there: `_read_results` rejects a non-boolean at the file
        boundary, and the ids it echoes are the caller's own keys from the
        caller's own file, so nothing about the split is disclosed. The check
        lands before the reserve, so a malformed file of one's own costs no
        budget. `_covers_holdout` keeps its own type check anyway; a predicate
        that trusts its caller is one refactor away from leaking again.
        """
        inc, split, record = self._fixture(tmp_path, capsys)
        poisoned = {f"t{i}": True for i in range(12)}
        poisoned[record["sel"][0]] = "yes"
        cand = _write(tmp_path, "poison.json", poisoned)
        code, out = self._gate(capsys, inc, cand, split, record)
        assert code == EXIT_CONFIG and "non-boolean" in out["error"]
        assert not oa._ledger_path(oa._holdout_key(record)).exists()

    def test_full_coverage_still_compares(self, tmp_path, capsys):
        """The redaction must not swallow the ordinary path."""
        inc, split, record = self._fixture(tmp_path, capsys)
        cand = _write(tmp_path, "cand.json", {f"t{i}": True for i in range(12)})
        code, out = self._gate(capsys, inc, cand, split, record)
        assert (code, out["compared"]) == (EXIT_OK, True)

    def test_the_predicate_accepts_a_complete_boolean_mapping(self):
        assert oa._covers_holdout({"a": True, "b": False}, ["a", "b"])

    def test_the_predicate_rejects_a_missing_task(self):
        assert not oa._covers_holdout({"a": True}, ["a", "b"])

    def test_the_predicate_rejects_a_non_boolean(self):
        assert not oa._covers_holdout({"a": True, "b": 1}, ["a", "b"])

    def test_the_predicate_accepts_an_empty_requirement(self):
        """No held-out ids means nothing to cover; the split guard rejects that
        case earlier, so this only pins the predicate as total."""
        assert oa._covers_holdout({}, [])


class TestTheIncumbentFingerprintIsRequired:
    """An optional integrity check is an integrity check nobody runs.

    `--incumbent-fingerprint` defaulted to None, and the guard compares only
    when both sides are present, so omitting the flag silently skipped the
    one check that catches a stale baseline: redraw the split, gate against
    an incumbent scored on the old one, and the comparison is between two
    different eval sets. `score` now reports the fingerprint so supplying it
    costs the caller nothing.
    """

    def _fixture(self, tmp_path, capsys):
        inc = _write(tmp_path, "inc.json", {f"t{i}": i % 3 != 0 for i in range(12)})
        _run(capsys, "split", "--results", inc, "--seed", "s1",
             "--out", tmp_path / "split.json")
        cand = _write(tmp_path, "cand.json", {f"t{i}": True for i in range(12)})
        return inc, cand, tmp_path / "split.json"

    def test_a_missing_incumbent_fingerprint_is_a_usage_error(self, tmp_path, capsys):
        inc, cand, split = self._fixture(tmp_path, capsys)
        with pytest.raises(SystemExit) as exc:
            _run(capsys, "gate", "--incumbent", inc, "--candidate", cand,
                 "--split", split, "--max-consultations", "3")
        assert exc.value.code == EXIT_CONFIG

    def test_score_reports_the_fingerprint_the_gate_will_demand(self, tmp_path, capsys):
        inc, _cand, split = self._fixture(tmp_path, capsys)
        _, out = _run(capsys, "score", "--results", inc, "--split", split)
        recorded = json.loads(split.read_text(encoding="utf-8"))["fingerprint"]
        assert out["fingerprint"] == recorded

    def test_the_fingerprint_score_reports_is_the_one_the_gate_accepts(self, tmp_path, capsys):
        """End to end: the value `score` prints must satisfy `gate`."""
        inc, cand, split = self._fixture(tmp_path, capsys)
        _, scored = _run(capsys, "score", "--results", inc, "--split", split)
        code, out = _run(capsys, "gate", "--incumbent", inc, "--candidate", cand,
                         "--split", split, "--max-consultations", "3",
                         "--incumbent-fingerprint", scored["fingerprint"])
        assert code == EXIT_OK and out["compared"] is True


class TestTheGateNeverPublishesTheHoldoutKey:
    """The key digests the held-out membership, so printing it is printing them.

    A fifth adversarial review (gpt-5.6-sol, 2026-07-26) found the digest in
    three error paths. It is an unsalted sha256 over a set the caller can
    enumerate: the universe is the caller's own results file, `opt` and the
    two group sizes are published, so a caller hashes every subset of the
    complement of the right size and matches. Whenever a test group exists the
    complement is not the held-out group, and that reversal is the only way to
    tell the two apart.
    """

    def _fixture(self, tmp_path, capsys):
        inc = _write(tmp_path, "inc.json", {f"t{i}": i % 3 != 0 for i in range(12)})
        split = tmp_path / "split.json"
        _run(capsys, "split", "--results", inc, "--seed", "s", "--out", split)
        return inc, split, json.loads(split.read_text())

    def _gate(self, capsys, inc, cand, split, record, cap="2"):
        return _run(
            capsys, "gate", "--incumbent", inc, "--candidate", cand,
            "--split", split, "--max-consultations", cap,
            "--incumbent-fingerprint", record["fingerprint"],
        )

    def test_lock_contention_does_not_publish_the_key(self, tmp_path, capsys):
        inc, split, record = self._fixture(tmp_path, capsys)
        key = oa._holdout_key(record)
        lock = oa._ledger_root() / f"{key}.lock"
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.touch()
        code, out = self._gate(capsys, inc, inc, split, record)
        assert code == EXIT_CONFIG and "another gate" in out["error"]
        assert key not in json.dumps(out)

    def test_lock_contention_still_says_where_to_look(self, tmp_path, capsys):
        """Redaction that hides the directory turns a stale lock into a puzzle."""
        inc, split, record = self._fixture(tmp_path, capsys)
        lock = oa._ledger_root() / f"{oa._holdout_key(record)}.lock"
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.touch()
        _, out = self._gate(capsys, inc, inc, split, record)
        assert str(oa._ledger_root()) in out["error"]

    def test_a_ledger_under_another_group_does_not_publish_either_key(self, tmp_path, capsys):
        inc, split, record = self._fixture(tmp_path, capsys)
        key = oa._holdout_key(record)
        ledger = oa._ledger_path(key)
        ledger.parent.mkdir(parents=True, exist_ok=True)
        ledger.write_text(
            json.dumps({"consultations": 0, "holdout": "f" * 64, "max_consultations": 2})
        )
        code, out = self._gate(capsys, inc, inc, split, record)
        assert (code, out["decision"]) == (EXIT_LOGIC, "REJECT")
        assert key not in json.dumps(out) and "f" * 64 not in json.dumps(out)

    def test_a_cap_mismatch_does_not_publish_the_key(self, tmp_path, capsys):
        inc, split, record = self._fixture(tmp_path, capsys)
        key = oa._holdout_key(record)
        self._gate(capsys, inc, inc, split, record, cap="2")
        code, out = self._gate(capsys, inc, inc, split, record, cap="5")
        assert (code, out["decision"]) == (EXIT_LOGIC, "REJECT")
        assert "cap of 2" in out["reason"] and key not in json.dumps(out)

    def test_a_malformed_ledger_does_not_publish_the_key(self, tmp_path, capsys):
        inc, split, record = self._fixture(tmp_path, capsys)
        key = oa._holdout_key(record)
        ledger = oa._ledger_path(key)
        ledger.parent.mkdir(parents=True, exist_ok=True)
        ledger.write_text(json.dumps({"consultations": -1, "holdout": key, "max_consultations": 2}))
        code, out = self._gate(capsys, inc, inc, split, record)
        assert code == EXIT_CONFIG
        assert key not in json.dumps(out)

    def test_the_decision_block_does_not_publish_the_key(self, tmp_path, capsys):
        """The ordinary success path is the one a caller reads every time."""
        inc, split, record = self._fixture(tmp_path, capsys)
        _, out = self._gate(capsys, inc, inc, split, record)
        assert oa._holdout_key(record) not in json.dumps(out)

    def test_the_key_separates_ids_that_contain_a_null_byte(self):
        """Joining on NUL is not injective when an id may contain one."""
        assert oa._holdout_key({"sel": ["a", "b\x00c"]}) != oa._holdout_key(
            {"sel": ["a\x00b", "c"]}
        )

    def test_the_key_still_ignores_the_order_it_is_given(self):
        assert oa._holdout_key({"sel": ["b", "a"]}) == oa._holdout_key({"sel": ["a", "b"]})

    def test_the_key_still_separates_different_members(self):
        assert oa._holdout_key({"sel": ["a", "b"]}) != oa._holdout_key({"sel": ["a", "c"]})


class TestAtomicWriteDoesNotDisguiseNonIOFailures:
    """A ConfigError means the disk refused. Anything else must keep its type.

    The cleanup arm catches BaseException so an interrupt still removes the
    temp file. Converting everything it caught into ConfigError would tell a
    caller the write failed when what actually happened was Ctrl-C, and would
    swallow an interrupt the operator meant to be immediate.
    """

    def test_an_interrupt_propagates_unchanged(self, tmp_path, monkeypatch):
        target = tmp_path / "artifact.md"
        target.write_text("before", encoding="utf-8")

        def _interrupt(src, dst):
            raise KeyboardInterrupt

        monkeypatch.setattr(oa.os, "replace", _interrupt)
        with pytest.raises(KeyboardInterrupt):
            oa._write_atomic(target, "after")
        assert target.read_text(encoding="utf-8") == "before"
        assert list(tmp_path.iterdir()) == [target]

    def test_an_os_error_becomes_a_config_error(self, tmp_path, monkeypatch):
        target = tmp_path / "artifact.md"
        target.write_text("before", encoding="utf-8")

        def _refuse(src, dst):
            raise OSError(28, "No space left on device")

        monkeypatch.setattr(oa.os, "replace", _refuse)
        with pytest.raises(oa.ConfigError, match="could not write"):
            oa._write_atomic(target, "after")
        assert list(tmp_path.iterdir()) == [target]

    def test_a_write_that_works_replaces_the_file(self, tmp_path):
        target = tmp_path / "artifact.md"
        target.write_text("before", encoding="utf-8")
        oa._write_atomic(target, "after")
        assert target.read_text(encoding="utf-8") == "after"
        assert list(tmp_path.iterdir()) == [target]


class TestASplitFileMustHoldGroupsOfTaskIds:
    """The gate indexes into every group, so a wrong shape must fail at the file.

    Added by the incoming review-thread commit; these cover its branch. A
    group holding numbers, or holding a bare string instead of a list, would
    otherwise surface as a TypeError deep in the comparison, long after the
    file that caused it went out of scope.
    """

    def _split_with(self, tmp_path, groups):
        record = {"opt": ["a"], "sel": ["b"], "test": [],
                  "seed": "s", "sel_ratio": 0.4, "test_ratio": 0.0,
                  "fingerprint": "x" * 64}
        record.update(groups)
        path = tmp_path / "bad.json"
        path.write_text(json.dumps(record), encoding="utf-8")
        return path

    @pytest.mark.parametrize("groups", [
        {"opt": "a"},
        {"sel": [1, 2]},
        {"test": [None]},
        {"opt": {"a": True}},
    ])
    def test_a_group_that_is_not_a_list_of_strings_is_refused(
        self, tmp_path, capsys, groups
    ):
        split = self._split_with(tmp_path, groups)
        inc = _write(tmp_path, "inc.json", {"a": True, "b": True})
        code, out = _run(capsys, "gate", "--incumbent", inc, "--candidate", inc,
                         "--split", split, "--max-consultations", "2",
                         "--incumbent-fingerprint", "x" * 64)
        assert code == EXIT_CONFIG
        assert "must be a list of strings" in out["error"]

    def test_a_well_formed_split_passes_the_shape_check(self, tmp_path, capsys):
        """The negative cases must not be passing for an unrelated reason."""
        split = self._split_with(tmp_path, {})
        assert "must be a list of strings" not in json.dumps(
            _run(capsys, "gate", "--incumbent",
                 _write(tmp_path, "i.json", {"a": True, "b": True}),
                 "--candidate", _write(tmp_path, "c.json", {"a": True, "b": True}),
                 "--split", split, "--max-consultations", "2",
                 "--incumbent-fingerprint", "x" * 64)[1]
        )


class TestNoLedgerFailureLeaksTheDigest:
    """The explicit messages were redacted; the generic ones still carried it.

    A sixth adversarial review (gpt-5.6-sol, 2026-07-26) found that redacting
    the three hand-written errors left every other way of failing on a ledger
    path intact: `_read_json` interpolates the file it could not parse, the
    atomic write interpolates the file it could not replace, and `os.open`
    raises with the lock's name for any errno but EEXIST. All three names end
    in the digest. The fix is one scrub at the exception seam rather than
    three sanitized wrappers, because a wrapper covers the paths someone
    remembered and a seam covers the ones added later.
    """

    def _fixture(self, tmp_path, capsys):
        inc = _write(tmp_path, "inc.json", {f"t{i}": i % 3 != 0 for i in range(12)})
        split = tmp_path / "split.json"
        _run(capsys, "split", "--results", inc, "--seed", "s", "--out", split)
        return inc, split, json.loads(split.read_text())

    def _gate(self, capsys, inc, split, record):
        return _run(
            capsys, "gate", "--incumbent", inc, "--candidate", inc,
            "--split", split, "--max-consultations", "2",
            "--incumbent-fingerprint", record["fingerprint"],
        )

    def test_an_unparseable_ledger_does_not_leak_the_digest(self, tmp_path, capsys):
        inc, split, record = self._fixture(tmp_path, capsys)
        key = oa._holdout_key(record)
        ledger = oa._ledger_path(key)
        ledger.parent.mkdir(parents=True, exist_ok=True)
        ledger.write_text("{not json")
        code, out = self._gate(capsys, inc, split, record)
        assert code == EXIT_CONFIG and key not in json.dumps(out)

    def test_an_unparseable_ledger_still_says_it_could_not_be_read(self, tmp_path, capsys):
        """Scrubbing that erases the diagnosis is worse than the leak."""
        inc, split, record = self._fixture(tmp_path, capsys)
        ledger = oa._ledger_path(oa._holdout_key(record))
        ledger.parent.mkdir(parents=True, exist_ok=True)
        ledger.write_text("{not json")
        _, out = self._gate(capsys, inc, split, record)
        assert "not valid JSON" in out["error"] and "ledger" in out["error"]

    def test_an_unwritable_ledger_does_not_leak_the_digest(self, tmp_path, capsys, monkeypatch):
        inc, split, record = self._fixture(tmp_path, capsys)
        key = oa._holdout_key(record)

        def _deny(path, _text):
            raise OSError(28, "No space left on device", str(path))

        monkeypatch.setattr(oa, "_write_atomic", _deny)
        code, out = self._gate(capsys, inc, split, record)
        assert code == EXIT_CONFIG and key not in json.dumps(out)

    def test_a_lock_cleanup_failure_does_not_leak(self, tmp_path, capsys, monkeypatch):
        """The unlink in the finally block names the lock, and the lock is the digest.

        Before round 7 this escaped as an uncaught PermissionError, since main
        catches ConfigError and not OSError. Round 9 then stopped it reaching
        main at all, because release runs after the decision is emitted and a
        second document on stdout breaks every reader of the first. So the
        assertions here are on the leak, which is the invariant, and both
        streams are checked; the exit code and the stream split belong to
        TestCleanupFailureDoesNotRewriteTheDecision.
        """
        inc, split, record = self._fixture(tmp_path, capsys)
        key = oa._holdout_key(record)
        real_unlink = Path.unlink

        def _boom(self, missing_ok=False):
            if self.suffix == ".lock":
                raise OSError(13, "Permission denied", str(self))
            return real_unlink(self, missing_ok=missing_ok)

        monkeypatch.setattr(Path, "unlink", _boom)
        code = oa.main([
            "gate", "--incumbent", str(inc), "--candidate", str(inc),
            "--split", str(split), "--max-consultations", "2",
            "--incumbent-fingerprint", record["fingerprint"],
        ])
        captured = capsys.readouterr()
        text = captured.out + captured.err
        assert code != EXIT_CONFIG
        assert key not in text
        for task in record["sel"]:
            assert task not in text

    def test_a_lock_that_fails_for_any_other_reason_does_not_leak(
        self, tmp_path, capsys, monkeypatch
    ):
        """os.open raises for more than EEXIST, and the name is the digest."""
        inc, split, record = self._fixture(tmp_path, capsys)
        key = oa._holdout_key(record)

        def _deny(path, *args, **kwargs):
            raise PermissionError(13, "Permission denied", str(path))

        monkeypatch.setattr(oa.os, "open", _deny)
        code, out = self._gate(capsys, inc, split, record)
        assert code == EXIT_CONFIG and key not in json.dumps(out)

    def test_the_scrub_leaves_messages_without_the_digest_alone(self):
        with pytest.raises(oa.ConfigError, match="plain trouble"):
            with oa._digest_scrubbed("a" * 64):
                raise oa.ConfigError("plain trouble")

    def test_the_scrub_replaces_the_digest_wherever_it_appears(self):
        key = "a" * 64
        with pytest.raises(oa.ConfigError) as caught:
            with oa._digest_scrubbed(key):
                raise oa.ConfigError(f"could not read /x/{key}.ledger")
        assert key not in str(caught.value) and "/x/" in str(caught.value)

    def test_the_scrub_passes_a_clean_block_through(self):
        with oa._digest_scrubbed("a" * 64):
            pass


class TestLedgerFailuresKeepTheJsonErrorContract:
    """A scrub that re-raises a raw OSError breaks the promise it protects.

    An eighth review (Copilot, PR #3458) found that `_digest_scrubbed` re-raised
    `OSError` untouched whenever the message did not contain the digest, and
    `main` catches `ConfigError`, `AdapterError`, and `ValueError` but not
    `OSError`. So the failures that name a path stayed inside the contract while
    the failures that do not, an `os.write` that runs out of space or an
    `os.close` that hits EIO, escaped as an uncaught traceback.

    That is the same defect the scrub was added to fix, one layer down: the
    handled paths are the ones somebody enumerated. The seam now converts every
    `OSError` it sees, and redacts the digest only when the message carries it,
    so the two concerns stay separate.
    """

    def test_an_oserror_without_the_digest_still_emits_json(self, capsys):
        with pytest.raises(oa.ConfigError) as caught:
            with oa._digest_scrubbed("a" * 64):
                raise OSError(28, "No space left on device")
        assert "No space left on device" in str(caught.value)

    def test_the_json_contract_holds_end_to_end_for_a_pathless_oserror(
        self, tmp_path, capsys, monkeypatch
    ):
        inc = _write(tmp_path, "inc.json", {f"t{i}": i % 3 != 0 for i in range(12)})
        split = tmp_path / "split.json"
        _run(capsys, "split", "--results", inc, "--seed", "s", "--out", split)
        record = json.loads(split.read_text())

        def _boom(_handle, _payload):
            raise OSError(28, "No space left on device")

        monkeypatch.setattr(oa.os, "write", _boom)
        code = oa.main([
            "gate", "--incumbent", str(inc), "--candidate", str(inc),
            "--split", str(split), "--max-consultations", "2",
            "--incumbent-fingerprint", record["fingerprint"],
        ])
        out = capsys.readouterr().out
        assert code == oa.EXIT_CONFIG
        payload = json.loads(out)
        assert payload["type"] == "ConfigError"
        assert "No space left on device" in payload["error"]

    def test_an_oserror_carrying_the_digest_is_still_redacted(self, capsys):
        key = "b" * 64
        with pytest.raises(oa.ConfigError) as caught:
            with oa._digest_scrubbed(key):
                raise OSError(13, f"Permission denied: /state/{key}.lock")
        assert key not in str(caught.value)
        assert "<held-out group>" in str(caught.value)

    def test_a_config_error_without_the_digest_is_reraised_as_itself(self, capsys):
        original = oa.ConfigError("the split file is not JSON")
        with pytest.raises(oa.ConfigError) as caught:
            with oa._digest_scrubbed("c" * 64):
                raise original
        assert caught.value is original

    def test_a_ledger_mismatch_passes_through_the_seam_untouched(self, capsys):
        with pytest.raises(oa.LedgerMismatchError):
            with oa._digest_scrubbed("c" * 64):
                raise oa.LedgerMismatchError("the cap moved")

    def test_a_non_oserror_passes_through_untouched(self, capsys):
        with pytest.raises(KeyboardInterrupt):
            with oa._digest_scrubbed("d" * 64):
                raise KeyboardInterrupt


class TestTheSeamLeaksNothingThroughTheCauseChain:
    """A scrubbed message with an unscrubbed `__cause__` is not scrubbed.

    A ninth review (gemini-3.1-pro-preview, 2026-07-26) found the redaction
    handing the digest straight back: `raise ConfigError(scrubbed) from exc`
    sets `__cause__` to the original, and a printed traceback walks the chain.
    The contention branch was worse, because its message withholds the lock
    name on purpose and then attached the `FileExistsError` that spells it out.

    The chain is severed exactly where it carries the digest. Where the message
    never had it, `from exc` stays, because the original raise site is worth
    keeping and there is nothing there to leak.
    """

    def _traceback(self, exc):
        return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))

    def test_a_scrubbed_oserror_leaks_nothing_through_the_chain(self):
        key = "a" * 64
        with pytest.raises(oa.ConfigError) as caught:
            with oa._digest_scrubbed(key):
                raise OSError(2, "No such file", f"/state/{key}.lock")
        assert key not in self._traceback(caught.value)

    def test_lock_contention_leaks_nothing_through_the_chain(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EVAL_LEDGER_DIR", str(tmp_path / "ledgers"))
        key = "b" * 64
        root = oa._ledger_root()
        root.mkdir(parents=True, exist_ok=True)
        (root / f"{key}.lock").write_text("999")
        with pytest.raises(oa.ConfigError) as caught:
            with oa._ledger_held(key):
                pass
        assert key not in self._traceback(caught.value)

    def test_a_pathless_oserror_keeps_its_cause_for_debugging(self):
        with pytest.raises(oa.ConfigError) as caught:
            with oa._digest_scrubbed("c" * 64):
                raise OSError(28, "No space left on device")
        assert isinstance(caught.value.__cause__, OSError)


class TestCleanupFailureDoesNotRewriteTheDecision:
    """The gate had already answered; removing the lock is bookkeeping.

    The same ninth review found that an unlink failure in the `finally` reached
    `main` after `_emit` had printed the decision, so stdout carried two JSON
    documents and a successful comparison returned the config-failure exit
    code. The module docstring promises a caller can read a field instead of
    guessing from the exit code, and two documents break every reader of it.

    Swallowing it silently would hide a lock that now blocks the next run, so
    the failure goes to stderr and the decision keeps stdout to itself.
    """

    def _fixture(self, tmp_path, capsys):
        inc = _write(tmp_path, "inc.json", {f"t{i}": i % 3 != 0 for i in range(12)})
        split = tmp_path / "split.json"
        _run(capsys, "split", "--results", inc, "--seed", "s", "--out", split)
        return inc, split, json.loads(split.read_text())

    def _gate(self, inc, split, record):
        return oa.main([
            "gate", "--incumbent", str(inc), "--candidate", str(inc),
            "--split", str(split), "--max-consultations", "2",
            "--incumbent-fingerprint", record["fingerprint"],
        ])

    def _break_unlink(self, monkeypatch):
        original = Path.unlink

        def refuse(self, missing_ok=False):
            if str(self).endswith(".lock"):
                raise OSError(13, "Permission denied", str(self))
            return original(self, missing_ok=missing_ok)

        monkeypatch.setattr(Path, "unlink", refuse)

    def test_stdout_still_holds_exactly_one_document(self, tmp_path, capsys, monkeypatch):
        inc, split, record = self._fixture(tmp_path, capsys)
        self._break_unlink(monkeypatch)
        self._gate(inc, split, record)
        payload = json.loads(capsys.readouterr().out)
        assert payload["decision"] in {"ACCEPT", "REJECT"}

    def test_the_decision_keeps_its_exit_code(self, tmp_path, capsys, monkeypatch):
        inc, split, record = self._fixture(tmp_path, capsys)
        self._break_unlink(monkeypatch)
        code = self._gate(inc, split, record)
        assert code != oa.EXIT_CONFIG

    def test_the_stale_lock_is_reported_on_stderr(self, tmp_path, capsys, monkeypatch):
        inc, split, record = self._fixture(tmp_path, capsys)
        self._break_unlink(monkeypatch)
        self._gate(inc, split, record)
        assert "Permission denied" in capsys.readouterr().err

    def test_the_warning_withholds_the_digest(self, tmp_path, capsys, monkeypatch):
        inc, split, record = self._fixture(tmp_path, capsys)
        key = oa._holdout_key(record)
        self._break_unlink(monkeypatch)
        self._gate(inc, split, record)
        captured = capsys.readouterr()
        assert key not in captured.err
        assert key not in captured.out

    def test_a_clean_release_says_nothing(self, tmp_path, capsys):
        inc, split, record = self._fixture(tmp_path, capsys)
        self._gate(inc, split, record)
        assert capsys.readouterr().err == ""


class TestTheLedgerRootIsNotOutsideTheSeam:
    """One line in `_ledger_held` sat outside the scrub, and it was the first one.

    A tenth review found `lock.parent.mkdir(...)` above the `with` rather than
    inside it. That has two costs and only the second one needs a contrived
    setup.

    The first is the round-8 contract defect, unfixed at this line. `mkdir` on a
    ledger root the process cannot create raises `PermissionError`, `main`
    catches `(ConfigError, AdapterError, ValueError)` and not `OSError`, so the
    caller piping stdout through a JSON reader gets a traceback instead of the
    error document the module docstring promises. A read-only home or a
    sandboxed runner reaches this with no help from anyone.

    The second is the leak. `$EVAL_LEDGER_DIR` can name a directory that
    contains the digest, and both the `mkdir` traceback and the release warning
    render that directory. A caller who set that variable already knows the
    digest, so this leaks to someone holding the secret. It is fixed anyway,
    because the standing rule from nine rounds is that a path by which the
    withheld thing is readable is not withholding it, and because the release
    warning was justified in review by the claim that a directory carries no
    digest. That justification was wrong, which is reason enough.
    """

    def _fixture(self, tmp_path, capsys):
        inc = _write(tmp_path, "inc.json", {f"t{i}": i % 3 != 0 for i in range(12)})
        split = tmp_path / "split.json"
        _run(capsys, "split", "--results", inc, "--seed", "s", "--out", split)
        return inc, split, json.loads(split.read_text())

    def _gate(self, inc, split, record):
        return oa.main([
            "gate", "--incumbent", str(inc), "--candidate", str(inc),
            "--split", str(split), "--max-consultations", "2",
            "--incumbent-fingerprint", record["fingerprint"],
        ])

    def _break(self, monkeypatch, method):
        original = getattr(Path, method)

        def refuse(self, *args, **kwargs):
            if method == "mkdir" or str(self).endswith(".lock"):
                raise PermissionError(13, "Permission denied", str(self))
            return original(self, *args, **kwargs)

        monkeypatch.setattr(Path, method, refuse)

    def test_an_unwritable_ledger_root_keeps_the_json_contract(
        self, tmp_path, capsys, monkeypatch
    ):
        """No digest anywhere. The contract still has to hold."""
        monkeypatch.setenv("EVAL_LEDGER_DIR", str(tmp_path / "plain"))
        inc, split, record = self._fixture(tmp_path, capsys)
        self._break(monkeypatch, "mkdir")
        code = self._gate(inc, split, record)
        payload = json.loads(capsys.readouterr().out)
        assert code == EXIT_CONFIG
        assert payload["type"] == "ConfigError"

    def test_a_digest_bearing_root_is_scrubbed_from_the_mkdir_failure(
        self, tmp_path, capsys, monkeypatch
    ):
        inc, split, record = self._fixture(tmp_path, capsys)
        key = oa._holdout_key(record)
        monkeypatch.setenv("EVAL_LEDGER_DIR", str(tmp_path / f"root-{key}"))
        self._break(monkeypatch, "mkdir")
        self._gate(inc, split, record)
        captured = capsys.readouterr()
        assert key not in captured.out + captured.err

    def test_a_digest_bearing_root_is_scrubbed_from_the_release_warning(
        self, tmp_path, capsys, monkeypatch
    ):
        inc, split, record = self._fixture(tmp_path, capsys)
        key = oa._holdout_key(record)
        monkeypatch.setenv("EVAL_LEDGER_DIR", str(tmp_path / f"root-{key}"))
        self._break(monkeypatch, "unlink")
        self._gate(inc, split, record)
        captured = capsys.readouterr()
        assert key not in captured.out + captured.err
        assert "<held-out group>" in captured.err

    def test_a_plain_root_is_still_named_so_the_lock_can_be_cleared(
        self, tmp_path, capsys, monkeypatch
    ):
        """Redaction that redacts everything is not redaction, it is silence."""
        root = tmp_path / "plain"
        monkeypatch.setenv("EVAL_LEDGER_DIR", str(root))
        inc, split, record = self._fixture(tmp_path, capsys)
        self._break(monkeypatch, "unlink")
        self._gate(inc, split, record)
        assert str(root) in capsys.readouterr().err


class TestOneDefinitionOfHowWeRedact:
    """The release warning was a second, hand-written redaction site, and it was wrong.

    Two rounds in a row found a redaction defect at a site that had been
    written by hand rather than routed through the seam. The rule the code now
    states once is the rule every site gets.
    """

    def test_a_digest_in_the_text_is_replaced(self):
        assert oa._scrub("under /x/abc123/y", "abc123") == "under /x/<held-out group>/y"

    def test_text_without_the_digest_is_returned_unchanged(self):
        assert oa._scrub("under /x/y", "abc123") == "under /x/y"

    def test_every_occurrence_is_replaced_not_only_the_first(self):
        out = oa._scrub("abc123 and abc123", "abc123")
        assert "abc123" not in out
        assert out.count("<held-out group>") == 2

    def test_empty_text_is_not_a_special_case(self):
        assert oa._scrub("", "abc123") == ""


class TestTheRootResolvesInsideTheContract:
    """An eleventh review found the seam's first line had moved, not vanished.

    Round 10 pulled `lock.parent.mkdir(...)` inside `_digest_scrubbed` and left
    `_ledger_root()` on the line above it. `Path.home()` raises `RuntimeError`
    when `$HOME` is unset and the uid has no passwd entry, which is an ordinary
    container running as a numeric user, and it happens on the DEFAULT
    configuration: `_ledger_root` consults home only when neither
    `$EVAL_LEDGER_DIR` nor `$XDG_STATE_HOME` is set.

    `main` catches `(ConfigError, AdapterError, ValueError)`, so that escaped as
    a traceback where the module docstring promises a JSON error document. The
    conversion belongs in `_ledger_root` rather than at either call site,
    because the failure is there and both callers need it.
    """

    @staticmethod
    def _no_home(monkeypatch):
        monkeypatch.delenv("EVAL_LEDGER_DIR", raising=False)
        monkeypatch.delenv("XDG_STATE_HOME", raising=False)
        monkeypatch.setattr(
            Path, "home",
            staticmethod(lambda: (_ for _ in ()).throw(RuntimeError("no home"))),
        )

    def test_an_unresolvable_home_is_a_config_error_not_a_runtime_error(self, monkeypatch):
        self._no_home(monkeypatch)
        with pytest.raises(oa.ConfigError) as caught:
            oa._ledger_root()
        assert "EVAL_LEDGER_DIR" in str(caught.value)

    def test_the_gate_still_emits_one_json_document(self, tmp_path, capsys, monkeypatch):
        inc = _write(tmp_path, "inc.json", {f"t{i}": i % 3 != 0 for i in range(12)})
        split = tmp_path / "split.json"
        _run(capsys, "split", "--results", inc, "--seed", "s", "--out", split)
        record = json.loads(split.read_text())
        self._no_home(monkeypatch)
        code = oa.main([
            "gate", "--incumbent", str(inc), "--candidate", str(inc),
            "--split", str(split), "--max-consultations", "2",
            "--incumbent-fingerprint", record["fingerprint"],
        ])
        assert code == EXIT_CONFIG
        assert json.loads(capsys.readouterr().out)["type"] == "ConfigError"

    def test_an_explicit_root_never_consults_home(self, tmp_path, monkeypatch):
        self._no_home(monkeypatch)
        monkeypatch.setenv("EVAL_LEDGER_DIR", str(tmp_path / "explicit"))
        assert oa._ledger_root() == tmp_path / "explicit"

    def test_xdg_state_home_also_never_consults_home(self, tmp_path, monkeypatch):
        self._no_home(monkeypatch)
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg"))
        assert oa._ledger_root().is_relative_to(tmp_path / "xdg")


class TestTheLockDescriptorIsAlwaysReleased:
    """The write and the close were in one try, so a failed write skipped the close.

    `os.write` on a full disk jumped straight to the `finally`, which unlinks
    the lock and never closes the descriptor. A one-shot CLI exits and the
    kernel reclaims it, so the practical cost is small; the reason to fix it is
    that `main` is importable and the module is used from tests, where the leak
    accumulates across a session.
    """

    def _fd_state(self, monkeypatch, tmp_path, fail_write):
        monkeypatch.setenv("EVAL_LEDGER_DIR", str(tmp_path / "root"))
        seen = {}
        real_open = oa.os.open

        def spy(*args, **kwargs):
            seen["fd"] = real_open(*args, **kwargs)
            return seen["fd"]

        monkeypatch.setattr(oa.os, "open", spy)
        if fail_write:
            monkeypatch.setattr(
                oa.os, "write",
                lambda *a, **k: (_ for _ in ()).throw(OSError(28, "No space left")),
            )
        return seen

    @staticmethod
    def _is_open(fd):
        try:
            os.fstat(fd)
        except OSError:
            return False
        return True

    def test_a_failed_write_still_closes_the_descriptor(self, tmp_path, monkeypatch):
        seen = self._fd_state(monkeypatch, tmp_path, fail_write=True)
        with pytest.raises(oa.ConfigError):
            with oa._ledger_held("d" * 64):
                pass
        assert self._is_open(seen["fd"]) is False

    def test_the_normal_path_closes_it_exactly_once(self, tmp_path, monkeypatch):
        seen = self._fd_state(monkeypatch, tmp_path, fail_write=False)
        with oa._ledger_held("e" * 64):
            pass
        assert self._is_open(seen["fd"]) is False


class TestRedactionIsNotCaseSensitive:
    """A hex digest has an uppercase spelling, and a path can carry either.

    Only reachable when the caller put the digest in `$EVAL_LEDGER_DIR`, which
    means the caller already knows it, so this is not a confidentiality bypass.
    It is fixed because the stated property is that the key is never printed,
    and hex is the one alphabet where case-insensitive matching carries no
    folding surprises.
    """

    def test_an_uppercase_digest_is_replaced(self):
        key = "f" * 60 + "abcd"
        assert key.upper() not in oa._scrub(f"/root-{key.upper()}/x", key)

    def test_a_mixed_case_digest_is_replaced(self):
        key = "abcdef" + "0" * 58
        mixed = "AbCdEf" + "0" * 58
        assert mixed not in oa._scrub(f"/root-{mixed}/x", key)

    def test_the_lowercase_case_still_works(self):
        key = "a" * 64
        assert oa._scrub(f"/root-{key}/x", key) == "/root-<held-out group>/x"

    def test_unrelated_text_is_untouched(self):
        assert oa._scrub("/root/ABCDEF/x", "a" * 64) == "/root/ABCDEF/x"


class TestTheGuardIsNotASecondDefinitionOfRedaction:
    """A twelfth review found the round-11 fix applied to only half the pair.

    Round 11 made `_scrub` case-insensitive and left the call site that decides
    whether to call it reading `if holdout_key in text`, which is case
    sensitive. So an uppercase digest failed the guard, skipped the scrub the
    round-11 fix had just corrected, and printed whole.

    That is the recurring shape once more, in its twelfth spelling: two places
    answer "does this text carry the key" and only one of them was fixed. The
    round-11 tests asserted on `_scrub` directly, which is why four passing
    tests said the case bug was closed while the CLI still printed the digest.
    Testing the function that changed is not testing the property that matters.

    Fixed by deleting the second definition rather than teaching it to fold
    case: `_scrub` returning a different string is the answer to both questions,
    so there is nothing left to keep in step.
    """

    def _fixture(self, tmp_path, capsys):
        inc = _write(tmp_path, "inc.json", {f"t{i}": i % 3 != 0 for i in range(12)})
        split = tmp_path / "split.json"
        _run(capsys, "split", "--results", inc, "--seed", "s", "--out", split)
        return inc, split, json.loads(split.read_text())

    def _gate_denied(self, monkeypatch, tmp_path, capsys, spell):
        inc, split, record = self._fixture(tmp_path, capsys)
        key = oa._holdout_key(record)
        monkeypatch.setenv(oa._LEDGER_DIR_ENV, str(tmp_path / f"denied-{spell(key)}"))
        monkeypatch.setattr(
            Path,
            "mkdir",
            lambda self, *a, **k: (_ for _ in ()).throw(
                PermissionError(13, "Permission denied", str(self))
            ),
        )
        code = oa.main([
            "gate", "--incumbent", str(inc), "--candidate", str(inc),
            "--split", str(split), "--max-consultations", "2",
            "--incumbent-fingerprint", record["fingerprint"],
        ])
        return key, code, capsys.readouterr()

    def test_an_uppercase_digest_does_not_reach_stdout(self, tmp_path, monkeypatch, capsys):
        key, code, out = self._gate_denied(monkeypatch, tmp_path, capsys, str.upper)
        assert code == oa.EXIT_CONFIG
        assert key.upper() not in out.out
        assert key.upper() not in out.err

    def test_an_uppercase_digest_still_leaves_a_readable_error(
        self, tmp_path, monkeypatch, capsys
    ):
        _key, _code, out = self._gate_denied(monkeypatch, tmp_path, capsys, str.upper)
        payload = json.loads(out.out)
        assert payload["type"] == "ConfigError"
        assert oa._HELD_OUT_PLACEHOLDER in payload["error"]

    def test_a_lowercase_digest_does_not_reach_stdout(self, tmp_path, monkeypatch, capsys):
        key, code, out = self._gate_denied(monkeypatch, tmp_path, capsys, str.lower)
        assert code == oa.EXIT_CONFIG
        assert key not in out.out
        assert key not in out.err

    def test_the_seam_scrubs_an_uppercase_digest_in_an_oserror(self):
        key = "b" * 64
        with pytest.raises(oa.ConfigError) as caught:
            with oa._digest_scrubbed(key):
                raise OSError(13, "denied", f"/root-{key.upper()}/x")
        assert key.upper() not in str(caught.value)
        assert oa._HELD_OUT_PLACEHOLDER in str(caught.value)

    def test_the_seam_scrubs_a_mixed_case_digest(self):
        key = "abcdef" + "0" * 58
        with pytest.raises(oa.ConfigError) as caught:
            with oa._digest_scrubbed(key):
                raise oa.ConfigError(f"/root-{'AbCdEf' + '0' * 58}/x")
        assert "AbCdEf" not in str(caught.value)

    def test_a_scrubbed_error_still_breaks_the_cause_chain(self):
        key = "c" * 64
        with pytest.raises(oa.ConfigError) as caught:
            with oa._digest_scrubbed(key):
                raise OSError(13, "denied", f"/root-{key.upper()}/x")
        assert caught.value.__cause__ is None

    def test_an_error_without_the_digest_keeps_its_message(self):
        with pytest.raises(oa.ConfigError) as caught:
            with oa._digest_scrubbed("d" * 64):
                raise OSError(28, "No space left on device")
        assert "No space left on device" in str(caught.value)

    def test_a_config_error_without_the_digest_is_reraised_as_itself(self):
        original = oa.ConfigError("nothing secret here")
        with pytest.raises(oa.ConfigError) as caught:
            with oa._digest_scrubbed("e" * 64):
                raise original
        assert caught.value is original
