"""Tests for council_backends: subprocess encoding, Copilot output cleanup, routing.

Ported from the machine-config llm-council unittest suite (encoding, footer,
argument limit), with the subprocess replaced by a fake. No test reaches a model.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
SCRIPTS_DIR = str(Path(__file__).resolve().parents[3] / ".claude/skills/llm-council/scripts")
for entry in (TESTS_SKILLS_DIR, SCRIPTS_DIR):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from claude_skills_import import import_skill_script

backends = import_skill_script(
    ".claude/skills/llm-council/scripts/council_backends.py", module_name="council_backends_t"
)


@pytest.fixture(autouse=True)
def _no_cli_on_path(monkeypatch, tmp_path):
    """Hide every vendor CLI and the real Copilot MCP config."""
    monkeypatch.setattr(backends.shutil, "which", lambda name: None)
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path / "copilot-home"))


class Completed:
    def __init__(self, stdout="ok�", returncode=0, stderr=""):
        self.stdout, self.returncode, self.stderr = stdout, returncode, stderr


@pytest.fixture
def calls(monkeypatch):
    seen = []

    def fake_run(cmd, **kwargs):
        seen.append((cmd, kwargs))
        return Completed()

    monkeypatch.setattr(backends.subprocess, "run", fake_run)
    return seen


def test_text_subprocesses_request_utf8_with_replacement(calls, monkeypatch):
    assert backends.gh_token() == "ok�"
    assert backends.call_copilot("gpt-5.5", "short") == "ok�"
    monkeypatch.setattr(backends, "_COPILOT_ARG_LIMIT", 1)
    assert backends.call_copilot("gpt-5.5", "long") == "ok�"

    assert len(calls) == 3
    for _, kwargs in calls:
        assert (kwargs["capture_output"], kwargs["text"]) == (True, True)
        assert (kwargs["encoding"], kwargs["errors"]) == ("utf-8", "replace")


def test_short_prompt_goes_on_the_command_line(calls):
    backends.call_copilot("gpt-6-sol", "hello")

    cmd = calls[0][0]
    assert cmd[0] == "copilot"
    assert cmd[cmd.index("-p") + 1] == "hello"
    assert cmd[cmd.index("--model") + 1] == "gpt-6-sol"


def test_long_prompt_goes_through_a_temp_file_that_is_removed(calls, monkeypatch):
    monkeypatch.setattr(backends, "_COPILOT_ARG_LIMIT", 1)

    backends.call_copilot("gpt-6-sol", "a long prompt")

    cmd = calls[0][0]
    assert "--add-dir" in cmd
    trampoline = cmd[cmd.index("-p") + 1]
    prompt_file = Path(trampoline.split("Read the file at ", 1)[1].split(" verbatim", 1)[0])
    granted = Path(cmd[cmd.index("--add-dir") + 1])
    assert granted == prompt_file.parent
    assert granted != Path(tempfile.gettempdir())
    assert not granted.exists()


def test_copilot_failure_raises(monkeypatch):
    monkeypatch.setattr(backends.subprocess, "run", lambda cmd, **kw: Completed("", 1, "boom"))

    with pytest.raises(RuntimeError, match="copilot rc=1: boom"):
        backends.call_copilot("gpt-6-sol", "x")


def test_arg_limit_threshold_reasonable():
    assert 1000 < backends._COPILOT_ARG_LIMIT < 30000


def test_strip_multiline_footer():
    raw = "Real response here.\n\n\nAI Credits 21.8 (15s)\nTokens ↑ 34.8k"

    match = backends._COPILOT_FOOTER.search(raw)

    stripped = raw[: match.start()].strip()
    assert stripped == "Real response here."


def test_strip_read_preamble():
    raw = "● Read foo.txt\n  │ /tmp/foo.txt\n  └ 1 line read\n\nActual response.\n"

    cleaned = backends._COPILOT_TOOL_PREAMBLE.sub("", raw)

    assert "Actual response." in cleaned
    assert "Read foo.txt" not in cleaned


def test_call_model_routes_copilot_ids_to_copilot(monkeypatch):
    monkeypatch.setattr(backends, "call_copilot", lambda model, prompt, timeout: f"copilot:{model}")

    assert backends.call_model(None, "claude-opus-5.5", "q") == "copilot:claude-opus-5.5"


def test_call_model_needs_a_token_for_github_models():
    with pytest.raises(RuntimeError, match="no gh token"):
        backends.call_model(None, "openai/gpt-4.1", "q")


# Route ladder rung 3: each member's own vendor CLI first


@pytest.mark.parametrize(
    ("model", "on_path", "expected"),
    [
        ("claude-opus-5.5", {"claude"}, "claude"),
        ("gpt-6-sol", {"codex"}, "codex"),
        ("gpt-6-sol", set(), "copilot"),
        ("claude-sonnet-5", {"codex"}, "copilot"),
        ("openai/gpt-4.1", {"claude", "codex"}, "github-models"),
    ],
)
def test_backend_for_prefers_the_vendor_cli(monkeypatch, model, on_path, expected):
    monkeypatch.setattr(backends.shutil, "which", lambda name: name if name in on_path else None)

    assert backends.backend_for(model) == expected


@pytest.mark.parametrize(
    ("copilot_id", "cli_id"),
    [
        ("claude-opus-5.5", "claude-opus-5-5"),
        ("claude-sonnet-5", "claude-sonnet-5"),
        ("claude-haiku-4.5", "claude-haiku-4-5"),
    ],
)
def test_claude_cli_model_ids(copilot_id, cli_id):
    assert backends.claude_cli_model(copilot_id) == cli_id


def test_claude_call_has_no_tools_and_uses_stdin(calls):
    assert backends.call_claude("claude-opus-5.5", "the question") == "ok\ufffd"

    cmd, kwargs = calls[0]
    assert cmd == [
        "claude",
        "-p",
        "--model",
        "claude-opus-5-5",
        "--tools",
        "",
        "--strict-mcp-config",
    ]
    assert kwargs["input"] == "the question"


def test_codex_call_is_read_only_and_uses_stdin(monkeypatch):
    seen = []

    def fake_run(cmd, **kwargs):
        seen.append((cmd, kwargs))
        Path(cmd[cmd.index("-o") + 1]).write_text("answer", encoding="utf-8")
        return Completed()

    monkeypatch.setattr(backends.subprocess, "run", fake_run)

    assert backends.call_codex("gpt-6-sol", "the question") == "answer"
    cmd, kwargs = seen[0]
    assert cmd[cmd.index("-s") + 1] == "read-only"
    assert "--ignore-user-config" in cmd
    assert cmd[cmd.index("--disable") + 1] == "apps"
    assert cmd[-1] == "-"
    assert kwargs["input"] == "the question"


@pytest.mark.parametrize("long_prompt", [False, True])
def test_copilot_calls_deny_shell_write_url_memory_and_mcp(calls, monkeypatch, long_prompt):
    if long_prompt:
        monkeypatch.setattr(backends, "_COPILOT_ARG_LIMIT", 1)

    backends.call_copilot("gpt-6-sol", "question")

    cmd = calls[0][0]
    denied = {cmd[i + 1] for i, arg in enumerate(cmd) if arg == "--deny-tool"}
    assert denied == {"shell", "write", "url", "memory"}
    assert "--disable-builtin-mcps" in cmd


def test_empty_claude_reply_raises(monkeypatch):
    monkeypatch.setattr(backends.subprocess, "run", lambda cmd, **kw: Completed(stdout="  \n"))

    with pytest.raises(RuntimeError, match="empty reply"):
        backends.call_claude("claude-opus-5.5", "q")


def test_copilot_disables_and_denies_each_user_mcp_server(calls, tmp_path, monkeypatch):
    home = tmp_path / "copilot-home"
    home.mkdir()
    (home / "mcp-config.json").write_text(
        '{"mcpServers": {"beads": {}, "ado": {}}}', encoding="utf-8"
    )

    backends.call_copilot("gpt-6-sol", "question")

    cmd = calls[0][0]
    disabled = {cmd[i + 1] for i, arg in enumerate(cmd) if arg == "--disable-mcp-server"}
    denied = {cmd[i + 1] for i, arg in enumerate(cmd) if arg == "--deny-tool"}
    assert disabled == {"beads", "ado"}
    assert {"beads", "ado", "shell", "write", "url", "memory"} <= denied


@pytest.mark.parametrize("content", ["not json", '{"mcpServers": []}', "[]"])
def test_unreadable_copilot_mcp_config_adds_no_servers(tmp_path, content):
    home = tmp_path / "copilot-home"
    home.mkdir()
    (home / "mcp-config.json").write_text(content, encoding="utf-8")

    assert backends._copilot_user_mcp_servers() == []


class FakeResponse:
    def __init__(self, status, body, reason="OK"):
        self.status, self.reason, self._body = status, reason, body

    def read(self):
        return self._body


class FakeConnection:
    seen: list = []

    def __init__(self, host, timeout=None, context=None):
        FakeConnection.seen.append({"host": host, "timeout": timeout, "context": context})
        self.response = FakeConnection.next_response

    def request(self, method, path, body=None, headers=None):
        FakeConnection.seen[-1].update(method=method, path=path, headers=headers)

    def getresponse(self):
        return self.response

    def close(self):
        FakeConnection.seen[-1]["closed"] = True


def test_github_models_posts_to_the_fixed_host_with_tls(monkeypatch):
    FakeConnection.seen = []
    FakeConnection.next_response = FakeResponse(
        200, b'{"choices": [{"message": {"content": "hi"}}]}'
    )
    monkeypatch.setattr(backends.http.client, "HTTPSConnection", FakeConnection)

    assert backends.call_github_models("tok", "openai/gpt-4.1", "q") == "hi"

    seen = FakeConnection.seen[0]
    assert (seen["host"], seen["method"], seen["path"]) == (
        "models.github.ai",
        "POST",
        "/inference/chat/completions",
    )
    assert seen["context"] is not None
    assert seen["headers"]["Authorization"] == "Bearer tok"
    assert seen["closed"] is True


def test_github_models_error_surfaces_status_and_body(monkeypatch):
    FakeConnection.seen = []
    FakeConnection.next_response = FakeResponse(429, b"slow down", reason="Too Many Requests")
    monkeypatch.setattr(backends.http.client, "HTTPSConnection", FakeConnection)

    with pytest.raises(RuntimeError, match="GitHub Models 429 Too Many Requests: slow down"):
        backends.call_github_models("tok", "openai/gpt-4.1", "q")
