"""Tests for the live durable-outcome producer (issue #5768, REQ-042).

A fake process runner stands in for `claude`, so these tests prove argv shape,
environment, stream parsing, grading, and record assembly. They do not prove a
real claude process behaves as the canned streams do; the committed live run
under `evals/durable-outcome-live/` is that evidence.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from tests.eval._durable_live_test_support import (
    GOOD_TASK,
    PLAUSIBLE_TASK,
    Verdict,
    classify,
    compare,
    fake_runner,
    grader_mod,
    live_mod,
    load,
    parse_record,
    record_mod,
    stream_mod,
    stream_text,
)

SETTINGS = live_mod.RunSettings("haiku", "low", retry_budget=1)
BASE = {
    "harness": "claude",
    "context_bytes": 0,
    "retry_budget": 1,
    "reviewer": "none",
    "control": "current",
}


def _run(task: str, overlays: list[str | None], tmp_path: Path, **kwargs: Any) -> Any:
    scenario = load(task)
    control_file = tmp_path / "control.md"
    control_file.write_text("rules", encoding="utf-8")
    runner = fake_runner(scenario, overlays, **kwargs)
    budget = live_mod.InvocationBudget(10)
    run = live_mod.run_task(
        scenario, "current", control_file, BASE, SETTINGS, budget, runner=runner
    )
    return run, runner, budget


class TestParseStream:
    def test_success_stream_yields_facts(self) -> None:
        facts = stream_mod.parse_stream(stream_text(tools=("Edit", "Bash"), denials=2))
        assert facts.completed and facts.failure == ""
        assert facts.models == ("claude-haiku-4-5-20251001",)
        assert facts.cli_version == "2.1.285"
        assert (facts.input_tokens, facts.output_tokens) == (10, 20)
        assert (facts.cache_read_tokens, facts.cache_write_tokens) == (30, 40)
        assert facts.tool_calls == ("Edit", "Bash")
        assert facts.permission_denials == 2
        assert facts.cost_usd == pytest.approx(0.02)

    def test_missing_result_event_is_incomplete(self) -> None:
        facts = stream_mod.parse_stream(stream_text(with_result=False))
        assert not facts.completed
        assert facts.failure == "no result event in stream"
        assert facts.cost_usd == 0.0

    def test_error_result_is_a_failure(self) -> None:
        facts = stream_mod.parse_stream(
            stream_text(subtype="error_during_execution", is_error=True)
        )
        assert not facts.completed
        assert facts.failure == "error_during_execution"

    @pytest.mark.parametrize("subtype", ["error_max_turns", "error_max_budget_usd"])
    def test_turn_and_budget_limits_are_task_outcomes_not_failures(self, subtype: str) -> None:
        facts = stream_mod.parse_stream(stream_text(subtype=subtype, is_error=True))
        assert facts.completed and facts.failure == ""
        assert facts.limit_hit == subtype

    def test_non_success_subtype_without_is_error_is_a_failure(self) -> None:
        facts = stream_mod.parse_stream(stream_text(subtype="error_during_execution"))
        assert not facts.completed

    def test_tool_error_blocks_are_counted(self) -> None:
        assert stream_mod.parse_stream(stream_text(tool_error=True)).tool_errors == 1

    @pytest.mark.parametrize("text", ["", "\n\n", "not json\n{broken"])
    def test_garbage_and_empty_input_is_incomplete(self, text: str) -> None:
        facts = stream_mod.parse_stream(text)
        assert not facts.completed and facts.models == ()

    def test_non_object_json_lines_are_ignored(self) -> None:
        text = "[1, 2]\n" + stream_text()
        assert stream_mod.parse_stream(text).completed

    def test_bool_token_counts_are_not_ints(self) -> None:
        assert stream_mod._int(True) == 0
        assert stream_mod._int(7) == 7
        assert stream_mod._int("7") == 0

    def test_two_models_are_both_recorded_once(self) -> None:
        text = stream_text(model="a") + stream_text(model="a") + stream_text(model="b")
        assert stream_mod.parse_stream(text).models == ("a", "b")


class TestArgvAndEnv:
    def test_argv_pins_controls_and_tool_allowlist(self, tmp_path: Path) -> None:
        argv = live_mod.claude_argv(SETTINGS, tmp_path / "c.md", "do it")
        assert argv[:3] == ["claude", "-p", "do it"]
        assert argv[argv.index("--model") + 1] == "haiku"
        assert argv[argv.index("--effort") + 1] == "low"
        assert argv[argv.index("--setting-sources") + 1] == ""
        assert "--strict-mcp-config" in argv and "--no-session-persistence" in argv
        assert argv[argv.index("--append-system-prompt-file") + 1].endswith("c.md")
        assert "--dangerously-skip-permissions" not in argv
        assert "WebFetch" not in argv and "Bash(python:*)" in argv

    def test_env_drops_billing_variables_and_disables_claude_mds(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sentinel-not-a-key")
        monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "sentinel-not-a-token")
        monkeypatch.setenv("CLAUDE_CODE_USE_BEDROCK", "1")
        env = live_mod.claude_env()
        assert "ANTHROPIC_API_KEY" not in env and "ANTHROPIC_AUTH_TOKEN" not in env
        assert "CLAUDE_CODE_USE_BEDROCK" not in env
        assert env["CLAUDE_CODE_DISABLE_CLAUDE_MDS"] == "1"
        assert "HOME" in env


class TestControls:
    def test_current_is_larger_than_reduced_and_reduced_is_agents_md(self) -> None:
        root = Path(__file__).resolve().parents[2]
        current = live_mod.control_text(root, "current")
        reduced = live_mod.control_text(root, "reduced")
        assert reduced == (root / "AGENTS.md").read_text(encoding="utf-8")
        assert reduced in current and len(current) > 5 * len(reduced)

    def test_unknown_control_raises(self, tmp_path: Path) -> None:
        with pytest.raises(live_mod.LiveRunError, match="unknown control"):
            live_mod.control_text(tmp_path, "none")

    def test_missing_control_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(live_mod.LiveRunError, match="not found"):
            live_mod.control_text(tmp_path, "reduced")


class TestBudget:
    def test_spend_raises_at_the_cap_before_launching(self) -> None:
        budget = live_mod.InvocationBudget(2)
        budget.spend()
        budget.spend()
        with pytest.raises(live_mod.LiveRunError, match="cap 2"):
            budget.spend()
        assert budget.used == 2

    def test_upper_bound_counts_every_round(self) -> None:
        assert live_mod.max_invocations(6, 2, 1, 1) == 24
        assert live_mod.max_invocations(6, 2, 2, 0) == 24


class TestRunClaude:
    def test_missing_binary(self, tmp_path: Path) -> None:
        def runner(*_a: Any, **_k: Any) -> Any:
            raise FileNotFoundError

        code, out, detail = live_mod.run_claude(["claude"], tmp_path, runner=runner)
        assert (code, out, detail) == (None, "", "claude is not on PATH")

    def test_timeout(self, tmp_path: Path) -> None:
        def runner(*_a: Any, **_k: Any) -> Any:
            raise subprocess.TimeoutExpired("claude", 1)

        code, _, detail = live_mod.run_claude(["claude"], tmp_path, runner=runner, timeout=1)
        assert code is None and "timed out" in detail

    def test_os_error(self, tmp_path: Path) -> None:
        def runner(*_a: Any, **_k: Any) -> Any:
            raise PermissionError

        code, _, detail = live_mod.run_claude(["claude"], tmp_path, runner=runner)
        assert code is None and "PermissionError" in detail

    def test_nonzero_exit_is_reported(self, tmp_path: Path) -> None:
        def runner(argv: Any, **_k: Any) -> Any:
            return subprocess.CompletedProcess(argv, 3, "out", "")

        assert live_mod.run_claude(["claude"], tmp_path, runner=runner) == (3, "out", "exit code 3")

    def test_text_mode_and_stdin_are_pinned(self, tmp_path: Path) -> None:
        seen: dict[str, Any] = {}

        def runner(argv: Any, **kwargs: Any) -> Any:
            seen.update(kwargs)
            return subprocess.CompletedProcess(argv, 0, None, "")

        live_mod.run_claude(["claude"], tmp_path, runner=runner)
        assert seen["encoding"] == "utf-8" and seen["errors"] == "replace"
        assert seen["stdin"] == subprocess.DEVNULL and seen["check"] is False


class TestRunTask:
    def test_known_good_first_pass_is_accepted_durable(self, tmp_path: Path) -> None:
        run, runner, budget = _run(GOOD_TASK, ["known_good"], tmp_path)
        assert run.record is not None and len(runner.calls) == 1 and budget.used == 1
        assert classify(run.record) is Verdict.ACCEPTED_DURABLE
        assert run.record.execution.retries == 0
        assert run.record.config.model == "claude-haiku-4-5-20251001"
        assert run.record.config.harness_version == "2.1.285"

    def test_known_bad_exhausts_retries_and_is_rejected(self, tmp_path: Path) -> None:
        run, runner, _ = _run(GOOD_TASK, ["known_bad"], tmp_path)
        assert run.record is not None and len(runner.calls) == 2
        assert classify(run.record) is Verdict.REJECTED
        assert run.record.execution.first_pass.value == "FAIL"
        assert run.record.execution.retries == 1

    def test_untouched_initial_state_is_rejected_without_artifact(self, tmp_path: Path) -> None:
        run, _, _ = _run(GOOD_TASK, [None], tmp_path)
        assert run.record is not None
        assert run.record.capability.produced_artifact is False
        assert classify(run.record) is Verdict.REJECTED

    def test_correction_round_recovers_and_counts_a_retry(self, tmp_path: Path) -> None:
        run, runner, _ = _run(GOOD_TASK, ["known_bad", "known_good"], tmp_path)
        assert run.record is not None and len(runner.calls) == 2
        assert run.record.execution.first_pass.value == "FAIL"
        assert run.record.execution.deterministic_acceptance.value == "PASS"
        assert classify(run.record) is Verdict.ACCEPTED_DURABLE

    def test_plausible_but_wrong_is_caught_by_hidden_checks(self, tmp_path: Path) -> None:
        run, _, _ = _run(PLAUSIBLE_TASK, ["known_bad"], tmp_path)
        assert run.record is not None
        assert classify(run.record) is Verdict.REJECTED

    def test_turn_limit_is_graded_not_dropped(self, tmp_path: Path) -> None:
        run, _, _ = _run(
            GOOD_TASK,
            ["known_bad"],
            tmp_path,
            stdout=lambda _i: stream_text(subtype="error_max_turns", is_error=True),
        )
        assert run.record is not None
        assert classify(run.record) is Verdict.REJECTED
        assert all(i.facts.limit_hit == "error_max_turns" for i in run.invocations)

    def test_turn_limit_exit_code_1_is_graded_not_a_harness_failure(self, tmp_path: Path) -> None:
        run, _, _ = _run(
            GOOD_TASK,
            ["known_good"],
            tmp_path,
            stdout=lambda _i: stream_text(subtype="error_max_turns", is_error=True),
            returncodes=[1],
        )
        assert run.record is not None
        assert classify(run.record) is Verdict.ACCEPTED_DURABLE

    def test_nonzero_exit_with_a_success_result_is_still_a_harness_failure(
        self, tmp_path: Path
    ) -> None:
        run, _, _ = _run(GOOD_TASK, ["known_good"], tmp_path, returncodes=[2])
        assert run.record is None and run.note == "exit code 2"

    def test_harness_failure_yields_no_record(self, tmp_path: Path) -> None:
        run, runner, _ = _run(GOOD_TASK, ["known_good"], tmp_path, returncodes=[1])
        assert run.record is None and len(runner.calls) == 1
        assert run.note == "exit code 1"

    def test_incomplete_stream_yields_no_record(self, tmp_path: Path) -> None:
        run, _, _ = _run(
            GOOD_TASK, ["known_good"], tmp_path, stdout=lambda _i: stream_text(with_result=False)
        )
        assert run.record is None and run.note == "no result event in stream"

    def test_cost_and_unapproved_actions_are_summed_across_rounds(self, tmp_path: Path) -> None:
        run, _, _ = _run(
            GOOD_TASK,
            ["known_bad", "known_good"],
            tmp_path,
            stdout=lambda _i: stream_text(tools=("Edit", "WebFetch"), cost=0.05),
        )
        assert run.record is not None
        assert run.record.economics.model_cost_usd == pytest.approx(0.10)
        assert run.record.risk.unapproved_external_actions == 2

    def test_unsupported_claim_is_counted_only_when_acceptance_fails(self, tmp_path: Path) -> None:
        claim = "All tests pass."
        bad, _, _ = _run(
            GOOD_TASK, ["known_bad"], tmp_path, stdout=lambda _i: stream_text(text=claim)
        )
        good, _, _ = _run(
            GOOD_TASK, ["known_good"], tmp_path, stdout=lambda _i: stream_text(text=claim)
        )
        assert bad.record.risk.unsupported_claims == 1
        assert good.record.risk.unsupported_claims == 0

    def test_budget_exhaustion_raises_before_a_second_launch(self, tmp_path: Path) -> None:
        scenario = load(GOOD_TASK)
        control_file = tmp_path / "c.md"
        control_file.write_text("x", encoding="utf-8")
        runner = fake_runner(scenario, ["known_bad"])
        with pytest.raises(live_mod.LiveRunError):
            live_mod.run_task(
                scenario,
                "current",
                control_file,
                BASE,
                SETTINGS,
                live_mod.InvocationBudget(1),
                runner=runner,
            )
        assert len(runner.calls) == 1


class TestCorrectionPrompt:
    def test_prompt_names_scope_problems_and_never_hidden_output(self) -> None:
        scenario = load(GOOD_TASK)
        result = live_mod.GradeResult(
            live_mod.Verdict.FAIL,
            ("a.py",),
            ("other.py",),
            ("slugger/core.py",),
            (grader_mod.CommandResult(("python",), 1, False, "AssertionError: HIDDEN-SENTINEL"),),
        )
        prompt = live_mod.correction_prompt(scenario, result)
        assert "other.py" in prompt and "slugger/core.py" in prompt
        assert "HIDDEN-SENTINEL" not in prompt and "AssertionError" not in prompt


class TestRecordHelpers:
    def test_record_to_row_roundtrips_through_the_strict_parser(self, tmp_path: Path) -> None:
        run, _, _ = _run(GOOD_TASK, ["known_good"], tmp_path)
        row = record_mod.record_to_row(run.record)
        assert parse_record(row) == run.record
        assert row["execution"]["deterministic_acceptance"] == "PASS"

    def test_followup_grade_matches_a_direct_grade_for_good_and_bad(self, tmp_path: Path) -> None:
        scenario = load(GOOD_TASK)
        for overlay, expected in (("known_good", "PASS"), ("known_bad", "FAIL")):
            workdir = tmp_path / overlay
            live_mod.materialize(scenario, workdir, overlay)
            direct = live_mod.grade(scenario, workdir)
            follow = record_mod.followup_grade(scenario, workdir, direct.changed_paths)
            assert direct.verdict.value == follow.verdict.value == expected

    def test_followup_removes_a_file_the_agent_deleted(self, tmp_path: Path) -> None:
        scenario = load(GOOD_TASK)
        workdir = tmp_path / "w"
        live_mod.materialize(scenario, workdir, "known_good")
        victim = workdir / "slugger" / "__init__.py"
        victim.unlink()
        follow = record_mod.followup_grade(scenario, workdir, ("slugger/__init__.py",))
        assert follow.verdict.value == "FAIL"

    def test_security_findings_counts_ruff_s_rules(self, tmp_path: Path) -> None:
        (tmp_path / "bad.py").write_text(
            "import subprocess\nsubprocess.call('ls', shell=True)\n", encoding="utf-8"
        )
        (tmp_path / "ok.py").write_text("x = 1\n", encoding="utf-8")
        assert record_mod.security_findings(tmp_path, ["bad.py"]) >= 1
        assert record_mod.security_findings(tmp_path, ["ok.py"]) == 0
        assert record_mod.security_findings(tmp_path, ["notes.md", "gone.py"]) == 0

    def test_security_findings_is_none_when_ruff_cannot_run(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")

        def boom(*_a: Any, **_k: Any) -> Any:
            raise OSError

        monkeypatch.setattr(record_mod.subprocess, "run", boom)
        assert record_mod.security_findings(tmp_path, ["a.py"]) is None

    def test_a_null_security_count_makes_the_record_unverified(self, tmp_path: Path) -> None:
        run, _, _ = _run(GOOD_TASK, ["known_good"], tmp_path)
        row = record_mod.record_to_row(run.record)
        row["risk"]["security_findings"] = None
        assert classify(parse_record(row)) is Verdict.UNVERIFIED

    def test_unapproved_actions_never_goes_negative(self) -> None:
        facts = stream_mod.parse_stream(stream_text(tools=("Edit",), denials=3))
        inv = stream_mod.Invocation("c", "t", 0, 0, 1.0, facts)
        assert record_mod.unapproved_actions([inv]) == 0


class TestExperiment:
    def test_two_controls_yield_matched_records_and_a_comparison(self, tmp_path: Path) -> None:
        scenario = load(GOOD_TASK)
        runner = fake_runner(scenario, ["known_good"])
        result = live_mod.run_experiment(
            [scenario],
            {"current": "a", "reduced": "b"},
            SETTINGS,
            live_mod.InvocationBudget(10),
            runner=runner,
        )
        assert set(result.records) == {"current", "reduced"}
        assert result.harness_failures == ()
        assert len(result.invocations) == 2
        comparison = compare(result.records["current"], result.records["reduced"])
        assert comparison["result"] in {"BETTER", "MIXED", "WORSE", "UNVERIFIED"}

    def test_harness_failure_is_listed_and_the_task_has_no_record(self) -> None:
        scenario = load(GOOD_TASK)
        runner = fake_runner(scenario, ["known_good"], returncodes=[1])
        result = live_mod.run_experiment(
            [scenario],
            {"current": "a"},
            SETTINGS,
            live_mod.InvocationBudget(10),
            runner=runner,
        )
        assert result.records["current"] == ()
        assert result.harness_failures == (("current", GOOD_TASK, "exit code 1"),)
