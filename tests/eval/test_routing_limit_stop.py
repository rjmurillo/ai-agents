# ruff: noqa: F811
"""`_run_live` stops at a usage-limit or credit-exhaustion failure (issue #5426)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.eval._routing_runner_test_support import backend_mod, cli, result_mod
from tests.eval.test_eval_routing_benchmark_cli import (  # noqa: F401
    ScriptedLive,
    _installed_matches_pin,
    _live_args,
    _no_ambient_credentials,
    scripted_live,
    small_config,
    verified,
)

CODEX_LIMIT = "Your workspace is out of credits"
CLAUDE_LIMIT = (
    "exit code 1; claude error (api_error_status=429, terminal_reason=api_error): "
    "You've hit your usage limit. Your limit resets at 3pm."
)


def _fail_with(detail: str) -> backend_mod.Script:
    patch = {"failure": result_mod.FailureKind.HARNESS, "failure_detail": detail}
    return backend_mod.Script(overrides={"role:orchestrator": patch, "role:worker": patch})


def _run(
    verified: Path, small_config: Path, tmp_path: Path, script: backend_mod.Script
) -> tuple[int, list[dict[str, object]]]:
    ScriptedLive.script = script
    output = tmp_path / "results.jsonl"
    code = cli.main([*_live_args(verified, small_config, output), "--repetitions", "2"])
    return code, [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]


@pytest.mark.parametrize("text", [CODEX_LIMIT, CLAUDE_LIMIT, "Out Of Credits", "USAGE LIMIT hit"])
def test_a_limit_failure_stops_spending_and_marks_every_later_row_not_run(
    text: str,
    verified: Path,
    small_config: Path,
    tmp_path: Path,
    scripted_live: type[ScriptedLive],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("CODEX_API_KEY", "a")
    monkeypatch.setenv("GH_TOKEN", "b")

    code, lines = _run(verified, small_config, tmp_path, _fail_with(text))

    first, rest = lines[0], lines[1:]
    assert code == cli.EXIT_HARNESS_FAILURE
    assert first["status"] == "HARNESS_FAILED" and len(scripted_live.created) == 1
    assert len(lines) == 2 * 6 * 2 * 2 and {r["status"] for r in rest} == {"NOT_RUN"}
    assert all("usage or credit limit" in str(r["reason"]) for r in rest)
    assert text[:12].lower() in str(rest[0]["reason"]).lower()
    err = capsys.readouterr().err
    assert "run stopped" in err and "NOT_RUN" in err


def test_a_harness_failure_that_is_not_a_limit_does_not_stop_the_run(
    verified: Path,
    small_config: Path,
    tmp_path: Path,
    scripted_live: type[ScriptedLive],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CODEX_API_KEY", "a")
    monkeypatch.setenv("GH_TOKEN", "b")
    detail = (
        "exit code 1; claude error (api_error_status=404, terminal_reason=api_error): bad model"
    )

    code, lines = _run(verified, small_config, tmp_path, _fail_with(detail))

    assert code == cli.EXIT_HARNESS_FAILURE
    assert len(lines) == 2 * 6 * 2 * 2 and len(scripted_live.created) == len(lines)
    assert {r["status"] for r in lines} == {"HARNESS_FAILED"}


def test_the_limit_reason_is_cut_to_a_bounded_length(
    verified: Path,
    small_config: Path,
    tmp_path: Path,
    scripted_live: type[ScriptedLive],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CODEX_API_KEY", "a")
    monkeypatch.setenv("GH_TOKEN", "b")

    _, lines = _run(verified, small_config, tmp_path, _fail_with(CODEX_LIMIT + " " + "x" * 2000))

    assert len(str(lines[1]["reason"])) < 400


def test_a_task_failure_that_mentions_credits_does_not_stop_the_run(
    verified: Path,
    small_config: Path,
    tmp_path: Path,
    scripted_live: type[ScriptedLive],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CODEX_API_KEY", "a")
    monkeypatch.setenv("GH_TOKEN", "b")
    patch = {"failure": result_mod.FailureKind.TASK, "failure_detail": CODEX_LIMIT}
    script = backend_mod.Script(overrides={"role:orchestrator": patch, "role:worker": patch})

    _, lines = _run(verified, small_config, tmp_path, script)

    assert len(scripted_live.created) == len(lines) and "NOT_RUN" not in {
        r["status"] for r in lines
    }


def test_the_budget_stop_keeps_its_exit_code_and_reason(
    verified: Path,
    small_config: Path,
    tmp_path: Path,
    scripted_live: type[ScriptedLive],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CODEX_API_KEY", "a")
    monkeypatch.setenv("GH_TOKEN", "b")
    output = tmp_path / "results.jsonl"
    args = _live_args(verified, small_config, output)
    args[2] = "5"

    code = cli.main(args)

    lines = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    cut = [line for line in lines if line["status"] == "NOT_RUN"]
    assert code == cli.EXIT_OK and cut and "usage or credit" not in cut[0]["reason"]


def test_every_live_row_labels_its_effort_evidence(
    verified: Path,
    small_config: Path,
    tmp_path: Path,
    scripted_live: type[ScriptedLive],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CODEX_API_KEY", "a")
    monkeypatch.setenv("GH_TOKEN", "b")

    _, lines = _run(verified, small_config, tmp_path, backend_mod.Script())

    by_harness = {json.loads(json.dumps(r["harness"]))["name"]: r["effort_evidence"] for r in lines}
    assert by_harness == {"codex": "backend", "copilot": "none"}
    assert cli.EFFORT_EVIDENCE == {"codex": "backend", "claude": "behavioral"}
