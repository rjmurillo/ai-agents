"""Selected-scenario runs and the harness arms of eval-rule-activation.py (#6737).

The first S7 run needed a scratch driver because the CLI could not pick one
scenario, repeat it, or restrict the arms. These tests pin the flags that
replace it, the call plan a dry run prints, the record a live run writes, and
the skill-routed arm's wiring. No model is called.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from tests.eval.test_eval_rule_activation import eval_mod

REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC_SCENARIOS = REPO_ROOT / "tests" / "evals" / "skill-scenarios" / "spec.json"
HARNESS = sys.modules["_claude_skill_harness"]


def _args(**overrides: Any) -> argparse.Namespace:
    values: dict[str, Any] = {
        "scenarios": [str(SPEC_SCENARIOS)],
        "scenario_id": "S7",
        "repeats": 1,
        "arms": None,
        "model": "claude-sonnet-5",
        "seed": 0,
        "dry_run": False,
        "judge_repeats": 1,
        "judge_reducer": "median",
        "output": None,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def _run_main(monkeypatch: pytest.MonkeyPatch, *argv: str) -> int:
    monkeypatch.setattr(sys, "argv", ["eval-rule-activation.py", *argv])
    return int(eval_mod.main())


def _judge(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
    return {"activation_score": 4, "citation_score": 4, "behavior_score": 4, "judge_failed": False}


class _FakeReply:
    def __init__(self, text: str, invocation: str | None) -> None:
        self.text = text
        self.model = "claude-sonnet-5"
        self.input_tokens_total = 9000 if invocation else 5000
        self.output_tokens = 40
        self.cli_version = "2.1.307"
        self.tool_calls = ()
        self.invocation = invocation
        self.credential_step = "env"


@pytest.fixture
def harness_calls(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def fake_run(text: str, **kwargs: Any) -> Any:
        calls.append({"text": text, **kwargs})
        name = kwargs["skill_name"]
        return _FakeReply(f"answer {len(calls)}", None if name is None else f"/{name}")

    monkeypatch.setattr(HARNESS, "run_harness", fake_run)
    monkeypatch.setattr(eval_mod, "score_response", _judge)
    monkeypatch.setattr(eval_mod, "RATE_LIMIT_SLEEP_SEC", 0)
    monkeypatch.setenv("EVAL_PROVIDER", "claude-cli")
    return calls


class TestSelectionError:
    def test_no_selection_is_allowed(self) -> None:
        assert eval_mod._selection_error(_args(scenario_id=None)) is None

    @pytest.mark.parametrize(
        "overrides",
        [{"repeats": 3}, {"arms": ["baseline"]}],
    )
    def test_repeats_and_arms_need_a_scenario(self, overrides: dict[str, Any]) -> None:
        error = eval_mod._selection_error(_args(scenario_id=None, **overrides))
        assert error == "--repeats and --arms need --scenario-id"

    def test_needs_exactly_one_file(self) -> None:
        error = eval_mod._selection_error(_args(scenarios=[str(SPEC_SCENARIOS)] * 2))
        assert error == "--scenario-id needs exactly one --scenarios file"

    @pytest.mark.parametrize("repeats", [0, -1])
    def test_repeats_must_be_positive(self, repeats: int) -> None:
        assert eval_mod._selection_error(_args(repeats=repeats)) == "--repeats must be positive"

    def test_blank_scenario_id_is_refused(self) -> None:
        assert "non-empty" in str(eval_mod._selection_error(_args(scenario_id="  ")))

    def test_an_arm_named_twice_is_refused(self) -> None:
        error = eval_mod._selection_error(_args(arms=["baseline", "baseline"]))
        assert error == "--arms names an arm twice"

    def test_harness_arms_need_the_claude_cli_transport(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("EVAL_PROVIDER", raising=False)
        error = eval_mod._selection_error(_args(arms=["harness-baseline", "skill-routed"]))
        assert "EVAL_PROVIDER must be claude-cli" in str(error)
        monkeypatch.setenv("EVAL_PROVIDER", "claude-cli")
        assert eval_mod._selection_error(_args(arms=["harness-baseline", "skill-routed"])) is None

    def test_text_arms_run_on_any_transport(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("EVAL_PROVIDER", raising=False)
        assert eval_mod._selection_error(_args(arms=["baseline", "full"])) is None


class TestDryRunPlan:
    def test_plan_counts_only_the_selected_cells(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("EVAL_PROVIDER", "claude-cli")
        code = _run_main(
            monkeypatch,
            "--scenarios",
            str(SPEC_SCENARIOS),
            "--scenario-id",
            "S7",
            "--repeats",
            "12",
            "--arms",
            "harness-baseline",
            "skill-routed",
            "--judge-repeats",
            "1",
            "--dry-run",
        )
        out = capsys.readouterr().out
        assert code == 0
        assert "12 repeats x 2 arms (harness-baseline, skill-routed)" in out
        assert "= 48 calls" in out
        assert "Total calls planned: 48" in out

    def test_default_arms_are_the_gate_mechanisms(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = _run_main(
            monkeypatch,
            "--scenarios",
            str(SPEC_SCENARIOS),
            "--scenario-id",
            "S7",
            "--dry-run",
        )
        assert code == 0
        assert "1 repeats x 3 arms (baseline, description, full)" in capsys.readouterr().out

    def test_unknown_scenario_id_is_a_config_error(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = _run_main(
            monkeypatch, "--scenarios", str(SPEC_SCENARIOS), "--scenario-id", "S99", "--dry-run"
        )
        assert code == 2
        assert "matches 0 scenarios" in capsys.readouterr().err

    def test_unknown_arm_is_refused_by_the_parser(self, monkeypatch: pytest.MonkeyPatch) -> None:
        with pytest.raises(SystemExit) as raised:
            _run_main(
                monkeypatch,
                "--scenarios",
                str(SPEC_SCENARIOS),
                "--scenario-id",
                "S7",
                "--arms",
                "control",
                "--dry-run",
            )
        assert raised.value.code == 2

    def test_selection_still_requires_both_pools_in_the_file(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # The pool check reads the file, not the selection, and costs no call.
        data = json.loads(SPEC_SCENARIOS.read_text(encoding="utf-8"))
        data["scenarios"] = [s for s in data["scenarios"] if s["id"] == "S7"]
        lone = tmp_path / "lone.json"
        lone.write_text(json.dumps(data), encoding="utf-8")
        code = _run_main(monkeypatch, "--scenarios", str(lone), "--scenario-id", "S7", "--dry-run")
        assert code == 2
        assert "declares no negative scenario" in capsys.readouterr().err


class TestHarnessTarget:
    def test_skill_target_yields_dir_and_frontmatter_name(self) -> None:
        skill = REPO_ROOT / ".claude" / "skills" / "spec" / "SKILL.md"
        fields = eval_mod._harness_target(skill, eval_mod.parse_rule(skill))
        assert fields == {"harness_skill_dir": str(skill.parent), "harness_skill_name": "spec"}

    def test_rule_target_is_refused(self, capsys: pytest.CaptureFixture[str]) -> None:
        rule = REPO_ROOT / ".claude" / "rules" / "voice.md"
        assert eval_mod._harness_target(rule, eval_mod.parse_rule(rule)) == 2
        assert "needs a skill_path target" in capsys.readouterr().err

    def test_reference_target_is_refused(self, capsys: pytest.CaptureFixture[str]) -> None:
        skill = REPO_ROOT / ".claude" / "skills" / "spec" / "SKILL.md"
        reference = skill.parent / "references" / "step-0-5-memory-gate.md"
        assert eval_mod._harness_target(skill, eval_mod.parse_rule(skill), reference) == 2
        assert "no reference_path" in capsys.readouterr().err

    def test_quoted_frontmatter_name_is_accepted(self, tmp_path: Path) -> None:
        skill = tmp_path / "x" / "SKILL.md"
        rule = {"frontmatter": 'name: "demo"', "description": "", "body": ""}
        fields = eval_mod._harness_target(skill, rule)
        assert fields == {"harness_skill_dir": str(skill.parent), "harness_skill_name": "demo"}

    def test_a_name_that_is_not_a_slash_command_is_refused(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        skill = tmp_path / "x" / "SKILL.md"
        rule = {"frontmatter": "name: Bad Name", "description": "", "body": ""}
        assert eval_mod._harness_target(skill, rule) == 2
        assert "not a slash command name" in capsys.readouterr().err


class TestSelectedRun:
    def test_pairs_each_repeat_and_keeps_whole_responses(
        self, harness_calls: list[dict[str, Any]]
    ) -> None:
        loaded = eval_mod._load_scenarios_file(str(SPEC_SCENARIOS))
        assert not isinstance(loaded, int)
        data, paths = loaded
        args = _args(repeats=3, arms=["harness-baseline", "skill-routed"])

        rule_id, result, n_calls = eval_mod._process_selected_scenario("", data, paths, args)

        assert rule_id == "spec"
        assert n_calls == 12
        assert result["selection"] == {
            "scenario_id": "S7",
            "repeats": 3,
            "arms": ["harness-baseline", "skill-routed"],
        }
        assert [r["repeat"] for r in result["repeats"]] == [1, 2, 3]
        s7 = next(s for s in data["scenarios"] if s["id"] == "S7")
        assert [c["text"] for c in harness_calls] == [s7["input"]] * 6
        assert [c["skill_name"] for c in harness_calls] == [None, "spec"] * 3
        routed = result["repeats"][0]["mechanisms"]["skill-routed"]
        control = result["repeats"][0]["mechanisms"]["harness-baseline"]
        assert routed["response"] == "answer 2"
        assert routed["harness"]["invocation"] == "/spec"
        assert routed["harness"]["input_tokens_total"] == 9000
        assert control["harness"]["skill_installed"] is None
        assert control["system_fingerprint"] == "claude-sonnet-5"
        assert routed["output_tokens"] == 40
        summary = result["summary"]
        assert summary["verdict"] == "NOT_GATED"
        assert summary["per_arm"]["skill-routed"]["graded_count"] == 3
        assert summary["per_arm"]["skill-routed"]["avg_score"] == 4.0

    def test_a_failed_cell_marks_the_run_incomplete_and_exits_external(
        self,
        harness_calls: list[dict[str, Any]],
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        real = HARNESS.run_harness

        def flaky(text: str, **kwargs: Any) -> Any:
            if kwargs["skill_name"] is not None and len(harness_calls) == 1:
                harness_calls.append({"text": text, **kwargs})
                raise RuntimeError("Claude CLI exited with code 1")
            return real(text, **kwargs)

        monkeypatch.setattr(HARNESS, "run_harness", flaky)
        out = tmp_path / "out.json"
        code = _run_main(
            monkeypatch,
            "--scenarios",
            str(SPEC_SCENARIOS),
            "--scenario-id",
            "S7",
            "--repeats",
            "2",
            "--arms",
            "harness-baseline",
            "skill-routed",
            "--judge-repeats",
            "1",
            "--output",
            str(out),
        )
        record = json.loads(out.read_text(encoding="utf-8"))["rules"]["spec"]
        first = record["repeats"][0]["mechanisms"]["skill-routed"]
        assert code == 3
        assert "exited with code 1" in first["error"]
        assert record["summary"]["verdict"] == "NOT_GATED_INCOMPLETE"
        assert record["summary"]["per_arm"]["skill-routed"]["graded_count"] == 1

    def test_text_arms_still_use_the_api_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        sent: list[str] = []

        def fake_api(*_a: Any, system: str = "", **_k: Any) -> str:
            sent.append(system)
            return "text answer"

        monkeypatch.setattr(eval_mod, "_call_api", fake_api)
        monkeypatch.setattr(eval_mod, "score_response", _judge)
        monkeypatch.setattr(eval_mod, "RATE_LIMIT_SLEEP_SEC", 0)
        loaded = eval_mod._load_scenarios_file(str(SPEC_SCENARIOS))
        assert not isinstance(loaded, int)
        data, paths = loaded

        _, result, n_calls = eval_mod._process_selected_scenario(
            "", data, paths, _args(arms=["baseline", "full"])
        )

        assert n_calls == 4
        assert sent[0] == ""
        assert "The following project rule applies" in sent[1]
        assert set(result["repeats"][0]["mechanisms"]) == {"baseline", "full"}


class TestEvalOneScenarioArms:
    def test_default_arms_are_unchanged(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(eval_mod, "_call_api", lambda *a, **k: "r")
        monkeypatch.setattr(eval_mod, "score_response", _judge)
        monkeypatch.setattr(eval_mod, "RATE_LIMIT_SLEEP_SEC", 0)
        scenario = {"id": "S1", "input": "x", "expected_gate": "g"}
        result = eval_mod.eval_one_scenario(
            "", {"description": "d", "body": "b"}, "r", scenario, "m", dry_run=False
        )
        assert tuple(result["mechanisms"]) == eval_mod.MECHANISMS
        assert "response" not in result["mechanisms"]["full"]

    def test_classify_verdict_for_selected_runs(self) -> None:
        assert eval_mod._classify_verdict("NOT_GATED") == 0
        assert eval_mod._classify_verdict("NOT_GATED_INCOMPLETE") == 3


class TestReviewFixes:
    def test_declined_cell_does_not_make_the_run_incomplete(self) -> None:
        repeats = [
            {
                "id": "S1",
                "negative_case": False,
                "mechanisms": {"description": eval_mod._declined_cell("")},
            }
        ]
        summary = eval_mod._selected_summary(repeats, ("description",))
        assert summary["verdict"] == "NOT_GATED"
        assert summary["per_arm"]["description"]["declined_count"] == 1

    def test_errored_cell_still_makes_the_run_incomplete(self) -> None:
        repeats = [
            {
                "id": "S1",
                "negative_case": False,
                "mechanisms": {"baseline": {"error": "boom", "scores": {}}},
            }
        ]
        assert eval_mod._selected_summary(repeats, ("baseline",))["verdict"] == (
            "NOT_GATED_INCOMPLETE"
        )

    def test_harness_arms_read_the_cli_overrides(
        self, harness_calls: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CLAUDE_CLI_BIN", "/opt/claude/bin/claude")
        monkeypatch.setenv("CLAUDE_CLI_TIMEOUT", "1800")
        loaded = eval_mod._load_scenarios_file(str(SPEC_SCENARIOS))
        assert not isinstance(loaded, int)
        data, paths = loaded
        eval_mod._process_selected_scenario("", data, paths, _args(arms=["harness-baseline"]))
        assert harness_calls[0]["executable"] == "/opt/claude/bin/claude"
        assert harness_calls[0]["timeout"] == 1800.0

    def test_each_repeat_gets_its_own_seed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        seeds: list[int | None] = []

        def fake_api(*_a: Any, seed: int | None = None, **_k: Any) -> str:
            seeds.append(seed)
            return "r"

        monkeypatch.setattr(eval_mod, "_call_api", fake_api)
        monkeypatch.setattr(eval_mod, "score_response", _judge)
        monkeypatch.setattr(eval_mod, "RATE_LIMIT_SLEEP_SEC", 0)
        loaded = eval_mod._load_scenarios_file(str(SPEC_SCENARIOS))
        assert not isinstance(loaded, int)
        data, paths = loaded
        eval_mod._process_selected_scenario(
            "", data, paths, _args(arms=["baseline"], repeats=3, seed=42)
        )
        assert seeds == [42, 44, 46]

    def test_missing_harness_usage_publishes_no_token_count(
        self, monkeypatch: pytest.MonkeyPatch, harness_calls: list[dict[str, Any]]
    ) -> None:
        def no_usage(text: str, **kwargs: Any) -> Any:
            reply = _FakeReply("a", None)
            reply.output_tokens = None  # type: ignore[assignment]
            reply.input_tokens_total = None  # type: ignore[assignment]
            return reply

        monkeypatch.setattr(HARNESS, "run_harness", no_usage)
        loaded = eval_mod._load_scenarios_file(str(SPEC_SCENARIOS))
        assert not isinstance(loaded, int)
        data, paths = loaded
        _, result, _ = eval_mod._process_selected_scenario(
            "", data, paths, _args(arms=["harness-baseline"])
        )
        cell = result["repeats"][0]["mechanisms"]["harness-baseline"]
        assert "output_tokens" not in cell
        assert cell["harness"]["input_tokens_total"] is None
