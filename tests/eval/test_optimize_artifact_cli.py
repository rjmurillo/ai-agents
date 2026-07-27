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

import contextlib
import importlib.util
import io
import json
import os
import stat
import sys
import traceback
from contextvars import ContextVar, copy_context
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


def _legacy_split_fingerprint(task_ids, *, seed, sel_ratio, test_ratio=0.0):
    payload = json.dumps(
        {
            "seed": seed,
            "tasks": sorted(task_ids),
            "sel_ratio": sel_ratio,
            "test_ratio": test_ratio,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return oa.hashlib.sha256(payload.encode()).hexdigest()


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


def _enveloped(corpus, results: dict) -> dict:
    """A results file in the envelope the extractor writes."""
    return {"schema": "optimizer-results/1", "corpus": corpus, "results": results}


def _env_file(tmp_path, name: str, corpus, n: int = 10):
    """An enveloped results file of `n` passing tasks."""
    return _write(tmp_path, name, _enveloped(corpus, {f"t{i}": True for i in range(n)}))


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
        assert out["results"] == {"C1": True, "C2": False}

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
        assert out["results"] == {"C1": True}

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
        assert out["results"] == {"S1": True}

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

    def test_rule_extract_refuses_empty_scores(self, tmp_path, capsys):
        """Missing or empty scores block is degraded (fail closed)."""
        scenarios = _write(
            tmp_path,
            "scen.json",
            [
                {
                    "id": "S1",
                    "negative_case": False,
                    "mechanisms": {
                        "full": {
                            "scores": {},
                        }
                    },
                }
            ],
        )
        code, out = _run(capsys, "extract", "--kind", "rule", "--input", scenarios)
        assert code == EXIT_CONFIG
        assert "degraded rule report" in out["error"]
        assert "S1" in out["error"]

    def test_rule_extract_refuses_missing_scores(self, tmp_path, capsys):
        """None scores block is degraded (fail closed)."""
        scenarios = _write(
            tmp_path,
            "scen.json",
            [
                {
                    "id": "S1",
                    "negative_case": False,
                    "mechanisms": {
                        "full": {}
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
        assert out["results"] == {"S2": True}

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

    def test_a_scenario_that_is_not_an_object_is_not_called_degraded(self, tmp_path, capsys):
        """A non-object entry has no id to report, so the scan skips it.

        The degraded scan reports task ids. A bare string or number in the
        array supplies none, so naming it would mean inventing one. The
        scorer refuses the same input on its own terms, which is where a
        malformed array should be caught.
        """
        scenarios = _write(tmp_path, "scen.json", ["not-an-object"])
        code, out = _run(capsys, "extract", "--kind", "rule", "--input", scenarios)
        assert code == EXIT_CONFIG
        assert "degraded" not in out["error"]

    def test_a_scenario_with_no_mechanisms_block_is_degraded(self, tmp_path, capsys):
        """No mechanisms block at all is the same loss as an errored one.

        A scenario that never ran and a scenario that ran and failed both
        yield no score. Treating the absent block as a pass would score a
        measurement that does not exist.
        """
        scenarios = _write(
            tmp_path, "scen.json", [{"id": "S9", "negative_case": False}]
        )
        code, out = _run(capsys, "extract", "--kind", "rule", "--input", scenarios)
        assert code == EXIT_CONFIG
        assert "degraded rule report" in out["error"]
        assert "S9" in out["error"]

    def test_a_judge_failure_verdict_is_reported_when_no_scenario_carries_it(
        self, tmp_path, capsys
    ):
        """The summary verdict is the only witness when the scenarios look clean.

        A report whose scenarios all scored but whose summary says the judge
        failed is still degraded, and nothing under that rule names the loss.
        The placeholder id exists so the refusal has something to point at.
        """
        envelope = {
            "rules": {
                "refactoring": {
                    "summary": {"verdict": "FAIL_JUDGE_ERRORS"},
                    "scenarios": [
                        {
                            "id": "S4",
                            "negative_case": False,
                            "mechanisms": {"full": {"scores": {"activation_score": 5}}},
                        }
                    ],
                }
            }
        }
        path = _write(tmp_path, "rules.json", envelope)
        code, out = _run(capsys, "extract", "--kind", "rule", "--input", path)
        assert code == EXIT_CONFIG
        assert "refactoring::<FAIL_JUDGE_ERRORS>" in out["error"]

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
        assert out["results"] == {"S1": False}

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
        assert out["results"] == {"tests.test_a::test_x": True, "tests.test_a::test_y": False}

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
        assert out["results"] == {
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
        assert out["results"] == {"refactoring::S1": True}

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

    def test_an_untampered_legacy_numeric_ratio_split_gates_normally(
        self, tmp_path, capsys
    ):
        inc, cand, split = self._setup(tmp_path, capsys)
        split["sel_ratio"] = 0.4
        split["test_ratio"] = 0.0
        tasks = [str(t) for group in ("opt", "sel", "test") for t in split[group]]
        split["fingerprint"] = _legacy_split_fingerprint(
            tasks, seed=split["seed"], sel_ratio=0.4, test_ratio=0.0
        )
        path = _write(tmp_path, "split.json", split)
        code, out = _run_gate(capsys, tmp_path, "--incumbent", inc, "--candidate", cand,
                         "--split", path)
        assert code == 0
        assert out["decision"] == "ACCEPT"

    def test_legacy_numeric_fingerprint_does_not_alias_precise_string_ratio(
        self, tmp_path, capsys
    ):
        inc, cand, split = self._setup(tmp_path, capsys)
        tasks = [str(t) for group in ("opt", "sel", "test") for t in split[group]]
        split["sel_ratio"] = "0.40000000000000000000000000000000001"
        split["test_ratio"] = "0.0"
        split["fingerprint"] = _legacy_split_fingerprint(
            tasks, seed=split["seed"], sel_ratio=0.4, test_ratio=0.0
        )
        path = _write(tmp_path, "split.json", split)
        code, out = _run_gate(capsys, tmp_path, "--incumbent", inc, "--candidate", cand,
                         "--split", path)
        assert code == EXIT_LOGIC
        assert out["decision"] == "REJECT"
        assert "fingerprint" in out["reason"]

    def test_string_schema_ratio_split_round_trips_without_legacy_float_fallback(
        self, tmp_path, capsys
    ):
        inc = _write(tmp_path, "inc.json", {f"t{i}": False for i in range(10)})
        cand = _write(tmp_path, "cand.json", {f"t{i}": True for i in range(10)})
        _, split = _split(capsys, tmp_path, "--results", inc, "--seed", "s1",
                        "--sel-ratio", "0.5", "--min-sel", "0")
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

    def test_a_task_moved_in_legacy_numeric_ratio_split_is_refused(
        self, tmp_path, capsys
    ):
        inc, cand, split = self._setup(tmp_path, capsys)
        split["sel_ratio"] = 0.4
        split["test_ratio"] = 0.0
        tasks = [str(t) for group in ("opt", "sel", "test") for t in split[group]]
        split["fingerprint"] = _legacy_split_fingerprint(
            tasks, seed=split["seed"], sel_ratio=0.4, test_ratio=0.0
        )
        moved = split["opt"][0]
        split["opt"] = [t for t in split["opt"] if t != moved]
        split["sel"] = [*split["sel"], moved]
        path = _write(tmp_path, "split.json", split)
        code, out = _run_gate(capsys, tmp_path, "--incumbent", inc, "--candidate", cand,
                         "--split", path)
        assert code == EXIT_LOGIC
        assert out["decision"] == "REJECT"
        assert "fingerprint" in out["reason"]

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

    @pytest.mark.parametrize("ratio", ["1/0", "1/2"])
    def test_split_rejects_non_decimal_ratio_syntax_without_traceback(
        self, tmp_path, capsys, ratio
    ):
        inc = _write(tmp_path, "inc.json", {f"t{i}": False for i in range(10)})
        code, out = _run(capsys, "split", "--results", inc, "--seed", "s1",
                         "--sel-ratio", ratio, "--out", tmp_path / "split.json")
        assert code == EXIT_CONFIG
        assert "decimal ratio" in out["error"]

    @pytest.mark.parametrize("ratio", ["1e20000000", "1e-20000000", "-1e20000000"])
    def test_split_rejects_absurd_decimal_exponents_without_traceback(
        self, tmp_path, capsys, ratio
    ):
        inc = _write(tmp_path, "inc.json", {f"t{i}": False for i in range(10)})
        code, out = _run(capsys, "split", "--results", inc, "--seed", "s1",
                         "--sel-ratio", ratio, "--out", tmp_path / "split.json")
        assert code == EXIT_CONFIG
        assert "decimal ratio" in out["error"]

    def test_split_writes_the_ratios_it_used(self, tmp_path, capsys):
        inc = _write(tmp_path, "inc.json", {f"t{i}": False for i in range(10)})
        _, split = _split(capsys, tmp_path, "--results", inc, "--seed", "s1",
                        "--sel-ratio", "0.4", "--test-ratio", "0.2")
        assert split["sel_ratio"] == "0.4"
        assert split["test_ratio"] == "0.2"

    def test_split_uses_raw_decimal_ratio_text_for_half_up_rounding(
        self, tmp_path, capsys
    ):
        inc = _write(tmp_path, "inc.json", {f"t{i}": False for i in range(25)})
        _, split = _split(capsys, tmp_path, "--results", inc, "--seed", "s1",
                        "--sel-ratio", "0.58", "--min-sel", "0")
        assert len(split["sel"]) == 15
        assert len(split["opt"]) == 10
        assert split["sel_ratio"] == "0.58"


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

    @pytest.mark.parametrize("bad_bar", [1.5, -0.1, 2.0, -1])
    def test_a_ledger_with_out_of_range_max_p_is_a_config_error(
        self, tmp_path, capsys, bad_bar
    ):
        """An out-of-range max_p in the ledger is data corruption, not a gate refusal."""
        inc, cand, split, ledger = self._fixture(tmp_path, capsys)
        record = json.loads(split.read_text(encoding="utf-8"))
        holdout_key = oa._holdout_key(record)
        ledger.parent.mkdir(parents=True, exist_ok=True)
        ledger.write_text(
            json.dumps({
                "consultations": 0,
                "holdout": holdout_key,
                "max_consultations": 100,
                "max_p": bad_bar,
            }),
            encoding="utf-8",
        )
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


class TestTheReportedTailCanAlsoRefuse:
    """`--max-p` promotes the printed McNemar tail into a gate.

    A live run over the seven files in tests/evals/rule-scenarios/ scored the
    identical rule text twice. Five of 24 tasks flipped with no input change
    and the held-out group moved 6/10 to 7/10, so on a nondeterministic scorer
    a strictly-greater rule accepts variance. The tail was already computed
    and printed; before this flag it could not refuse anything.

    Default stays absent: a held-out group of three cannot reach a
    conventional floor, and a bar nothing can clear is not a gate.
    """

    def _gate(self, tmp_path, capsys, *extra, cap=1, seed="s1"):
        """Budget of one by default: the bar is family-wise, so a larger
        budget divides it and these cases are about the bar itself. `seed`
        draws a different held-out group, and so a different ledger, for
        cases that gate twice under different settings."""
        inc = _write(tmp_path, "inc.json", {f"t{i}": False for i in range(10)})
        cand = _write(tmp_path, "cand.json", {f"t{i}": True for i in range(10)})
        _, split = _split(capsys, tmp_path, "--results", inc, "--seed", seed)
        split_path = _write(tmp_path, "split.json", split)
        return _run_gate(
            capsys, tmp_path, "--incumbent", inc, "--candidate", cand,
            "--split", split_path, *extra, cap=cap,
        )

    def test_the_bar_is_divided_across_the_budget_it_was_declared_with(
        self, tmp_path, capsys
    ):
        """A tail that clears the bar at a budget of one misses it at ten."""
        _, tight = self._gate(tmp_path, capsys, "--max-p", "0.1", cap=1)
        assert tight["decision"] == "ACCEPT"
        _, spread = self._gate(tmp_path, capsys, "--max-p", "0.1", cap=10, seed="s2")
        assert spread["decision"] == "REJECT"
        assert spread["max_p_per_comparison"] == pytest.approx(0.01)

    def test_without_the_flag_a_win_with_a_wide_tail_still_accepts(self, tmp_path, capsys):
        code, out = self._gate(tmp_path, capsys)
        assert out["p_value"] == pytest.approx(0.0625)
        assert out["decision"] == "ACCEPT"
        assert code == EXIT_OK

    def test_the_same_win_is_refused_under_a_conventional_bar(self, tmp_path, capsys):
        code, out = self._gate(tmp_path, capsys, "--max-p", "0.05")
        assert out["decision"] == "REJECT"
        assert code == EXIT_LOGIC
        assert "0.0625" in out["reason"] and "0.05" in out["reason"]

    def test_a_bar_the_tail_clears_still_accepts(self, tmp_path, capsys):
        _, out = self._gate(tmp_path, capsys, "--max-p", "0.1")
        assert out["decision"] == "ACCEPT"

    def test_the_reported_tail_is_unchanged_by_the_bar(self, tmp_path, capsys):
        """The bar decides; it must not edit the evidence it decided on."""
        _, loose = self._gate(tmp_path, capsys, "--max-p", "1.0")
        assert loose["p_value"] == pytest.approx(0.0625)

    def test_a_refused_win_still_spends_its_consultation(self, tmp_path, capsys):
        """The held-out group was read to compute the tail. Reading is the cost."""
        _, out = self._gate(tmp_path, capsys, "--max-p", "0.0")
        assert out["decision"] == "REJECT"
        assert out["sel_consultations"] == 1

    def test_a_bar_outside_the_unit_interval_is_a_config_error(self, tmp_path, capsys):
        code, _ = self._gate(tmp_path, capsys, "--max-p", "1.5")
        assert code == EXIT_CONFIG

    def test_a_non_numeric_bar_is_refused_by_the_parser(self, tmp_path, capsys):
        with pytest.raises(SystemExit):
            self._gate(tmp_path, capsys, "--max-p", "nope")


class TestTheBarIsPinnedLikeTheBudget:
    """Round fourteen: a re-suppliable bar is not a bar.

    An adversarial reviewer (gpt-5.6-terra, 2026-07-27) pointed out that the
    ledger pins the consultation cap precisely so a caller who hits the budget
    cannot raise it and carry on, but left `--max-p` re-suppliable. A candidate
    refused at 0.05 could be gated again at 0.1 against the same held-out group
    and accepted. That is the mutable-cap defect wearing a different hat, so it
    gets the same treatment: the bar is fixed when the group is opened, and its
    absence is pinned just as firmly as its presence.

    Validating the flag before the ledger write matters for the same reason the
    write happens early. A nonsense bar is decidable without reading the group,
    so it must not cost a consultation.
    """

    def _fixture(self, tmp_path, capsys):
        inc = _write(tmp_path, "inc.json", {f"t{i}": i < 2 for i in range(10)})
        cand = _write(tmp_path, "cand.json", {f"t{i}": True for i in range(10)})
        _, record = _split(capsys, tmp_path, "--results", inc, "--seed", "pin")
        return inc, cand, _write(tmp_path, "split.json", record), record

    def _gate(self, capsys, inc, cand, split, record, *extra, cap="4"):
        return _run(
            capsys, "gate", "--incumbent", inc, "--candidate", cand,
            "--split", split, "--max-consultations", cap,
            "--incumbent-fingerprint", str(record["fingerprint"]), *extra,
        )

    def test_a_bar_cannot_be_loosened_after_the_group_was_opened(self, tmp_path, capsys):
        inc, cand, split, record = self._fixture(tmp_path, capsys)
        self._gate(capsys, inc, cand, split, record, "--max-p", "0.05")
        code, out = self._gate(capsys, inc, cand, split, record, "--max-p", "0.5")
        assert (code, out["decision"]) == (EXIT_LOGIC, "REJECT")
        assert "0.05" in out["reason"]

    def test_a_bar_cannot_be_dropped_after_the_group_was_opened(self, tmp_path, capsys):
        """Omitting the flag is the loosest setting of all, so it is pinned too."""
        inc, cand, split, record = self._fixture(tmp_path, capsys)
        self._gate(capsys, inc, cand, split, record, "--max-p", "0.05")
        code, out = self._gate(capsys, inc, cand, split, record)
        assert (code, out["decision"]) == (EXIT_LOGIC, "REJECT")

    def test_a_bar_cannot_be_added_after_the_group_was_opened_without_one(self, tmp_path, capsys):
        inc, cand, split, record = self._fixture(tmp_path, capsys)
        self._gate(capsys, inc, cand, split, record)
        code, out = self._gate(capsys, inc, cand, split, record, "--max-p", "0.05")
        assert (code, out["decision"]) == (EXIT_LOGIC, "REJECT")

    def test_the_same_bar_twice_is_not_a_mismatch(self, tmp_path, capsys):
        inc, cand, split, record = self._fixture(tmp_path, capsys)
        self._gate(capsys, inc, cand, split, record, "--max-p", "0.5")
        code, out = self._gate(capsys, inc, cand, split, record, "--max-p", "0.5")
        assert out.get("reason", "") == "" or "opened under" not in out["reason"]
        assert code in (EXIT_OK, EXIT_LOGIC)

    def test_a_pinned_bar_mismatch_does_not_publish_the_key(self, tmp_path, capsys):
        inc, cand, split, record = self._fixture(tmp_path, capsys)
        key = oa._holdout_key(record)
        self._gate(capsys, inc, cand, split, record, "--max-p", "0.05")
        _, out = self._gate(capsys, inc, cand, split, record, "--max-p", "0.5")
        assert key not in json.dumps(out)

    def test_a_nonsense_bar_costs_no_consultation(self, tmp_path, capsys):
        """Decidable without reading the group, so it must not charge for one."""
        inc, cand, split, record = self._fixture(tmp_path, capsys)
        code, _ = self._gate(capsys, inc, cand, split, record, "--max-p", "1.5")
        assert code == EXIT_CONFIG
        assert not oa._ledger_path(oa._holdout_key(record)).exists()

    def test_a_nonsense_bar_is_config_error_even_on_an_exhausted_budget(self, tmp_path, capsys):
        """The flag is wrong whether or not the budget would have refused."""
        inc, cand, split, record = self._fixture(tmp_path, capsys)
        for _ in range(2):
            self._gate(capsys, inc, cand, split, record, "--max-p", "0.5", cap="2")
        code, _ = self._gate(capsys, inc, cand, split, record, "--max-p", "-1", cap="2")
        assert code == EXIT_CONFIG

    def test_the_verdict_reports_the_bar_it_applied(self, tmp_path, capsys):
        inc, cand, split, record = self._fixture(tmp_path, capsys)
        _, out = self._gate(capsys, inc, cand, split, record, "--max-p", "0.5")
        assert out["max_p"] == 0.5
        assert out["max_p_per_comparison"] == 0.125

    def test_the_verdict_reports_an_absent_bar_as_absent(self, tmp_path, capsys):
        inc, cand, split, record = self._fixture(tmp_path, capsys)
        _, out = self._gate(capsys, inc, cand, split, record)
        assert out["max_p"] is None and out["max_p_per_comparison"] is None

    def test_a_malformed_bar_in_the_ledger_is_named(self, tmp_path, capsys):
        """A hand-edited ledger says so rather than comparing a string to a float."""
        inc, cand, split, record = self._fixture(tmp_path, capsys)
        key = oa._holdout_key(record)
        ledger = oa._ledger_path(key)
        ledger.parent.mkdir(parents=True, exist_ok=True)
        ledger.write_text(
            json.dumps(
                {
                    "consultations": 0,
                    "holdout": key,
                    "max_consultations": 4,
                    "max_p": "loose",
                }
            ),
            encoding="utf-8",
        )
        code, out = self._gate(capsys, inc, cand, split, record, "--max-p", "0.5")
        assert code == EXIT_CONFIG
        assert "max_p" in out["error"] and key not in json.dumps(out)

    def test_a_ledger_written_before_the_bar_existed_reads_as_no_bar(
        self, tmp_path, capsys
    ):
        """An absent key is the absent policy, so old ledgers keep working."""
        inc, cand, split, record = self._fixture(tmp_path, capsys)
        key = oa._holdout_key(record)
        ledger = oa._ledger_path(key)
        ledger.parent.mkdir(parents=True, exist_ok=True)
        ledger.write_text(
            json.dumps({"consultations": 0, "holdout": key, "max_consultations": 4}),
            encoding="utf-8",
        )
        code, out = self._gate(capsys, inc, cand, split, record)
        assert code in (EXIT_OK, EXIT_LOGIC)
        assert out["max_p"] is None

    def test_a_contract_violation_inside_the_gate_exits_as_config(
        self, tmp_path, capsys, monkeypatch
    ):
        """Defense in depth: cmd_gate screens the flag, but the library still
        refuses an incoherent call rather than escaping as a traceback."""
        inc, cand, split, record = self._fixture(tmp_path, capsys)

        def _explode(*_args, **_kwargs):
            raise ValueError("max_p needs a p_value to judge")

        monkeypatch.setattr(oa, "gate", _explode)
        code, out = self._gate(capsys, inc, cand, split, record, "--max-p", "0.5")
        assert code == EXIT_CONFIG
        assert "p_value" in out["error"]


# The two corpus identities the architect incident actually disagreed on,
# padded to the sha256 width the producer emits.
_CORPUS_ONE = "be99fa1b1180".ljust(64, "0")
_CORPUS_TWO = "26136df314d6".ljust(64, "0")


class TestTheSeamCarriesTheCorpusItWasScoredAgainst:
    """A comparison of two results files says nothing unless both scored the
    same tasks, and until now the seam could not tell.

    On 2026-07-27 two architect-spike runs were gated against each other and
    read as a null control. They agreed on `model_id` and `agent_prompt_sha`
    and disagreed on `fixture_set_sha`: every one of the eight fixture files
    had changed between them. The accept was published before the mismatch was
    found. The report format already carried the falsifier, and
    `_fixture_set_sha`'s own docstring says it exists so a report consumer can
    verify two runs hit the same set. `extract` never read it.

    Task ids do not substitute. All eight ids matched across those two runs
    while the contents behind them differed, so a key-set comparison would
    have passed the pair through.
    """

    def _agent_report(self, tmp_path, name, corpus, rates=None):
        payload = {
            "per_fixture_pass_rates": rates
            or {f"t{i}": {"agent": [1.0 if i < 5 else 0.0]} for i in range(10)}
        }
        if corpus is not None:
            payload["fixture_set_sha"] = corpus
        return _write(tmp_path, name, payload)

    def _extract(self, capsys, report, out_name, tmp_path):
        _, out = _run(capsys, "extract", "--kind", "agent", "--input", report)
        return _write(tmp_path, out_name, out)

    def _gate_pair(self, tmp_path, capsys, inc_corpus, cand_corpus, seed="c1"):
        inc = self._extract(
            capsys, self._agent_report(tmp_path, "ri.json", inc_corpus), "inc.json", tmp_path
        )
        cand = self._extract(
            capsys,
            self._agent_report(
                tmp_path,
                "rc.json",
                cand_corpus,
                rates={f"t{i}": {"agent": [1.0]} for i in range(10)},
            ),
            "cand.json",
            tmp_path,
        )
        _, split = _split(capsys, tmp_path, "--results", inc, "--seed", seed)
        split_path = _write(tmp_path, "split.json", split)
        code, out = _run_gate(
            capsys, tmp_path, "--incumbent", inc, "--candidate", cand,
            "--split", split_path, cap=5,
        )
        return code, out, split

    # -- extract carries it forward ----------------------------------------

    def test_extract_carries_the_report_s_own_corpus_identity(self, tmp_path, capsys):
        report = self._agent_report(tmp_path, "r.json", _CORPUS_ONE)
        code, out = _run(capsys, "extract", "--kind", "agent", "--input", report)
        assert code == EXIT_OK
        assert out["corpus"] == _CORPUS_ONE
        assert out["results"]["t0"] is True
        assert out["schema"] == "optimizer-results/1"

    def test_a_report_without_the_field_extracts_an_unknown_corpus(self, tmp_path, capsys):
        """Absent is null, never a value invented from the task ids.

        A synthesized id would make two unrelated corpora compare equal
        whenever their ids matched, which is the exact failure this guards.
        """
        report = self._agent_report(tmp_path, "r.json", None)
        code, out = _run(capsys, "extract", "--kind", "agent", "--input", report)
        assert code == EXIT_OK
        assert out["corpus"] is None

    def test_a_non_string_corpus_field_in_the_report_is_refused(self, tmp_path, capsys):
        """A corpus identity that is not an identity is a config error, not a
        value to coerce. Coercing it would let `17` and `"17"` compare equal
        across two reports that meant different things."""
        report = _write(
            tmp_path, "r.json",
            {"per_fixture_pass_rates": {"t0": {"agent": [1.0]}}, "fixture_set_sha": 17},
        )
        code, _ = _run(capsys, "extract", "--kind", "agent", "--input", report)
        assert code == EXIT_CONFIG

    def test_the_hook_path_has_no_corpus_source_and_says_so(self, tmp_path, capsys):
        junit = tmp_path / "j.xml"
        junit.write_text(
            '<testsuite><testcase classname="tests.a" name="test_x"/></testsuite>',
            encoding="utf-8",
        )
        code, out = _run(capsys, "extract", "--kind", "hook", "--input", junit)
        assert code == EXIT_OK
        assert out["corpus"] is None
        assert out["results"]

    # -- the reader ---------------------------------------------------------

    def test_a_bare_mapping_still_reads_as_results_with_an_unknown_corpus(self, tmp_path):
        path = _write(tmp_path, "legacy.json", {"a": True, "b": False})
        parsed = oa._read_results(path)
        assert parsed.results == {"a": True, "b": False}
        assert parsed.corpus is None

    def test_a_task_named_schema_does_not_masquerade_as_an_envelope(self, tmp_path):
        """The discriminator is a string-valued `schema`, not the key alone.

        Bare mappings are all-boolean by construction, so a task id that
        collides with the envelope's key still parses as a task.
        """
        path = _write(tmp_path, "legacy.json", {"schema": True, "results": False})
        parsed = oa._read_results(path)
        assert parsed.results == {"schema": True, "results": False}
        assert parsed.corpus is None

    def test_an_unrecognized_envelope_version_is_refused_not_guessed(self, tmp_path):
        path = _write(
            tmp_path, "future.json",
            {"schema": "optimizer-results/2", "corpus": None, "results": {"a": True}},
        )
        with pytest.raises(oa.ConfigError, match="optimizer-results/2"):
            oa._read_results(path)

    def test_an_envelope_whose_corpus_is_not_a_string_is_refused(self, tmp_path):
        path = _write(
            tmp_path, "bad.json",
            {"schema": "optimizer-results/1", "corpus": 17, "results": {"a": True}},
        )
        with pytest.raises(oa.ConfigError, match="corpus"):
            oa._read_results(path)

    def test_an_envelope_without_results_is_refused(self, tmp_path):
        path = _write(tmp_path, "bad.json", {"schema": "optimizer-results/1", "corpus": None})
        with pytest.raises(oa.ConfigError, match="results"):
            oa._read_results(path)

    def test_non_boolean_verdicts_are_still_refused_inside_an_envelope(self, tmp_path):
        path = _write(
            tmp_path, "bad.json",
            {"schema": "optimizer-results/1", "corpus": None, "results": {"a": 1}},
        )
        with pytest.raises(oa.ConfigError, match="non-boolean"):
            oa._read_results(path)

    # -- the refusal --------------------------------------------------------

    def test_two_known_and_different_corpora_are_refused_uncompared(self, tmp_path, capsys):
        code, out, _ = self._gate_pair(tmp_path, capsys, _CORPUS_ONE, _CORPUS_TWO)
        assert code == EXIT_LOGIC
        assert out["decision"] == "REJECT"
        assert out["compared"] is False
        assert "corpus" in out["reason"]

    def test_the_refusal_spends_no_consultation(self, tmp_path, capsys):
        """Decidable from two header fields, so it must be free.

        A mismatch that cost a consultation would let a caller burn a budget
        it can never spend usefully, and the pair is unusable no matter how
        much budget remains.
        """
        code, out, split = self._gate_pair(tmp_path, capsys, _CORPUS_ONE, _CORPUS_TWO)
        assert out["consultations"] == 0
        assert not oa._ledger_path(oa._holdout_key(split)).exists()

    def test_matching_corpora_gate_normally(self, tmp_path, capsys):
        code, out, _ = self._gate_pair(tmp_path, capsys, _CORPUS_ONE, _CORPUS_ONE, seed="c2")
        assert out["compared"] is True
        assert out["corpus_verified"] is True

    def test_an_unknown_corpus_beside_a_known_one_is_refused(self, tmp_path, capsys):
        """This assertion is the inverse of the one it replaces.

        The first cut let unknown pass beside known, on the reasoning that the
        rule and hook paths publish no corpus and refusing unknown would
        disable the gate for them. That reasoning holds for a pair where
        *neither* side knows, and a fifteenth review showed it does not survive
        the asymmetric case: it made the refusal deletable, since stripping the
        envelope off either file turns a known mismatch into an unknown that
        compares. A pair scored on one corpus does not have one side that
        forgot.
        """
        code, out, _ = self._gate_pair(tmp_path, capsys, None, _CORPUS_TWO, seed="c3")
        assert code == EXIT_LOGIC
        assert out["compared"] is False

    def test_two_unknown_corpora_are_reported_rather_than_silently_allowed(
        self, tmp_path, capsys
    ):
        """Unknown on both sides is not refused: the rule and hook paths have
        no corpus source at all, so refusing there would disable the gate for
        two of three artifact classes. It is reported so an operator reading
        the verdict knows the comparison was never checked."""
        code, out, _ = self._gate_pair(tmp_path, capsys, None, None, seed="c3b")
        assert out["compared"] is True
        assert out["corpus_verified"] is False

    def test_both_unknown_gates_and_reports_unverified(self, tmp_path, capsys):
        code, out, _ = self._gate_pair(tmp_path, capsys, None, None, seed="c4")
        assert out["compared"] is True
        assert out["corpus_verified"] is False

    def test_the_mismatch_refusal_names_no_held_out_task(self, tmp_path, capsys):
        _, out, split = self._gate_pair(tmp_path, capsys, _CORPUS_ONE, _CORPUS_TWO, seed="c5")
        blob = json.dumps(out)
        for task_id in split["sel"] + split["test"]:
            assert task_id not in blob
        assert oa._holdout_key(split) not in blob

    def test_an_exhausted_budget_does_not_mask_the_mismatch(self, tmp_path, capsys):
        """Same precedent as the `--max-p` range check: a refusal decidable
        without the held-out group must not be reordered behind one that needs
        the ledger, or the caller is told to buy budget for a comparison that
        can never be valid."""
        inc = self._extract(
            capsys, self._agent_report(tmp_path, "ri.json", _CORPUS_ONE), "inc.json", tmp_path
        )
        cand = self._extract(
            capsys, self._agent_report(tmp_path, "rc.json", _CORPUS_TWO), "cand.json", tmp_path
        )
        _, split = _split(capsys, tmp_path, "--results", inc, "--seed", "c6")
        split_path = _write(tmp_path, "split.json", split)
        code, out = _run_gate(
            capsys, tmp_path, "--incumbent", inc, "--candidate", cand,
            "--split", split_path, cap=1, spent=1,
        )
        assert out["decision"] == "REJECT"
        assert "corpus" in out["reason"]

    # -- the other readers keep working -------------------------------------

    def test_split_reads_an_envelope(self, tmp_path, capsys):
        inc = self._extract(
            capsys, self._agent_report(tmp_path, "r.json", _CORPUS_ONE), "inc.json", tmp_path
        )
        code, split = _split(capsys, tmp_path, "--results", inc, "--seed", "c7")
        assert code == EXIT_OK
        assert len(split["opt"]) + len(split["sel"]) + len(split["test"]) == 10

    def test_score_reads_an_envelope(self, tmp_path, capsys):
        inc = self._extract(
            capsys, self._agent_report(tmp_path, "r.json", _CORPUS_ONE), "inc.json", tmp_path
        )
        _, split = _split(capsys, tmp_path, "--results", inc, "--seed", "c8")
        split_path = _write(tmp_path, "split.json", split)
        code, out = _run(
            capsys, "score", "--results", inc, "--split", split_path, "--group", "opt"
        )
        assert code == EXIT_OK
        assert 0.0 <= out["score"] <= 1.0


_SHA_A = "a" * 64
_SHA_B = "b" * 64


class TestTheCorpusPinCannotBeStrippedAway:
    """A refusal a caller can delete their way past is not a refusal.

    The first cut of the corpus guard refused only when both files declared a
    corpus and the two disagreed. That left the mismatch reachable by omission:
    piping either side through anything that emits a bare mapping, which is
    what every consumer wrote before the envelope existed, turned the pair from
    "known to differ" into "unknown", and unknown compared. The bypass needed no
    intent. It is the same shape as the incident it was built for, where nobody
    edited anything and the field simply went unread.

    Two changes close it. `split` pins the corpus of the results it was drawn
    from, so the baseline commitment carries the corpus rather than the
    comparison inferring it. And one known corpus beside an unknown one is a
    conflict, because the asymmetry is itself the evidence: a pair scored on one
    corpus does not have one side that forgot.

    The limit is worth stating. The split file is caller-supplied and its
    corpus pin is outside the fingerprint, so a caller who edits two files in
    concert can still defeat this. That is not what it defends against. It
    defends against omission, which is the failure that actually happened.
    """

    def _report(self, tmp_path, name, corpus, rates=None):
        payload = {
            "per_fixture_pass_rates": rates
            or {f"t{i}": {"agent": [1.0 if i < 5 else 0.0]} for i in range(10)}
        }
        if corpus is not None:
            payload["fixture_set_sha"] = corpus
        return _write(tmp_path, name, payload)

    def _extract(self, capsys, report, out_name, tmp_path):
        _, out = _run(capsys, "extract", "--kind", "agent", "--input", report)
        return _write(tmp_path, out_name, out)

    def _pair(self, tmp_path, capsys, inc_corpus, cand_corpus):
        """Two enveloped results files that differ only in verdicts and corpus."""
        inc = self._extract(
            capsys, self._report(tmp_path, "ri.json", inc_corpus), "inc.json", tmp_path
        )
        cand = self._extract(
            capsys,
            self._report(
                tmp_path, "rc.json", cand_corpus,
                rates={f"t{i}": {"agent": [1.0]} for i in range(10)},
            ),
            "cand.json",
            tmp_path,
        )
        return inc, cand

    def _bare(self, tmp_path, name, path):
        """The same results with the envelope stripped, as an old consumer emits."""
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return _write(tmp_path, name, payload["results"])

    def _gate(self, tmp_path, capsys, inc, cand, seed, split_from=None, **kw):
        _, split = _split(capsys, tmp_path, "--results", split_from or inc, "--seed", seed)
        split_path = _write(tmp_path, "split.json", split)
        return _run_gate(
            capsys, tmp_path, "--incumbent", inc, "--candidate", cand,
            "--split", split_path, cap=5, **kw
        )

    # -- the pin ------------------------------------------------------------

    def test_split_records_the_corpus_of_the_results_it_was_drawn_from(
        self, tmp_path, capsys
    ):
        inc = self._extract(
            capsys, self._report(tmp_path, "r.json", _SHA_A), "inc.json", tmp_path
        )
        code, split = _split(capsys, tmp_path, "--results", inc, "--seed", "p1")
        assert code == EXIT_OK
        assert split["corpus"] == _SHA_A

    def test_a_split_drawn_from_a_task_list_pins_nothing(self, tmp_path, capsys):
        tasks = tmp_path / "tasks.txt"
        tasks.write_text("\n".join(f"t{i}" for i in range(10)), encoding="utf-8")
        code, split = _split(capsys, tmp_path, "--tasks", tasks, "--seed", "p2")
        assert code == EXIT_OK
        assert "corpus" not in split

    def test_a_split_drawn_from_a_bare_mapping_pins_unknown(self, tmp_path, capsys):
        legacy = _write(tmp_path, "legacy.json", {f"t{i}": i < 5 for i in range(10)})
        code, split = _split(capsys, tmp_path, "--results", legacy, "--seed", "p3")
        assert code == EXIT_OK
        assert split["corpus"] is None

    # -- the bypass, closed -------------------------------------------------

    def test_stripping_one_envelope_does_not_buy_a_comparison(self, tmp_path, capsys):
        inc, cand = self._pair(tmp_path, capsys, _SHA_A, _SHA_B)
        stripped = self._bare(tmp_path, "cand-bare.json", cand)
        code, out = self._gate(tmp_path, capsys, inc, stripped, "p4")
        assert code == EXIT_LOGIC
        assert out["decision"] == "REJECT"
        assert out["compared"] is False
        assert out["consultations"] == 0

    def test_stripping_both_envelopes_does_not_buy_a_comparison(self, tmp_path, capsys):
        inc, cand = self._pair(tmp_path, capsys, _SHA_A, _SHA_B)
        code, split = _split(capsys, tmp_path, "--results", inc, "--seed", "p5")
        split_path = _write(tmp_path, "split.json", split)
        code, out = _run_gate(
            capsys, tmp_path,
            "--incumbent", self._bare(tmp_path, "i-bare.json", inc),
            "--candidate", self._bare(tmp_path, "c-bare.json", cand),
            "--split", split_path, cap=5,
        )
        assert out["decision"] == "REJECT"
        assert out["compared"] is False

    def test_one_known_corpus_beside_an_unknown_one_conflicts_without_a_pin(
        self, tmp_path, capsys
    ):
        """No pin at all, so the conflict has to come from the pair itself."""
        inc, cand = self._pair(tmp_path, capsys, _SHA_A, None)
        _, split = _split(capsys, tmp_path, "--results", inc, "--seed", "p6")
        split.pop("corpus")
        split_path = _write(tmp_path, "split.json", split)
        code, out = _run_gate(
            capsys, tmp_path, "--incumbent", inc, "--candidate", cand,
            "--split", split_path, cap=5,
        )
        assert out["decision"] == "REJECT"
        assert out["compared"] is False

    # -- what must keep working ---------------------------------------------

    def test_two_unknown_corpora_still_compare(self, tmp_path, capsys):
        """The rule and hook paths publish no corpus and must not be disabled."""
        inc = _write(tmp_path, "inc.json", {f"t{i}": i < 5 for i in range(10)})
        cand = _write(tmp_path, "cand.json", {f"t{i}": True for i in range(10)})
        code, out = self._gate(tmp_path, capsys, inc, cand, "p7")
        assert out["compared"] is True
        assert out["corpus_verified"] is False

    def test_a_matching_digest_on_both_sides_compares_and_reports_verified(
        self, tmp_path, capsys
    ):
        inc, cand = self._pair(tmp_path, capsys, _SHA_A, _SHA_A)
        code, out = self._gate(tmp_path, capsys, inc, cand, "p8")
        assert out["compared"] is True
        assert out["corpus_verified"] is True

    def test_a_pinned_digest_that_both_files_match_compares(self, tmp_path, capsys):
        inc, cand = self._pair(tmp_path, capsys, _SHA_A, _SHA_A)
        _, split = _split(capsys, tmp_path, "--results", inc, "--seed", "p9")
        assert split["corpus"] == _SHA_A
        split_path = _write(tmp_path, "split.json", split)
        _, out = _run_gate(
            capsys, tmp_path, "--incumbent", inc, "--candidate", cand,
            "--split", split_path, cap=5,
        )
        assert out["compared"] is True

    # -- the digest has to look like one ------------------------------------

    @pytest.mark.parametrize(
        "bad", ["", "   ", "be99fa1b1180", "A" * 64, "g" * 64, "a" * 63, "a" * 65]
    )
    def test_a_corpus_that_is_not_a_sha256_digest_is_refused_at_extract(
        self, tmp_path, capsys, bad
    ):
        report = self._report(tmp_path, "r.json", bad)
        code, _ = _run(capsys, "extract", "--kind", "agent", "--input", report)
        assert code == EXIT_CONFIG

    def test_a_lowercase_sha256_digest_survives_extract(self, tmp_path, capsys):
        report = self._report(tmp_path, "r.json", _SHA_A)
        code, out = _run(capsys, "extract", "--kind", "agent", "--input", report)
        assert code == EXIT_OK
        assert out["corpus"] == _SHA_A

    def test_an_envelope_whose_corpus_is_not_a_digest_is_refused(self, tmp_path):
        path = _write(
            tmp_path, "bad.json",
            {"schema": "optimizer-results/1", "corpus": "", "results": {"a": True}},
        )
        with pytest.raises(oa.ConfigError, match="corpus"):
            oa._read_results(path)

    # -- ordering: a parse error must not stand in for the ledger's answer ---

    def test_malformed_results_do_not_preempt_an_exhausted_ledger(
        self, tmp_path, capsys
    ):
        """The budget refusal is the authoritative one and has to survive.

        Reading both files before the lock is what makes the corpus refusal
        free. Doing the *whole* read there would let a bad verdict mapping
        answer in place of the ledger, which tells the caller to fix the wrong
        thing.
        """
        inc = _write(tmp_path, "inc.json", {f"t{i}": i < 5 for i in range(10)})
        _, split = _split(capsys, tmp_path, "--results", inc, "--seed", "pa")
        split_path = _write(tmp_path, "split.json", split)
        bad = _write(tmp_path, "cand.json", {f"t{i}": "yes" for i in range(10)})
        code, out = _run_gate(
            capsys, tmp_path, "--incumbent", inc, "--candidate", bad,
            "--split", split_path, cap=1, spent=1,
        )
        assert code == EXIT_LOGIC
        assert out["decision"] == "REJECT"
        assert "consultation" in out["reason"]

    def test_unreadable_results_do_not_preempt_an_exhausted_ledger(
        self, tmp_path, capsys
    ):
        inc = _write(tmp_path, "inc.json", {f"t{i}": i < 5 for i in range(10)})
        _, split = _split(capsys, tmp_path, "--results", inc, "--seed", "pb")
        split_path = _write(tmp_path, "split.json", split)
        junk = tmp_path / "cand.json"
        junk.write_text("{not json", encoding="utf-8")
        code, out = _run_gate(
            capsys, tmp_path, "--incumbent", inc, "--candidate", junk,
            "--split", split_path, cap=1, spent=1,
        )
        assert code == EXIT_LOGIC
        assert out["decision"] == "REJECT"
        assert "consultation" in out["reason"]

    def test_malformed_results_still_fail_loudly_when_the_budget_allows(
        self, tmp_path, capsys
    ):
        """Deferring the full read must not swallow it."""
        inc = _write(tmp_path, "inc.json", {f"t{i}": i < 5 for i in range(10)})
        _, split = _split(capsys, tmp_path, "--results", inc, "--seed", "pc")
        split_path = _write(tmp_path, "split.json", split)
        bad = _write(tmp_path, "cand.json", {f"t{i}": "yes" for i in range(10)})
        code, _ = _run_gate(
            capsys, tmp_path, "--incumbent", inc, "--candidate", bad,
            "--split", split_path, cap=5,
        )
        assert code == EXIT_CONFIG

    def test_the_preflight_refusal_names_no_task_and_no_digest(
        self, tmp_path, capsys
    ):
        inc, cand = self._pair(tmp_path, capsys, _SHA_A, _SHA_B)
        _, split = _split(capsys, tmp_path, "--results", inc, "--seed", "pd")
        split_path = _write(tmp_path, "split.json", split)
        _, out = _run_gate(
            capsys, tmp_path, "--incumbent", inc, "--candidate", cand,
            "--split", split_path, cap=5,
        )
        blob = json.dumps(out)
        assert oa._holdout_key(split) not in blob
        assert not any(t in blob for t in split["sel"] + split["test"])

    def test_a_preflight_read_failure_leaves_the_digest_out_of_the_error(
        self, tmp_path, capsys, monkeypatch
    ):
        """Whatever goes wrong under the preflight is still scrubbed.

        The error lands on stdout as JSON, not on stderr: `main` turns a
        `ConfigError` into a payload so a driver can tell a refusal from a
        config failure by reading a field. An earlier version of this test read
        stderr after `_run_gate` had already drained the capture, so it asserted
        the digest was absent from an empty string and could not have failed.
        """
        inc = _write(tmp_path, "inc.json", {f"t{i}": i < 5 for i in range(10)})
        _, split = _split(capsys, tmp_path, "--results", inc, "--seed", "pe")
        split_path = _write(tmp_path, "split.json", split)
        key = oa._holdout_key(split)
        monkeypatch.setattr(oa, "_corpus_header", lambda _p: (_ for _ in ()).throw(
            OSError(f"cannot open {key}")
        ))
        code, out = _run_gate(
            capsys, tmp_path, "--incumbent", inc, "--candidate", inc,
            "--split", split_path, cap=5,
        )
        assert code == EXIT_CONFIG
        assert out["type"] == "ConfigError"
        assert key not in json.dumps(out)
        assert oa._HELD_OUT_PLACEHOLDER in out["error"]

    def test_that_scrub_test_would_fail_without_the_scrubber(
        self, tmp_path, capsys, monkeypatch
    ):
        """The negative control the tautological version never had."""
        inc = _write(tmp_path, "inc.json", {f"t{i}": i < 5 for i in range(10)})
        _, split = _split(capsys, tmp_path, "--results", inc, "--seed", "pe2")
        split_path = _write(tmp_path, "split.json", split)
        key = oa._holdout_key(split)
        monkeypatch.setattr(oa, "_corpus_header", lambda _p: (_ for _ in ()).throw(
            OSError(f"cannot open {key}")
        ))
        monkeypatch.setattr(oa, "_digest_scrubbed", contextlib.nullcontext)
        with pytest.raises(OSError) as caught:
            _run_gate(
                capsys, tmp_path, "--incumbent", inc, "--candidate", inc,
                "--split", split_path, cap=5,
            )
        assert key in str(caught.value)

    # -- the predicate on its own -------------------------------------------

    @pytest.mark.parametrize(
        ("pin", "inc", "cand", "conflict"),
        [
            (oa._UNPINNED, None, None, False),
            (oa._UNPINNED, _SHA_A, _SHA_A, False),
            (None, None, None, False),
            (_SHA_A, _SHA_A, _SHA_A, False),
            (oa._UNPINNED, _SHA_A, _SHA_B, True),
            (oa._UNPINNED, _SHA_A, None, True),
            (oa._UNPINNED, None, _SHA_A, True),
            (_SHA_A, _SHA_A, None, True),
            (_SHA_A, None, None, True),
            (_SHA_A, _SHA_B, _SHA_B, True),
            (None, _SHA_A, _SHA_A, True),
        ],
    )
    def test_the_conflict_rule_is_more_than_one_declared_corpus(
        self, pin, inc, cand, conflict
    ):
        assert oa._corpus_conflict(pin, inc, cand) is conflict

    def test_an_absent_pin_is_not_the_same_as_a_pin_of_unknown(self):
        """`None` is a legal pin, so absence needs a value JSON cannot produce.

        Collapsing the two would make a split written before the pin existed
        assert that its corpus was unknown, which would refuse every enveloped
        pair gated against an older split.
        """
        assert oa._corpus_conflict(oa._UNPINNED, _SHA_A, _SHA_A) is False
        assert oa._corpus_conflict(None, _SHA_A, _SHA_A) is True
        assert json.loads(json.dumps({"corpus": None}))["corpus"] is None


class TestWhatTheVerdictClaimsWasChecked:
    """Round sixteen: the pin is caller-supplied, so say when it was absent.

    `corpus_verified` reports that the two results agree. It cannot report that
    the split was drawn from the corpus they name, because a caller who deletes
    the split's `corpus` key leaves two agreeing files and nothing to contradict
    them. Refusing that pair would disable the gate for the rule and hook paths,
    which pin nothing at all, so the verdict names the weaker guarantee instead
    of hiding it behind the stronger one.
    """

    def test_a_pinned_split_that_agrees_reports_both_facts(self, tmp_path, capsys):
        inc = _env_file(tmp_path, "inc.json", _CORPUS_ONE)
        _, split = _split(capsys, tmp_path, "--results", inc, "--seed", "pin-a")
        split_path = _write(tmp_path, "split.json", split)
        _, out = _run_gate(
            capsys, tmp_path, "--incumbent", inc, "--candidate", inc,
            "--split", split_path, cap=5,
        )
        assert out["corpus_verified"] is True
        assert out["corpus_pinned"] is True

    def test_deleting_the_pin_is_visible_in_the_verdict(self, tmp_path, capsys):
        """The one-file edit the guard cannot refuse is the one it must report."""
        inc = _env_file(tmp_path, "inc.json", _CORPUS_ONE)
        _, split = _split(capsys, tmp_path, "--results", inc, "--seed", "pin-b")
        del split["corpus"]
        split_path = _write(tmp_path, "split.json", split)
        _, out = _run_gate(
            capsys, tmp_path, "--incumbent", inc, "--candidate", inc,
            "--split", split_path, cap=5,
        )
        assert out["corpus_verified"] is True
        assert out["corpus_pinned"] is False

    def test_a_task_list_split_pins_nothing_and_says_so(self, tmp_path, capsys):
        tasks = tmp_path / "ids.txt"
        tasks.write_text("\n".join(f"t{i}" for i in range(10)), encoding="utf-8")
        _, split = _split(capsys, tmp_path, "--tasks", tasks, "--seed", "pin-c")
        split_path = _write(tmp_path, "split.json", split)
        inc = _env_file(tmp_path, "inc.json", _CORPUS_ONE)
        _, out = _run_gate(
            capsys, tmp_path, "--incumbent", inc, "--candidate", inc,
            "--split", split_path, cap=5,
        )
        assert out["corpus_verified"] is True
        assert out["corpus_pinned"] is False

    def test_legacy_files_claim_neither(self, tmp_path, capsys):
        inc = _write(tmp_path, "inc.json", {f"t{i}": True for i in range(10)})
        _, split = _split(capsys, tmp_path, "--results", inc, "--seed", "pin-d")
        split_path = _write(tmp_path, "split.json", split)
        _, out = _run_gate(
            capsys, tmp_path, "--incumbent", inc, "--candidate", inc,
            "--split", split_path, cap=5,
        )
        assert out["corpus_verified"] is False
        assert out["corpus_pinned"] is False


class TestTheCorpusIsRecheckedAgainstWhatWasActuallyScored:
    """Round sixteen: the preflight reads headers, the gate reads bodies.

    Two reads of one path can disagree, whether because a writer moved under
    them or because the two parsers drift. The values the comparison is scored
    from are the ones in `ResultsFile`, so those are the ones that have to
    agree before a consultation is charged.
    """

    def _swapped(self, tmp_path, capsys, monkeypatch, header_says):
        inc = _env_file(tmp_path, "inc.json", _CORPUS_ONE)
        cand = _env_file(tmp_path, "cand.json", _CORPUS_TWO)
        _, split = _split(capsys, tmp_path, "--results", inc, "--seed", "toc")
        split_path = _write(tmp_path, "split.json", split)
        real = oa._corpus_header
        monkeypatch.setattr(
            oa, "_corpus_header",
            lambda p: header_says if Path(p) == Path(cand) else real(p),
        )
        return _run_gate(
            capsys, tmp_path, "--incumbent", inc, "--candidate", cand,
            "--split", split_path, cap=5,
        )

    def test_a_file_that_changes_after_the_preflight_is_refused(
        self, tmp_path, capsys, monkeypatch
    ):
        code, out = self._swapped(tmp_path, capsys, monkeypatch, _CORPUS_ONE)
        assert code == EXIT_LOGIC
        assert out["decision"] == "REJECT"
        assert out["compared"] is False

    def test_the_recheck_refuses_before_the_consultation_is_charged(
        self, tmp_path, capsys, monkeypatch
    ):
        """Round seventeen strengthened this.

        It read `sel_consultations`, which reports prior ledger spend and was
        therefore zero here whether or not this run charged. The claim worth
        making is that no ledger exists at all afterward.
        """
        _, out = self._swapped(tmp_path, capsys, monkeypatch, _CORPUS_ONE)
        assert out["consultations"] == 0
        record = json.loads((tmp_path / "split.json").read_text(encoding="utf-8"))
        assert not oa._ledger_path(oa._holdout_key(record)).exists()

    def test_an_honest_preflight_still_compares(self, tmp_path, capsys, monkeypatch):
        code, out = self._swapped(tmp_path, capsys, monkeypatch, _CORPUS_TWO)
        assert code == EXIT_LOGIC
        assert out["compared"] is False
        assert "corpus" in out["reason"]


class TestASplitCannotCarryACorpusThatIsNotOne:
    """Round sixteen: the pin comes off a caller-supplied file unvalidated."""

    def _gate_with_pin(self, tmp_path, capsys, pin):
        inc = _env_file(tmp_path, "inc.json", _CORPUS_ONE)
        _, split = _split(capsys, tmp_path, "--results", inc, "--seed", "bad-pin")
        split["corpus"] = pin
        split_path = _write(tmp_path, "split.json", split)
        return _run_gate(
            capsys, tmp_path, "--incumbent", inc, "--candidate", inc,
            "--split", split_path, cap=5,
        )

    @pytest.mark.parametrize("pin", [[], {}, 7, True, "nope", _CORPUS_ONE.upper()])
    def test_a_pin_that_is_not_a_digest_is_a_config_error(self, tmp_path, capsys, pin):
        code, out = self._gate_with_pin(tmp_path, capsys, pin)
        assert code == EXIT_CONFIG
        assert out["type"] == "ConfigError"
        assert "corpus" in out["error"]

    def test_an_unhashable_pin_does_not_reach_the_set(self, tmp_path, capsys):
        """A list pin used to raise `TypeError` out of the conflict rule."""
        code, out = self._gate_with_pin(tmp_path, capsys, [])
        assert code == EXIT_CONFIG
        assert out["type"] == "ConfigError"

    def test_a_null_pin_is_still_legal(self, tmp_path, capsys):
        code, out = self._gate_with_pin(tmp_path, capsys, None)
        assert code == EXIT_LOGIC
        assert out["decision"] == "REJECT"
        assert out["compared"] is False

    def test_a_real_digest_pin_is_accepted(self, tmp_path, capsys):
        code, out = self._gate_with_pin(tmp_path, capsys, _CORPUS_ONE)
        assert out.get("corpus_pinned") is True


class TestAParserFailureNeverPreemptsTheLedger:
    """Round sixteen: `_read_json` promised one exception family and had two."""

    def _deep(self, tmp_path, name):
        path = tmp_path / name
        path.write_text("[" * 200_000 + "]" * 200_000, encoding="utf-8")
        return path

    def test_deeply_nested_json_is_a_config_error_not_a_traceback(
        self, tmp_path, capsys
    ):
        inc = _write(tmp_path, "inc.json", {f"t{i}": True for i in range(10)})
        _, split = _split(capsys, tmp_path, "--results", inc, "--seed", "deep")
        split_path = _write(tmp_path, "split.json", split)
        code, out = _run_gate(
            capsys, tmp_path, "--incumbent", inc,
            "--candidate", self._deep(tmp_path, "cand.json"),
            "--split", split_path, cap=5,
        )
        assert code == EXIT_CONFIG
        assert out["type"] == "ConfigError"

    def test_an_exhausted_budget_still_answers_first(self, tmp_path, capsys):
        """The defect: a parse crash in the preflight outranked the ledger."""
        inc = _write(tmp_path, "inc.json", {f"t{i}": True for i in range(10)})
        _, split = _split(capsys, tmp_path, "--results", inc, "--seed", "deep2")
        split_path = _write(tmp_path, "split.json", split)
        _run_gate(
            capsys, tmp_path, "--incumbent", inc, "--candidate", inc,
            "--split", split_path, cap=1,
        )
        code, out = _run_gate(
            capsys, tmp_path, "--incumbent", inc,
            "--candidate", self._deep(tmp_path, "cand.json"),
            "--split", split_path, cap=1,
        )
        assert code == EXIT_LOGIC
        assert "consultation" in out["reason"]
        assert out["compared"] is False


class TestEveryWriteFailurePrintsOneJsonDocument:
    """Round seventeen: `mkstemp` sat outside the block that wraps `OSError`.

    `_write_atomic` carries two promises. The artifact is never left half
    written, and a failure prints one JSON document like every other failure
    the CLI reports. The temp file was created before the `try` that turns
    `OSError` into `ConfigError`, so a missing or unwritable parent escaped as
    a raw traceback and a caller parsing stdout as JSON crashed on it.
    """

    def _tasks(self, tmp_path, n: int = 30):
        path = tmp_path / "tasks.txt"
        path.write_text("\n".join(f"t{i}" for i in range(n)) + "\n", encoding="utf-8")
        return path

    def _split_into(self, tmp_path, capsys, out):
        return _run(
            capsys, "split", "--tasks", self._tasks(tmp_path), "--seed", "w", "--out", out
        )

    def test_a_missing_parent_directory_is_a_config_error(self, tmp_path, capsys):
        code, out = self._split_into(tmp_path, capsys, tmp_path / "absent" / "split.json")
        assert code == EXIT_CONFIG
        assert out["type"] == "ConfigError"

    def test_the_message_names_the_write_and_the_path(self, tmp_path, capsys):
        target = tmp_path / "absent" / "split.json"
        _, out = self._split_into(tmp_path, capsys, target)
        assert "could not write" in out["error"]
        assert str(target) in out["error"]

    def test_a_parent_that_refuses_the_temp_file_is_a_config_error(
        self, tmp_path, capsys, monkeypatch
    ):
        def _refuse(*_args, **_kwargs):
            raise OSError(13, "permission denied")

        monkeypatch.setattr(oa.tempfile, "mkstemp", _refuse)
        code, out = self._split_into(tmp_path, capsys, tmp_path / "split.json")
        assert code == EXIT_CONFIG
        assert out["type"] == "ConfigError"

    def test_a_non_io_failure_from_mkstemp_still_escapes(
        self, tmp_path, capsys, monkeypatch
    ):
        """Negative control: the new arm must not swallow unrelated failures."""

        def _boom(*_args, **_kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr(oa.tempfile, "mkstemp", _boom)
        with pytest.raises(RuntimeError, match="boom"):
            self._split_into(tmp_path, capsys, tmp_path / "split.json")

    def test_a_writable_parent_still_writes_the_split(self, tmp_path, capsys):
        """Positive control: the wrapping did not break the normal path."""
        target = tmp_path / "split.json"
        code, _ = self._split_into(tmp_path, capsys, target)
        assert code == EXIT_OK
        assert json.loads(target.read_text(encoding="utf-8"))["sel"]


class TestABinaryFileIsAConfigErrorWhereverItIsRead:
    """Round seventeen: `_read_json` let `UnicodeDecodeError` through by name.

    `_read_text` wraps it because it subclasses `ValueError` rather than
    `OSError`, so the `OSError` arm never caught it. `_read_json` reads text
    the same way and did not, so one reader called a binary artifact a config
    problem and the other reported the decoder's own class instead. The error
    document is part of the contract, so the two readers have to agree.
    """

    def _split_from(self, tmp_path, capsys, name, blob: bytes):
        path = tmp_path / name
        path.write_bytes(blob)
        return _run(
            capsys, "split", "--results", path, "--seed", "u", "--out", tmp_path / "o.json"
        )

    def test_invalid_utf8_is_a_config_error(self, tmp_path, capsys):
        code, out = self._split_from(tmp_path, capsys, "bad.json", b"\xff\xfe\x00{")
        assert code == EXIT_CONFIG
        assert out["type"] == "ConfigError"

    def test_the_message_names_utf8_the_way_the_text_reader_does(self, tmp_path, capsys):
        _, out = self._split_from(tmp_path, capsys, "bad.json", b"\xff\xfe\x00{")
        assert "is not valid UTF-8" in out["error"]

    def test_valid_utf8_that_is_not_json_still_reports_json(self, tmp_path, capsys):
        """Edge: the two failures are different and must stay distinguishable."""
        _, out = self._split_from(tmp_path, capsys, "bad.json", b"not json at all")
        assert out["type"] == "ConfigError"
        assert "is not valid JSON" in out["error"]

    def test_valid_utf8_json_still_parses(self, tmp_path, capsys):
        """Positive control."""
        blob = json.dumps({f"t{i}": True for i in range(30)}).encode("utf-8")
        code, _ = self._split_from(tmp_path, capsys, "good.json", blob)
        assert code == EXIT_OK


class TestBothCorpusChecksSpeakWithOneVoice:
    """Round seventeen: the recheck carried a key the preflight did not.

    `_corpus_refusal` says in its own docstring that two call sites phrasing
    the same refusal would let the caller tell which read caught it. The
    recheck then emitted `_corpus_refusal() | {"sel_consultations": spent}`,
    so the key set alone answered the question the docstring said it must not.
    Reporting the ledger there was also the wrong fact to add: `_guard` runs
    first, so budget is never exhausted by the time the recheck fires, and the
    only honest number both call sites share is that this run charged nothing.
    """

    def _pair(self, tmp_path, capsys):
        inc = _env_file(tmp_path, "inc.json", _CORPUS_ONE)
        cand = _env_file(tmp_path, "cand.json", _CORPUS_TWO)
        _, split = _split(capsys, tmp_path, "--results", inc, "--seed", "voice")
        split_path = _write(tmp_path, "split.json", split)
        return ("--incumbent", inc, "--candidate", cand, "--split", split_path)

    def _both(self, tmp_path, capsys, monkeypatch):
        argv = self._pair(tmp_path, capsys)
        _, early = _run_gate(capsys, tmp_path, *argv, cap=5)
        monkeypatch.setattr(oa, "_corpus_header", lambda _p: _CORPUS_ONE)
        _, late = _run_gate(capsys, tmp_path, *argv, cap=5)
        return early, late

    def test_the_two_refusals_are_one_document(self, tmp_path, capsys, monkeypatch):
        early, late = self._both(tmp_path, capsys, monkeypatch)
        assert early == late

    def test_neither_refusal_reports_the_ledger(self, tmp_path, capsys, monkeypatch):
        early, late = self._both(tmp_path, capsys, monkeypatch)
        assert "sel_consultations" not in early
        assert "sel_consultations" not in late

    def test_both_report_that_this_run_charged_nothing(
        self, tmp_path, capsys, monkeypatch
    ):
        early, late = self._both(tmp_path, capsys, monkeypatch)
        assert early["consultations"] == 0
        assert late["consultations"] == 0

    def test_the_patched_run_really_reaches_the_second_check(
        self, tmp_path, capsys, monkeypatch
    ):
        """Negative control: with an agreeing preflight the bodies must be read.

        Without this the comparison above could be two preflight refusals, and
        the identity it asserts would hold for a reason that proves nothing.
        """
        argv = self._pair(tmp_path, capsys)
        seen: list[Path] = []
        real = oa._read_results
        monkeypatch.setattr(oa, "_corpus_header", lambda _p: _CORPUS_ONE)
        monkeypatch.setattr(
            oa, "_read_results", lambda p: (seen.append(Path(p)), real(p))[1]
        )
        code, out = _run_gate(capsys, tmp_path, *argv, cap=5)
        assert len(seen) == 2
        assert code == EXIT_LOGIC
        assert out["compared"] is False


class TestEveryVerdictNamesWhatThisRunCharged:
    """Round nineteen: `consultations` was missing exactly where it was not zero.

    `_corpus_refusal` established the contract in its own docstring: the
    honest claim a refusal can make is that this run charged nothing, reported
    as `consultations: 0`. The charged paths never reported the other half.
    A caller reading `consultations` got 0 on every refusal and a missing key
    on every verdict, so the one field that answers "what did this cost me"
    was absent from the only outcomes with a nonzero answer.

    `sel_consultations` is the running total against the held-out group after
    this run's charge, which is why the guard refusal reports `spent` and the
    verdict reports `spent + 1`: nothing is charged before the guard. The
    ledger-mismatch refusal reported a literal 0, which is a running total it
    had no basis for. The count is parsed before the mismatch is raised, so
    the number exists, but on a key mismatch it belongs to a different group
    and naming it would leak that group's history through a refusal that
    deliberately withholds the group itself. Absence is the honest report.
    """

    def _pair(self, tmp_path, capsys, cand_all_true=True):
        inc = _write(tmp_path, "inc.json", {f"t{i}": i % 3 != 0 for i in range(12)})
        _, split = _split(capsys, tmp_path, "--results", inc, "--seed", "n19")
        split_path = _write(tmp_path, "split.json", split)
        cand = _write(tmp_path, "cand.json", {f"t{i}": cand_all_true for i in range(12)})
        return ("--incumbent", inc, "--candidate", cand, "--split", split_path)

    def test_a_charged_verdict_reports_one(self, tmp_path, capsys):
        argv = self._pair(tmp_path, capsys)
        _, out = _run_gate(capsys, tmp_path, *argv, cap=5)
        assert out["consultations"] == 1

    def test_a_charged_verdict_still_reports_the_running_total(self, tmp_path, capsys):
        """The running total includes this run's charge, so a first gate reads 1."""
        argv = self._pair(tmp_path, capsys)
        _, out = _run_gate(capsys, tmp_path, *argv, cap=5)
        assert out["sel_consultations"] == 1

    def test_the_two_counts_are_different_numbers_on_a_later_run(
        self, tmp_path, capsys
    ):
        """Edge: with prior spend the charge stays 1 while the total moves.

        Asserting both on a first run cannot distinguish them, because the
        charge and the total are both 1 there.
        """
        argv = self._pair(tmp_path, capsys)
        _, out = _run_gate(capsys, tmp_path, *argv, spent=3, cap=9)
        assert out["consultations"] == 1
        assert out["sel_consultations"] == 4

    def test_a_coverage_refusal_reports_the_charge_it_took(self, tmp_path, capsys):
        """The coverage refusal is charged, so it must not report zero."""
        inc = _write(tmp_path, "inc.json", {f"t{i}": True for i in range(12)})
        _, split = _split(capsys, tmp_path, "--results", inc, "--seed", "n19c")
        split_path = _write(tmp_path, "split.json", split)
        cand = _write(tmp_path, "cand.json", {"t0": True})
        code, out = _run_gate(
            capsys, tmp_path, "--incumbent", inc, "--candidate", cand,
            "--split", split_path, cap=5,
        )
        assert code == EXIT_LOGIC
        assert out["compared"] is False
        assert out["consultations"] == 1

    def test_a_guard_refusal_reports_no_charge(self, tmp_path, capsys):
        """Negative: an exhausted budget spends nothing, so the charge is zero."""
        argv = self._pair(tmp_path, capsys)
        code, out = _run_gate(capsys, tmp_path, *argv, spent=2, cap=2)
        assert code == EXIT_LOGIC
        assert out["consultations"] == 0
        assert out["sel_consultations"] == 2

    def test_a_ledger_mismatch_claims_no_running_total(self, tmp_path, capsys):
        """A cap it cannot honour is not a licence to report a total of zero."""
        argv = self._pair(tmp_path, capsys)
        _run_gate(capsys, tmp_path, *argv, spent=2, cap=9)
        code, out = _run_gate(capsys, tmp_path, *argv, cap=4)
        assert code == EXIT_LOGIC
        assert out["consultations"] == 0
        assert "sel_consultations" not in out

    def test_every_gate_outcome_names_the_charge(self, tmp_path, capsys):
        """One key set for the field that answers what this run cost.

        Four outcomes, reached by four different routes: a verdict, a charged
        coverage refusal, an uncharged guard refusal, and an uncharged drift
        refusal. Each is checked for the same key rather than for its own.
        """
        argv = self._pair(tmp_path, capsys)
        seen = [_run_gate(capsys, tmp_path, *argv, cap=5)[1]]
        seen.append(_run_gate(capsys, tmp_path, *argv, spent=2, cap=2)[1])

        drift_inc = _write(tmp_path, "d_inc.json", {f"t{i}": True for i in range(12)})
        _, split = _split(capsys, tmp_path, "--results", drift_inc, "--seed", "n19d")
        split["sel"] = list(split["sel"])[:-1]
        drift_split = _write(tmp_path, "d_split.json", split)
        drift_cand = _write(tmp_path, "d_cand.json", {f"t{i}": True for i in range(12)})
        seen.append(
            _run_gate(
                capsys, tmp_path, "--incumbent", drift_inc, "--candidate", drift_cand,
                "--split", drift_split, cap=5,
            )[1]
        )
        assert [out.get("consultations", "MISSING") for out in seen] == [1, 0, 0]


class TestAFailedCleanupDoesNotReplaceTheFailureItCleansUpAfter:
    """Round nineteen: the unlink in the handler could raise out of the handler.

    Round seventeen moved `mkstemp` inside the guarded block so a write
    failure printed one JSON document instead of a traceback. The cleanup
    itself stayed unguarded. An `OSError` from `tmp.unlink` inside the
    `except` arm propagates in place of the exception being handled, so the
    caller gets a traceback again, and it names the unlink rather than the
    write that actually failed. A parent whose permissions are revoked after
    `mkstemp` fails both calls, which is the pair that produces it.

    The comment in that handler also claimed the descriptor is closed when
    `os.fdopen` fails. It was not: nothing called `os.close`, so that path
    leaked a descriptor while the comment said it did not.
    """

    def _tasks(self, tmp_path):
        path = tmp_path / "tasks.txt"
        path.write_text("\n".join(f"t{i}" for i in range(30)) + "\n", encoding="utf-8")
        return path

    def _split_into(self, tmp_path, capsys, out):
        return _run(
            capsys, "split", "--tasks", self._tasks(tmp_path), "--seed", "n19", "--out", out
        )

    def _both_fail(self, monkeypatch):
        def _no_replace(*_args, **_kwargs):
            raise OSError(13, "replace denied")

        def _no_unlink(*_args, **_kwargs):
            raise OSError(13, "unlink denied")

        monkeypatch.setattr(oa.os, "replace", _no_replace)
        monkeypatch.setattr(oa.Path, "unlink", _no_unlink)

    def test_a_failed_cleanup_is_still_one_json_document(
        self, tmp_path, capsys, monkeypatch
    ):
        self._both_fail(monkeypatch)
        code, out = self._split_into(tmp_path, capsys, tmp_path / "split.json")
        assert code == EXIT_CONFIG
        assert out["type"] == "ConfigError"

    def test_the_message_names_the_write_not_the_cleanup(
        self, tmp_path, capsys, monkeypatch
    ):
        """The failure a caller must act on is the write, not the tidy-up."""
        self._both_fail(monkeypatch)
        _, out = self._split_into(tmp_path, capsys, tmp_path / "split.json")
        assert "replace denied" in out["error"]
        assert "unlink denied" not in out["error"]

    def test_a_cleanup_that_works_is_unchanged(self, tmp_path, capsys, monkeypatch):
        """Positive control: the ordinary failure path still reports the write."""

        def _no_replace(*_args, **_kwargs):
            raise OSError(13, "replace denied")

        monkeypatch.setattr(oa.os, "replace", _no_replace)
        code, out = self._split_into(tmp_path, capsys, tmp_path / "split.json")
        assert code == EXIT_CONFIG
        assert "replace denied" in out["error"]

    def test_a_non_io_cleanup_failure_still_escapes(
        self, tmp_path, capsys, monkeypatch
    ):
        """Negative control: the new arm must not swallow a real bug."""

        def _no_replace(*_args, **_kwargs):
            raise OSError(13, "replace denied")

        def _boom(*_args, **_kwargs):
            raise RuntimeError("cleanup boom")

        monkeypatch.setattr(oa.os, "replace", _no_replace)
        monkeypatch.setattr(oa.Path, "unlink", _boom)
        with pytest.raises(RuntimeError, match="cleanup boom"):
            self._split_into(tmp_path, capsys, tmp_path / "split.json")

    def test_a_descriptor_is_closed_when_fdopen_fails(
        self, tmp_path, capsys, monkeypatch
    ):
        """Edge: the one path where the with-block never takes the descriptor."""
        closed: list[int] = []
        real_close = oa.os.close

        def _no_fdopen(fd, *_args, **_kwargs):
            raise OSError(13, "fdopen denied")

        monkeypatch.setattr(oa.os, "fdopen", _no_fdopen)
        monkeypatch.setattr(
            oa.os, "close", lambda fd: (closed.append(fd), real_close(fd))[1]
        )
        code, _ = self._split_into(tmp_path, capsys, tmp_path / "split.json")
        assert code == EXIT_CONFIG
        assert closed


class TestTheLedgerRenameIsMadeDurableNotJustTheBytes:
    """Round nineteen: `fsync` on the file does not persist the rename.

    `_write_atomic` fsyncs the temporary file and then calls `os.replace`.
    The bytes are durable; the directory entry that points at them is not.
    A host that loses power after the gate reports a charged consultation can
    come back with the rename undone, which restores the previous ledger and
    hands the caller the consultation again. The whole point of charging
    before scoring is that a crash must not return a free look, so a charge
    that a crash can erase defeats the ordering it was written to protect.
    """

    def _dir_fsyncs(self, monkeypatch):
        kinds: list[bool] = []
        real = oa.os.fsync

        def _record(fd):
            kinds.append(stat.S_ISDIR(os.fstat(fd).st_mode))
            return real(fd)

        monkeypatch.setattr(oa.os, "fsync", _record)
        return kinds

    @pytest.mark.skipif(os.name == "nt", reason="Windows cannot open a directory fd")
    def test_the_parent_directory_is_fsynced(self, tmp_path, monkeypatch):
        kinds = self._dir_fsyncs(monkeypatch)
        oa._write_atomic(tmp_path / "ledger.json", "{}\n")
        assert any(kinds)

    @pytest.mark.skipif(os.name == "nt", reason="Windows cannot open a directory fd")
    def test_the_file_is_still_fsynced_too(self, tmp_path, monkeypatch):
        """Positive control: the directory fsync must not have replaced it."""
        kinds = self._dir_fsyncs(monkeypatch)
        oa._write_atomic(tmp_path / "ledger.json", "{}\n")
        assert not all(kinds)

    @pytest.mark.skipif(os.name == "nt", reason="Windows cannot open a directory fd")
    def test_the_directory_fsync_follows_the_rename(self, tmp_path, monkeypatch):
        """Edge: fsyncing the directory before the rename persists nothing."""
        order: list[str] = []
        real_fsync = oa.os.fsync
        real_replace = oa.os.replace

        def _fsync(fd):
            order.append("dir" if stat.S_ISDIR(os.fstat(fd).st_mode) else "file")
            return real_fsync(fd)

        def _replace(src, dst):
            order.append("replace")
            return real_replace(src, dst)

        monkeypatch.setattr(oa.os, "fsync", _fsync)
        monkeypatch.setattr(oa.os, "replace", _replace)
        oa._write_atomic(tmp_path / "ledger.json", "{}\n")
        assert order.index("dir") > order.index("replace")

    @pytest.mark.skipif(os.name == "nt", reason="Windows cannot open a directory fd")
    def test_a_directory_that_refuses_fsync_does_not_undo_the_write(
        self, tmp_path, capsys, monkeypatch
    ):
        """The bytes and the rename already landed, so the file must stay.

        Round twenty: the first version of this guard raised ConfigError here.
        That made a durability fix into an availability regression. os.replace
        was previously the last operation in the function, so every failure
        path preceded the rename and left the destination untouched. Adding a
        step after the rename created the first failure that can fire once the
        write has already succeeded, and in the ledger's case once a
        consultation has already been charged.
        """
        real = oa.os.fsync
        target = tmp_path / "ledger.json"
        target.write_text("{}\n", encoding="utf-8")

        def _refuse(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                raise OSError(13, "dir fsync denied")
            return real(fd)

        monkeypatch.setattr(oa.os, "fsync", _refuse)
        oa._write_atomic(target, '{"spent": 1}\n')
        assert target.read_text(encoding="utf-8") == '{"spent": 1}\n'

    @pytest.mark.skipif(os.name == "nt", reason="Windows cannot open a directory fd")
    def test_a_directory_that_refuses_fsync_does_not_abort_the_caller(
        self, tmp_path, capsys, monkeypatch
    ):
        """Negative: aborting after the charge costs a look and returns none.

        _write_atomic writes the ledger before the gate scores. Raising after
        os.replace succeeds means the consultation is spent and the caller
        gets an exception instead of a verdict, which is the one trade the
        charge-before-scoring order exists to avoid in the other direction.
        """
        real = oa.os.fsync

        def _refuse(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                raise OSError(13, "dir fsync denied")
            return real(fd)

        monkeypatch.setattr(oa.os, "fsync", _refuse)
        oa._write_atomic(tmp_path / "ledger.json", "{}\n")

    @pytest.mark.skipif(os.name == "nt", reason="Windows cannot open a directory fd")
    def test_the_lost_guarantee_is_reported_on_stderr(self, tmp_path, capsys, monkeypatch):
        """Not raising is not the same as not saying.

        Silently continuing would leave the caller believing a durability
        guarantee that did not hold, which is the shape this file keeps
        correcting. stderr is the right channel: the exit-code contract
        reserves stdout for the one JSON document a caller parses.
        """
        real = oa.os.fsync

        def _refuse(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                raise OSError(13, "dir fsync denied")
            return real(fd)

        monkeypatch.setattr(oa.os, "fsync", _refuse)
        oa._write_atomic(tmp_path / "ledger.json", "{}\n")
        captured = capsys.readouterr()
        assert "durab" in captured.err.lower()
        assert captured.out == ""

    @pytest.mark.skipif(os.name == "nt", reason="Windows cannot open a directory fd")
    def test_the_warning_does_not_claim_the_write_failed(self, tmp_path, capsys, monkeypatch):
        """Negative: the write succeeded, so saying otherwise is a false claim."""
        real = oa.os.fsync

        def _refuse(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                raise OSError(13, "dir fsync denied")
            return real(fd)

        monkeypatch.setattr(oa.os, "fsync", _refuse)
        oa._write_atomic(tmp_path / "ledger.json", "{}\n")
        assert "could not write" not in capsys.readouterr().err

    def test_a_file_fsync_failure_still_refuses(self, tmp_path, capsys, monkeypatch):
        """Control: before the rename nothing landed, so it is still an error.

        The distinction is what makes the change above a correction rather
        than a loosening. A failure that precedes os.replace leaves the
        destination untouched, so refusing is both honest and free.
        """

        def _refuse(fd):
            raise OSError(5, "file fsync denied")

        monkeypatch.setattr(oa.os, "fsync", _refuse)
        with pytest.raises(oa.ConfigError, match="could not write"):
            oa._write_atomic(tmp_path / "ledger.json", "{}\n")


class TestARefusalDoesNotAdviseAnInvocationTheParserRejects:
    """Round twenty: the budget refusal named a command that does not exist.

    The exhausted-budget message told the operator to "report on the test
    group". `score --group` accepts only "opt", and by design: the README
    lists "score --group opt refuses to read any other group" as a property
    the mechanism enforces whether or not the optimizer cooperates. Widening
    the choice to reach the test group would hand the loop unmetered reads of
    the one group held back as a final unbiased look, which is the opposite of
    what the advice was reaching for.

    So the advice is removed rather than implemented. The wording itself is
    asserted in tests/test_eval_optimizer_core.py, next to the function that
    produces it; what belongs here is the boundary that made the advice false.
    """

    def test_the_parser_still_refuses_the_group_the_message_named(self, capsys, tmp_path):
        """Control: the enforced boundary is unchanged by this fix."""
        with pytest.raises(SystemExit) as excinfo:
            oa.main(["score", "--kind", "rule", "--input", "x.json", "--group", "test"])
        assert excinfo.value.code == EXIT_CONFIG
        assert "invalid choice" in capsys.readouterr().err


class TestADiagnosticNeitherLeaksNorFails:
    """Round twenty-one: a warning is still a way out of the process.

    Round twenty stopped the directory-fsync failure from aborting a caller
    whose consultation was already charged, by printing instead of raising.
    That moved the failure rather than removing it. `print` itself raises when
    stderr is closed or broken, and `_write_atomic` converts any `OSError` from
    that region into a `ConfigError`, so the abort round twenty removed came
    straight back one layer down.

    The leak is the same shape. `_digest_scrubbed` is a seam over raised
    exceptions, and its own docstring gives the reason: "a wrapper covers the
    paths someone remembered; a seam covers the one added next year." A warning
    that prints and returns never reaches that seam, so the new diagnostic
    named a ledger directory in full, and `$EVAL_LEDGER_DIR` can carry the
    held-out digest. The tenth review already found and fixed exactly that at
    the lock-cleanup warning; this reintroduced it two rounds later at a site
    the seam does not cover.

    Both are one rule, and it was written down zero times: a diagnostic must
    not leak what raised diagnostics redact, and must not fail where the code
    it reports on already succeeded.
    """

    @staticmethod
    def _stderr_that_refuses(monkeypatch):
        class _Closed:
            def write(self, _text):
                raise OSError(32, "stderr closed")

            def flush(self):
                pass

        monkeypatch.setattr(oa.sys, "stderr", _Closed())

    @staticmethod
    def _fsync_refuses(monkeypatch):
        def _fsync(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                raise OSError(13, "dir fsync denied")
            return None

        monkeypatch.setattr(oa.os, "fsync", _fsync)

    @pytest.mark.skipif(os.name == "nt", reason="Windows cannot open a directory fd")
    def test_a_broken_stderr_does_not_abort_the_write_that_succeeded(
        self, tmp_path, monkeypatch
    ):
        """The exact regression round twenty fixed, one layer down."""
        self._fsync_refuses(monkeypatch)
        self._stderr_that_refuses(monkeypatch)
        oa._write_atomic(tmp_path / "ledger.json", '{"n": 1}\n')
        assert (tmp_path / "ledger.json").read_text(encoding="utf-8") == '{"n": 1}\n'

    @pytest.mark.skipif(os.name == "nt", reason="Windows cannot open a directory fd")
    def test_a_broken_stderr_is_not_reported_as_a_failed_write(
        self, tmp_path, monkeypatch
    ):
        """`_write_atomic` turns any OSError from that region into ConfigError."""
        self._fsync_refuses(monkeypatch)
        self._stderr_that_refuses(monkeypatch)
        oa._write_atomic(tmp_path / "ledger.json", "{}\n")

    @pytest.mark.skipif(os.name == "nt", reason="Windows cannot open a directory fd")
    def test_the_warning_withholds_a_digest_bearing_directory(
        self, tmp_path, capsys, monkeypatch
    ):
        """`$EVAL_LEDGER_DIR` can name the held-out digest; the tenth review
        found the lock warning printing one and fixed it there only."""
        key = "b" * 64
        root = tmp_path / f"ledger-{key}"
        root.mkdir()
        self._fsync_refuses(monkeypatch)
        with oa._digest_scrubbed(key):
            oa._write_atomic(root / "ledger.json", "{}\n")
        err = capsys.readouterr().err
        assert key not in err

    @pytest.mark.skipif(os.name == "nt", reason="Windows cannot open a directory fd")
    def test_the_withheld_digest_is_replaced_not_dropped(
        self, tmp_path, capsys, monkeypatch
    ):
        """An error naming nothing is a worse trade than the leak, so the
        placeholder must survive where the digest was."""
        key = "c" * 64
        root = tmp_path / f"ledger-{key}"
        root.mkdir()
        self._fsync_refuses(monkeypatch)
        with oa._digest_scrubbed(key):
            oa._write_atomic(root / "ledger.json", "{}\n")
        err = capsys.readouterr().err
        assert oa._HELD_OUT_PLACEHOLDER in err

    @pytest.mark.skipif(os.name == "nt", reason="Windows cannot open a directory fd")
    def test_an_uppercase_digest_is_withheld_too(self, tmp_path, capsys, monkeypatch):
        """Edge: the same case-folding the twelfth review had to add to `_scrub`."""
        key = "d" * 64
        root = tmp_path / f"ledger-{key.upper()}"
        root.mkdir()
        self._fsync_refuses(monkeypatch)
        with oa._digest_scrubbed(key):
            oa._write_atomic(root / "ledger.json", "{}\n")
        err = capsys.readouterr().err
        assert key.upper() not in err

    @pytest.mark.skipif(os.name == "nt", reason="Windows cannot open a directory fd")
    def test_the_warning_still_reaches_stderr_outside_a_scrub(
        self, tmp_path, capsys, monkeypatch
    ):
        """Positive control: withholding must not become silence."""
        self._fsync_refuses(monkeypatch)
        oa._write_atomic(tmp_path / "ledger.json", "{}\n")
        assert "durab" in capsys.readouterr().err.lower()

    @pytest.mark.skipif(os.name == "nt", reason="Windows cannot open a directory fd")
    def test_the_scrub_does_not_outlive_its_block(self, tmp_path, capsys, monkeypatch):
        """Negative control: a key left active would redact a later run's
        unrelated output, and hex is common enough in these paths to matter."""
        key = "e" * 64
        with oa._digest_scrubbed(key):
            pass
        root = tmp_path / f"dir-{key}"
        root.mkdir()
        self._fsync_refuses(monkeypatch)
        oa._write_atomic(root / "ledger.json", "{}\n")
        assert key in capsys.readouterr().err

    @pytest.mark.skipif(os.name == "nt", reason="Windows cannot open a directory fd")
    def test_the_scrub_is_cleared_when_its_block_raises(
        self, tmp_path, capsys, monkeypatch
    ):
        """Edge: the seam exists to catch exceptions, so the unwinding path is
        the one that must restore state, not the falling-off-the-end path."""
        key = "f" * 64
        with pytest.raises(oa.ConfigError):
            with oa._digest_scrubbed(key):
                raise OSError(5, "nothing to do with the digest")
        root = tmp_path / f"dir-{key}"
        root.mkdir()
        self._fsync_refuses(monkeypatch)
        oa._write_atomic(root / "ledger.json", "{}\n")
        assert key in capsys.readouterr().err

    @pytest.mark.skipif(os.name == "nt", reason="Windows cannot open a directory fd")
    def test_a_stream_closed_for_real_does_not_abort_the_write(self, tmp_path, monkeypatch):
        """A closed Python stream raises ValueError, not OSError.

        Round twenty-one demonstrated the crash with a double whose `write`
        raised `OSError(32)`, and the guard was written to the demonstration
        rather than to the class. A genuinely closed stream raises
        `ValueError: I/O operation on closed file`, which walks straight
        through an `OSError`-only suppression into the same abort.
        """
        stream = io.StringIO()
        stream.close()
        monkeypatch.setattr(sys, "stderr", stream)
        self._fsync_refuses(monkeypatch)
        oa._write_atomic(tmp_path / "ledger.json", '{"n": 1}\n')
        assert json.loads((tmp_path / "ledger.json").read_text()) == {"n": 1}

    @pytest.mark.skipif(os.name == "nt", reason="Windows cannot open a directory fd")
    def test_a_stderr_that_is_absent_is_treated_like_one_that_is_none(
        self, tmp_path, monkeypatch
    ):
        """Edge: `sys.stderr` can be missing, not only `None` or broken.

        The docstring claimed only the stream check sat outside the guard. The
        stream read sat outside it too, and `sys.stderr` is an attribute lookup
        that raises `AttributeError` when an embedding harness deletes it. That
        raise is the abort rounds twenty through twenty-three were each spent
        removing, arriving through the one expression none of them guarded.
        Reading it totally routes the missing case into the `None` branch that
        already existed, so the rule is enforced without a second one.
        """
        monkeypatch.delattr(sys, "stderr")
        self._fsync_refuses(monkeypatch)
        oa._write_atomic(tmp_path / "ledger.json", '{"n": 1}\n')
        assert json.loads((tmp_path / "ledger.json").read_text()) == {"n": 1}

    def test_the_key_read_outside_the_guard_cannot_raise(self):
        """The second unguarded read is total only because of a constructor arg.

        `_warn` reads the scrub key before entering the guard, so `get()` must
        not raise. It cannot, because the `ContextVar` carries `default=None`,
        and a `ContextVar` without one raises `LookupError` outside a set
        scope. That argument sits fifty lines from the read that depends on it,
        which is the distance that lets an edit look harmless. Dropping it
        turns thirteen diagnostic tests red without any of them naming the
        cause, so the invariant is asserted here where the name is the reason.
        """
        assert oa._ACTIVE_HOLDOUT_KEY.get() is None
        with pytest.raises(LookupError):
            ContextVar("_probe_without_default").get()

    @pytest.mark.skipif(os.name == "nt", reason="Windows cannot open a directory fd")
    def test_a_warning_never_lands_on_the_stream_carrying_the_verdict(
        self, tmp_path, capsys, monkeypatch
    ):
        """`print(file=None)` writes to stdout, and stdout carries the payload.

        `sys.stderr` is `None` under a pythonw-style launcher and after a
        harness detaches it. Passing that through as the `file` argument does
        not silence the warning, it redirects it onto the one stream whose
        every byte the caller parses as JSON.
        """
        monkeypatch.setattr(sys, "stderr", None)
        self._fsync_refuses(monkeypatch)
        oa._write_atomic(tmp_path / "ledger.json", "{}\n")
        assert capsys.readouterr().out == ""

    def test_the_lock_cleanup_warning_withholds_the_digest(
        self, tmp_path, capsys, monkeypatch
    ):
        """Negative: the leak claim said 'both sites' and tested one.

        Round twenty-one reported it had covered the leak and the crash at
        both warning sites. It had not; all eight tests drove `_write_atomic`.
        A twenty-second review read the tests rather than the prose.
        """
        monkeypatch.setattr(oa, "_ledger_root", lambda: tmp_path)
        key = "d" * 64

        def _refuse(self, **kwargs):
            raise OSError(13, f"cannot unlink {self}")

        with oa._ledger_held(key):
            monkeypatch.setattr(Path, "unlink", _refuse)
        monkeypatch.undo()
        err = capsys.readouterr().err
        assert key not in err
        assert oa._HELD_OUT_PLACEHOLDER in err

    @pytest.mark.skipif(os.name == "nt", reason="Windows cannot open a directory fd")
    def test_an_inner_scrub_restores_the_outer_key_and_not_none(
        self, tmp_path, capsys, monkeypatch
    ):
        """Edge: the claim was 'key restore under nesting', which had no test.

        `_ledger_held` scrubs for the whole lock lifecycle and the contention
        branch nests a second scrub inside it, so nesting is not hypothetical
        here. Clearing on the inner exit rather than restoring the outer key
        would unprotect the rest of the outer block, and every existing test
        would still pass because none of them nests.
        """
        outer = "a" * 64
        inner = "b" * 64
        with oa._digest_scrubbed(outer):
            with oa._digest_scrubbed(inner):
                pass
            root = tmp_path / f"dir-{outer}"
            root.mkdir()
            self._fsync_refuses(monkeypatch)
            oa._write_atomic(root / "ledger.json", "{}\n")
        err = capsys.readouterr().err
        assert outer not in err
        assert oa._HELD_OUT_PLACEHOLDER in err

    def test_a_redaction_that_raises_costs_the_message_and_not_the_caller(
        self, capsys, monkeypatch
    ):
        """Negative: the guard has to cover the redaction, not just the write.

        The first draft of the three-rule docstring asserted the opposite,
        that `_scrub` belonged outside the suppression so a broken redactor
        would fail loudly. Writing that sentence down is what disproved it. A
        redaction that raises leaves the message unprinted either way, because
        the exception skips the `print` with `message` still bound to its
        unscrubbed value. So excluding it buys no leak protection at all and
        costs the caller the abort that rounds twenty through twenty-two were
        spent removing.
        """
        key = "e" * 64

        def _explode(text, holdout_key):
            raise RuntimeError("redactor is broken")

        monkeypatch.setattr(oa, "_scrub", _explode)
        with oa._digest_scrubbed(key):
            oa._warn(f"cannot sync {key}")
        captured = capsys.readouterr()
        assert captured.err == ""
        assert key not in captured.out

    def test_a_scrub_set_in_another_context_cannot_overwrite_this_one(self):
        """Edge: two live scopes at once, which one shared global cannot hold.

        A twenty-second review ran two scopes concurrently against the module
        global this replaced and got a key disclosed under the wrong scope and
        a stale key left active after both had exited.

        No threads here, deliberately. The first draft of this test used two
        and passed against the very global it exists to rule out: the barrier
        releases both, but they still run one at a time, and the second thread
        finished its restore before the first resumed, so each read its own
        key by scheduling luck. A test that passes against the mutation is
        worth less than no test, because it also reports as covered.
        `copy_context` asks the same question with the scheduler removed.

        A twenty-third review pointed out that the first working version drove
        the `ContextVar` directly rather than this module's own scope, which
        tests the standard library instead of the seam. Its proposed repair,
        abandoning a generator mid-scope, does not discriminate as written:
        CPython drops the generator's last reference when the function
        returns, closes it, and runs the very `finally` the test needs left
        undone, so it passes against a module global too. Measured, not
        argued. Holding the reference is what abandons the scope for real.

        Closing it happens inside the same `Context` that opened it. Dropping
        the reference from out here instead leaves CPython to close the
        generator during collection, where `reset` is handed a token from a
        context it is no longer in, refuses it, and pytest reports the
        ignored exception as a warning. That is the limitation the `finally`
        in `_digest_scrubbed` discloses, reached from a test rather than from
        a call site.
        """
        outer = "a" * 64
        inner = "b" * 64
        abandoned = []

        def abandon_a_key_without_restoring_it():
            def never_finishes():
                with oa._digest_scrubbed(inner):
                    yield

            generator = never_finishes()
            abandoned.append(generator)
            next(generator)

        def close_what_was_abandoned():
            while abandoned:
                abandoned.pop().close()

        context = copy_context()
        try:
            with oa._digest_scrubbed(outer):
                context.run(abandon_a_key_without_restoring_it)
                assert oa._ACTIVE_HOLDOUT_KEY.get() == outer
            assert oa._ACTIVE_HOLDOUT_KEY.get() is None
        finally:
            context.run(close_what_was_abandoned)
