"""Tests for the Codex harness adapter of the durable-outcome driver (issue #5768).

A fake process runner stands in for `codex`. These tests prove argv shape,
environment isolation, output parsing, grading, and record assembly. They do
not prove a real codex process behaves as the canned streams do; the committed
live run under `evals/durable-outcome-live/` is that evidence.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from tests.eval._durable_live_test_support import (
    GOOD_TASK,
    PLAUSIBLE_TASK,
    Verdict,
    classify,
    cli,
    codex_mod,
    fake_runner,
    live_mod,
    load,
)


def live_mod_path() -> Path:
    return Path(__file__).resolve().parents[2] / "scripts" / "eval"


FRAME = "2026-10-03T13:40:20.686016Z TRACE tungstenite::protocol: Received message "


def _frame(kind: str, response_id: str, model: str, effort: str | None) -> str:
    reasoning = {"effort": effort} if effort else {}
    body = {
        "type": kind,
        "response": {"id": response_id, "model": model, "reasoning": reasoning},
    }
    return FRAME + json.dumps(body)


def _stderr(model: str = "gpt-5.6-luna", effort: str | None = "low") -> str:
    return "\n".join(
        [
            "Reading additional input from stdin...",
            _frame("response.created", "r1", model, effort),
            _frame("response.completed", "r1", model, effort),
            FRAME + "Binary Data<length=4>",
        ]
    )


def _stdout(
    *,
    items: Sequence[dict[str, Any]] = (),
    text: str = "Done.",
    usage: dict[str, int] | None = None,
    terminal: dict[str, Any] | None = None,
) -> str:
    counts = usage or {"input_tokens": 1000, "cached_input_tokens": 400, "output_tokens": 50}
    events: list[dict[str, Any]] = [{"type": "thread.started"}, {"type": "turn.started"}]
    events += [{"type": "item.completed", "item": item} for item in items]
    events.append({"type": "item.completed", "item": {"type": "agent_message", "text": text}})
    events.append(terminal or {"type": "turn.completed", "usage": counts})
    return "".join(json.dumps(event) + "\n" for event in events)


SETTINGS = live_mod.RunSettings("gpt-5.6-luna", "low", retry_budget=1, harness="codex")
BASE = {
    "harness": "codex",
    "context_bytes": 0,
    "retry_budget": 1,
    "reviewer": "none",
    "control": "current",
}


class TestArgv:
    def test_argv_pins_model_effort_sandbox_and_control(self) -> None:
        argv = codex_mod.codex_argv("gpt-5.6-luna", "low", 'rules "x"\nline', "do it")
        assert argv[:3] == ["codex", "exec", "--json"]
        assert argv[argv.index("-m") + 1] == "gpt-5.6-luna"
        assert "model_reasoning_effort=low" in argv
        assert argv[argv.index("-s") + 1] == "workspace-write"
        for flag in ("--ignore-user-config", "--ignore-rules", "--ephemeral"):
            assert flag in argv
        assert argv[-2:] == ["--", "do it"]

    def test_a_prompt_that_looks_like_a_flag_stays_positional(self) -> None:
        argv = codex_mod.codex_argv("m", "low", "t", "-s danger-full-access")
        assert argv[-2:] == ["--", "-s danger-full-access"]
        assert argv.index("--") > argv.index("workspace-write")
        assert "danger-full-access" not in argv[: argv.index("--")]

    def test_del_is_escaped_so_toml_accepts_the_control_text(self) -> None:
        argv = codex_mod.codex_argv("m", "low", "a\x7fb", "p")
        value = next(a for a in argv if a.startswith("developer_instructions="))
        assert "\x7f" not in value and "\\u007f" in value

    def test_control_text_is_a_toml_string_that_round_trips(self) -> None:
        text = 'quote " backslash \\ newline\n tab\t unicode é'
        argv = codex_mod.codex_argv("m", "low", text, "p")
        value = next(a for a in argv if a.startswith("developer_instructions="))
        decoded = json.loads(value.removeprefix("developer_instructions="))
        assert decoded == text

    def test_no_dangerous_flags(self) -> None:
        argv = codex_mod.codex_argv("m", "low", "t", "p")
        assert "danger-full-access" not in argv
        assert "--dangerously-bypass-approvals-and-sandbox" not in argv


class TestEnv:
    def test_env_drops_billing_variables_and_enables_frame_logging(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sentinel-not-a-key")
        monkeypatch.setenv("CODEX_API_KEY", "sentinel-not-a-key")
        monkeypatch.setenv("OPENAI_BASE_URL", "https://example.invalid")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sentinel-not-a-key")
        env = codex_mod.codex_env()
        for name in ("OPENAI_API_KEY", "CODEX_API_KEY", "OPENAI_BASE_URL", "ANTHROPIC_API_KEY"):
            assert name not in env
        assert env["RUST_LOG"] == codex_mod.CODEX_RUST_LOG
        assert "HOME" in env

    def test_codex_home_passes_through_unchanged(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CODEX_HOME", "/operator/codex-home")
        assert codex_mod.codex_env()["CODEX_HOME"] == "/operator/codex-home"
        monkeypatch.delenv("CODEX_HOME")
        assert "CODEX_HOME" not in codex_mod.codex_env()


class TestNoCredentialAccess:
    """The driver must never link to, copy, or read a credential file."""

    FILES = ("_durable_codex.py", "_durable_live.py", "eval_durable_live.py")

    @pytest.mark.parametrize("name", FILES)
    def test_source_names_no_credential_path_or_link_call(self, name: str) -> None:
        text = (live_mod_path() / name).read_text(encoding="utf-8")
        for token in ("symlink", "auth.json", ".credentials.json", "shutil.copy", "copyfile"):
            assert token not in text.replace("never creates a", ""), (name, token)

    def test_a_run_creates_no_symlink_anywhere_in_its_scratch_tree(self, tmp_path: Path) -> None:
        scenario = load(GOOD_TASK)
        seen: list[Path] = []

        def runner(argv: Any, **kwargs: Any) -> Any:
            seen.extend(p for p in Path(kwargs["cwd"]).parent.rglob("*") if p.is_symlink())
            return fake(argv, **kwargs)

        fake = fake_runner(scenario, ["known_good"], stdout=lambda _i: _stdout())
        settings = live_mod.RunSettings("gpt-5.6-luna", "low", retry_budget=0, harness="codex")
        live_mod.run_experiment(
            [scenario], {"current": "rules"}, settings, live_mod.InvocationBudget(5), runner=runner
        )
        assert seen == []

    def test_the_child_environment_never_names_a_credential_file(self) -> None:
        env = codex_mod.codex_env()
        assert not any("auth.json" in value or ".credentials" in value for value in env.values())


class TestParse:
    def test_success_run_yields_facts(self) -> None:
        facts = codex_mod.parse_codex_run(_stdout(), _stderr(), "codex-cli 0.157.1")
        assert facts.completed and facts.failure == "" and facts.limit_hit == ""
        assert facts.models == ("gpt-5.6-luna",) and facts.efforts == ("low",)
        assert facts.cli_version == "codex-cli 0.157.1" and facts.final_text == "Done."

    def test_cached_tokens_do_not_overlap_input(self) -> None:
        facts = codex_mod.parse_codex_run(_stdout(), "")
        assert (facts.input_tokens, facts.cache_read_tokens, facts.output_tokens) == (600, 400, 50)
        assert facts.cost_usd == 0.0 and facts.cache_write_tokens == 0

    def test_cached_larger_than_input_never_goes_negative(self) -> None:
        usage = {"input_tokens": 5, "cached_input_tokens": 9, "output_tokens": 1}
        assert codex_mod.parse_codex_run(_stdout(usage=usage), "").input_tokens == 0

    def test_tool_items_map_to_allowed_names_and_failures_count(self) -> None:
        items: list[dict[str, Any]] = [
            {"type": "command_execution", "exit_code": 0, "status": "completed"},
            {"type": "command_execution", "exit_code": 2, "status": "completed"},
            {"type": "file_change", "status": "failed"},
            {"type": "reasoning"},
            {"type": "mcp_tool_call", "status": "completed"},
        ]
        facts = codex_mod.parse_codex_run(_stdout(items=items), "")
        assert facts.tool_calls == ("Bash", "Bash", "Edit", "mcp_tool_call")
        assert facts.tool_errors == 2

    def test_turn_failed_is_a_harness_failure(self) -> None:
        terminal = {"type": "turn.failed", "error": {"message": "boom"}}
        facts = codex_mod.parse_codex_run(_stdout(terminal=terminal), "")
        assert not facts.completed and facts.failure == "turn.failed"

    def test_error_event_before_completion_is_a_failure(self) -> None:
        text = json.dumps({"type": "error", "message": "x"}) + "\n" + _stdout()
        facts = codex_mod.parse_codex_run(text, "")
        assert not facts.completed and facts.failure == "error"

    def test_missing_turn_completed_is_never_a_pass(self) -> None:
        facts = codex_mod.parse_codex_run(json.dumps({"type": "thread.started"}), "")
        assert not facts.completed and "no turn.completed" in facts.failure

    def test_empty_and_malformed_output_fail_closed(self) -> None:
        for text in ("", "not json\n\n[1, 2]\n"):
            facts = codex_mod.parse_codex_run(text, "")
            assert not facts.completed and facts.models == ()

    def test_no_backend_frames_means_no_model_and_no_effort(self) -> None:
        facts = codex_mod.parse_codex_run(_stdout(), "no frames here")
        assert facts.models == () and facts.efforts == ()

    def test_a_truncated_json_frame_drops_attribution_not_the_run(self) -> None:
        facts = codex_mod.parse_codex_run(_stdout(), FRAME + '{"type": "response.cre')
        assert facts.completed and facts.models == () and facts.efforts == ()

    def test_two_responses_with_different_models_are_both_recorded(self) -> None:
        stderr = _stderr("a", "low") + "\n" + _frame("response.created", "r2", "b", "high")
        facts = codex_mod.parse_codex_run(_stdout(), stderr)
        assert facts.models == ("a", "b") and facts.efforts == ("low", "high")


class TestRunTask:
    def _run(self, task: str, overlays: list[str | None], tmp_path: Path, **kw: Any) -> Any:
        scenario = load(task)
        control_file = tmp_path / "control.md"
        control_file.write_text("rules", encoding="utf-8")
        settings = live_mod.RunSettings("gpt-5.6-luna", "low", retry_budget=1, harness="codex")
        runner = fake_runner(scenario, overlays, stdout=lambda _i: _stdout(), **kw)
        budget = live_mod.InvocationBudget(10)
        run = live_mod.run_task(
            scenario, "current", control_file, BASE, settings, budget, runner=runner
        )
        return run, runner

    def test_known_good_first_pass_is_accepted_durable(self, tmp_path: Path) -> None:
        run, runner = self._run(GOOD_TASK, ["known_good"], tmp_path)
        assert run.record is not None and len(runner.calls) == 1
        assert classify(run.record) is Verdict.ACCEPTED_DURABLE
        assert run.record.config.harness == "codex"
        assert run.record.config.harness_version == "unobserved"
        assert runner.calls[0][0] == "codex" and runner.calls[0][-1].startswith("Complete this")

    def test_known_bad_is_rejected_after_one_correction(self, tmp_path: Path) -> None:
        run, runner = self._run(PLAUSIBLE_TASK, ["known_bad"], tmp_path)
        assert run.record is not None and len(runner.calls) == 2
        assert classify(run.record) is Verdict.REJECTED
        assert "deterministic acceptance check failed" in runner.calls[1][-1]

    def test_nonzero_exit_without_a_turn_is_a_harness_failure(self, tmp_path: Path) -> None:
        scenario = load(GOOD_TASK)
        control_file = tmp_path / "c.md"
        control_file.write_text("r", encoding="utf-8")
        settings = live_mod.RunSettings("m", "low", harness="codex")

        def runner(argv: Any, **_k: Any) -> Any:
            return subprocess.CompletedProcess(argv, 1, "", "")

        run = live_mod.run_task(
            scenario, "current", control_file, BASE, settings, live_mod.InvocationBudget(5),
            runner=runner,
        )
        assert run.record is None and run.note

    def test_unknown_harness_is_refused_before_any_launch(self) -> None:
        settings = live_mod.RunSettings("m", "low", harness="gemini")
        with pytest.raises(live_mod.LiveRunError, match="unknown harness"):
            live_mod.run_experiment([], {}, settings, live_mod.InvocationBudget(1))


class TestExperiment:
    def test_experiment_labels_records_codex(self) -> None:
        scenario = load(GOOD_TASK)
        runner = fake_runner(scenario, ["known_good"], stdout=lambda _i: _stdout())
        settings = live_mod.RunSettings("gpt-5.6-luna", "low", retry_budget=0, harness="codex")
        result = live_mod.run_experiment(
            [scenario], {"current": "rules"}, settings, live_mod.InvocationBudget(5), runner=runner
        )
        assert result.harness_failures == ()
        assert result.records["current"][0].config.harness == "codex"


class TestCli:
    def test_dry_run_names_the_codex_harness_and_default_model(self, capsys: Any) -> None:
        assert cli.main(["--harness", "codex", "--tasks", GOOD_TASK]) == 0
        report = json.loads(capsys.readouterr().out)
        assert report["harness"] == "codex" and report["model"] == "gpt-5.6-luna"
        assert report["model_calls"] == 0

    def test_dry_run_default_stays_claude_haiku(self, capsys: Any) -> None:
        assert cli.main(["--tasks", GOOD_TASK]) == 0
        report = json.loads(capsys.readouterr().out)
        assert report["harness"] == "claude" and report["model"] == "haiku"

    def test_live_without_stored_login_exits_auth(self, tmp_path: Path) -> None:
        argv = ["--harness", "codex", "--live", "--output-dir", str(tmp_path)]
        assert cli.main(argv) == cli.EXIT_AUTH

    def test_live_with_codex_off_path_exits_auth(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(cli.shutil, "which", lambda _name: None)
        argv = ["--harness", "codex", "--live", "--use-stored-login", "--output-dir", str(tmp_path)]
        assert cli.main(argv) == cli.EXIT_AUTH

    def test_effort_is_verified_only_when_every_run_names_it(self) -> None:
        facts = codex_mod.parse_codex_run(_stdout(), _stderr(effort="low"))
        bare = codex_mod.parse_codex_run(_stdout(), "")
        args = type("A", (), {"harness": "codex", "effort": "low"})()
        full = live_mod.ExperimentResult(
            {}, (live_mod.Invocation("c", "t", 0, 0, 1.0, facts),), ()
        )
        partial = live_mod.ExperimentResult(
            {},
            (
                live_mod.Invocation("c", "t", 0, 0, 1.0, facts),
                live_mod.Invocation("c", "t", 1, 0, 1.0, bare),
            ),
            (),
        )
        assert cli._effort_fields(args, full)["effort_verified"] is True
        assert cli._effort_fields(args, partial)["effort_verified"] is False
        other = type("A", (), {"harness": "codex", "effort": "high"})()
        assert cli._effort_fields(other, full)["effort_verified"] is False

    def test_claude_effort_stays_unobservable(self) -> None:
        args = type("A", (), {"harness": "claude", "effort": "low"})()
        fields = cli._effort_fields(args, live_mod.ExperimentResult({}, (), ()))
        assert fields["effort_verified"] is False
