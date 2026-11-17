"""Tests for the last-resort Sol route: codex or droid, read-only, no other model.

The subprocess is faked, so no test reaches a model. Covers the exact
read-only argv for each CLI, failure classes, and the sol_loop ``review``
and ``gate --route cli`` steps.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _sol_loop_helpers import SOL, _argv, _logs, _out, mod

cli = sys.modules["sol_cli"]


class Proc:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr


@pytest.fixture
def on_path(monkeypatch):
    def set_runners(*names):
        monkeypatch.setattr(
            cli.shutil, "which", lambda name: f"/bin/{name}" if name in names else None
        )

    return set_runners


def _fake_run(monkeypatch, reply="VERDICT: APPROVE\n", returncode=0, stdout="", stderr=""):
    calls = []

    def fake(cmd, **kwargs):
        calls.append((cmd, kwargs))
        if "-o" in cmd and returncode == 0:
            Path(cmd[cmd.index("-o") + 1]).write_text(reply, encoding="utf-8")
        return Proc(returncode, stdout if stdout or "-o" in cmd else reply, stderr)

    monkeypatch.setattr(cli.subprocess, "run", fake)
    return calls


# Runner choice and argv


def test_codex_is_preferred_over_droid(on_path):
    on_path("codex", "droid")

    assert cli.available_runner() == "codex"


def test_droid_is_used_when_codex_is_absent(on_path):
    on_path("droid")

    assert cli.available_runner() == "droid"


def test_no_runner_when_neither_cli_exists(on_path):
    on_path()

    assert cli.available_runner() == ""


def test_codex_call_is_read_only_and_reads_the_brief_on_stdin(on_path, monkeypatch, tmp_path):
    on_path("codex")
    calls = _fake_run(monkeypatch)

    result = cli.run_sol("codex", SOL, "the brief", tmp_path)

    cmd, kwargs = calls[0]
    assert result.ok
    assert cmd[1:3] == ["exec", "-m"] and cmd[3] == SOL
    assert cmd[cmd.index("-s") + 1] == "read-only"
    assert "--ignore-user-config" in cmd
    assert cmd[cmd.index("--disable") + 1] == "apps"
    assert cmd[-1] == "-"
    assert kwargs["input"] == "the brief"
    assert (kwargs["encoding"], kwargs["errors"]) == ("utf-8", "replace")


def test_droid_call_has_no_autonomy_flag(on_path, monkeypatch, tmp_path):
    on_path("droid")
    calls = _fake_run(monkeypatch)

    result = cli.run_sol("droid", SOL, "the brief", tmp_path)

    cmd, _ = calls[0]
    assert result.ok and result.text == "VERDICT: APPROVE\n"
    assert cmd[1:4] == ["exec", "-m", SOL]
    assert "--auto" not in cmd
    assert "-f" in cmd
    assert cmd[cmd.index("--only-tools") + 1] == "Read,Grep,Glob,LS"


# Failures


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ('{"status":402,"title":"Payment Required"} usage limit (resets in 7h)', "quota"),
        ("API Error: 400 unknown provider for model x", "model-unsupported"),
        ("The 'x' model is not supported", "model-unsupported"),
        ("HTTP 429 Too Many Requests", "rate-limit"),
        ("401 Unauthorized: not logged in", "auth"),
        ("HTTP 503 service unavailable", "5xx"),
        ("request id 4290ab: connection reset", "unknown"),
        ("used 512 tokens before the connection dropped", "unknown"),
        ("error at line 503 of the patch", "unknown"),
        ("HTTP status 502 bad gateway", "5xx"),
    ],
)
def test_failure_classification(message, expected):
    assert cli.classify_failure(message) == expected


def test_codex_turn_failed_message_is_classified(on_path, monkeypatch, tmp_path):
    on_path("codex")
    events = json.dumps({"type": "turn.failed", "error": {"message": "usage limit reached"}})
    _fake_run(monkeypatch, returncode=1, stdout=events + "\n")

    result = cli.run_sol("codex", SOL, "b", tmp_path)

    assert (result.ok, result.failure_class) == (False, "quota")


def test_timeout_is_classified(on_path, monkeypatch, tmp_path):
    on_path("codex")

    def boom(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, 1)

    monkeypatch.setattr(cli.subprocess, "run", boom)

    assert cli.run_sol("codex", SOL, "b", tmp_path, timeout=1).failure_class == "timeout"


def test_empty_reply_is_invalid_output(on_path, monkeypatch, tmp_path):
    on_path("droid")
    _fake_run(monkeypatch, reply="  \n")

    assert cli.run_sol("droid", SOL, "b", tmp_path).failure_class == "invalid-output"


def test_missing_runner_is_not_ok(on_path, tmp_path):
    on_path()

    assert cli.run_sol("codex", SOL, "b", tmp_path).ok is False


# sol_loop review and gate --route cli


def _brief(tmp_path):
    path = tmp_path / "brief.md"
    path.write_text("Review only.\n", encoding="utf-8")
    return path


def test_gate_cli_route_skips_quietly_without_a_cli(tmp_path, critic_file, monkeypatch, capsys):
    monkeypatch.setattr(mod, "available_runner", lambda: "")

    code = mod.main(_argv("gate", tmp_path, critic_file, "--route", "cli"))

    out = _out(capsys)
    assert code == mod.EXIT_OK
    assert (out["verdict"], out["log"]) == ("SKIPPED", None)
    assert _logs(tmp_path) == []


def test_review_records_the_cli_reply(tmp_path, critic_file, monkeypatch, capsys):
    monkeypatch.setattr(mod, "available_runner", lambda: "codex")
    reply = "VERDICT: CHANGES\nS1 [should] src/app/b.py:5 bug. Repro: run it.\n"
    monkeypatch.setattr(
        mod,
        "run_sol",
        lambda runner, model, brief, cwd, timeout: cli.CliResult(ok=True, text=reply),
    )

    code = mod.main(_argv("review", tmp_path, critic_file, "--brief-file", str(_brief(tmp_path))))

    log = _logs(tmp_path)[0]
    assert code == mod.EXIT_OK
    assert (log["status"], log["runner"], log["counts"]["sol_only"]) == ("ok", "codex", 1)


def test_review_failure_takes_the_warn_path_with_no_fallback(
    tmp_path, critic_file, monkeypatch, capsys
):
    calls = []
    monkeypatch.setattr(mod, "available_runner", lambda: "droid")

    def failing(runner, model, brief, cwd, timeout):
        calls.append(model)
        return cli.CliResult(ok=False, failure_class="quota", detail="droid: usage limit")

    monkeypatch.setattr(mod, "run_sol", failing)

    code = mod.main(_argv("review", tmp_path, critic_file, "--brief-file", str(_brief(tmp_path))))

    out = _out(capsys)
    assert code == mod.EXIT_UNAVAILABLE
    assert (out["reason"], calls) == ("review-model-unavailable", [SOL])
    assert _logs(tmp_path)[0]["failure_class"] == "quota"


def test_review_without_a_cli_is_a_config_error(tmp_path, critic_file, monkeypatch):
    monkeypatch.setattr(mod, "available_runner", lambda: "")

    assert (
        mod.main(_argv("review", tmp_path, critic_file, "--brief-file", str(_brief(tmp_path)))) == 2
    )
    assert _logs(tmp_path) == []


def test_review_refuses_a_non_sol_model(tmp_path, critic_file, monkeypatch):
    monkeypatch.setattr(mod, "run_sol", lambda *a: pytest.fail("no model call expected"))
    argv = _argv("review", tmp_path, critic_file, "--brief-file", str(_brief(tmp_path)))
    argv[argv.index("--model") + 1] = "claude-opus-5-5"

    assert mod.main(argv) == mod.EXIT_CONFIG
