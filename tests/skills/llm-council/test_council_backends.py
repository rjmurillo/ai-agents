"""Tests for council_backends: subprocess encoding, Copilot output cleanup, routing.

Ported from the machine-config llm-council unittest suite (encoding, footer,
argument limit), with the subprocess replaced by a fake. No test reaches a model.
"""

from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path

import pytest

_SUPPORT_SPEC = importlib.util.spec_from_file_location(
    "llm_council_support", Path(__file__).with_name("_support.py")
)
if _SUPPORT_SPEC is None or _SUPPORT_SPEC.loader is None:
    raise ImportError("llm-council _support.py is missing")
support = importlib.util.module_from_spec(_SUPPORT_SPEC)
_SUPPORT_SPEC.loader.exec_module(support)

backends = support.load_script("council_backends.py", "council_backends_t")


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


def _copilot_reply(stdout: str, monkeypatch) -> str:
    monkeypatch.setattr(backends.subprocess, "run", lambda cmd, **kw: Completed(stdout))
    reply: str = backends.call_copilot("gpt-6-sol", "q")
    return reply


REAL_FOOTER = "\n\nChanges    +0 -0\nAI Credits 0 (12s)\nResume     copilot --resume=68947a59-aaaa"


@pytest.mark.parametrize(
    "footer",
    [
        REAL_FOOTER,
        "\n\nChanges    +0 -0\nAI Credits 0 (12s)",
        "\n\nChanges    +3 -1\nAI Credits 21.8 (15s)\nTokens \u2191 34.8k \u2193 1.2k",
        "\n\n\nAI Credits 21.8 (15s)\nTokens \u2193 9\n\n",
    ],
)
def test_real_footer_is_stripped(monkeypatch, footer):
    assert _copilot_reply("Real response here." + footer, monkeypatch) == "Real response here."


def test_footer_lookalike_inside_the_answer_is_preserved(monkeypatch):
    answer = "Summary\nChanges +12 lines require migration.\nFinding: old clients fail."

    assert _copilot_reply(answer, monkeypatch) == answer


def test_footer_lookalike_inside_the_answer_survives_a_real_footer(monkeypatch):
    answer = "Summary\nChanges +12 lines require migration.\nFinding: old clients fail."

    assert _copilot_reply(answer + REAL_FOOTER, monkeypatch) == answer


def test_mid_text_ai_credits_line_followed_by_prose_is_preserved(monkeypatch):
    answer = "Cost note\nAI Credits 5\nare billed per request.\nDone."

    assert _copilot_reply(answer + REAL_FOOTER, monkeypatch) == answer


@pytest.mark.parametrize(
    "last_line",
    [
        "AI Credits 5 reviews remain.",
        "Tokens ↑ grew a lot",
        "AI Credits 5 (soon)",
        "AI Credits 5 ()",
        "Resume copilot --resume=",
    ],
)
def test_final_answer_line_shaped_like_a_footer_is_kept(monkeypatch, last_line):
    answer = f"Answer.\n{last_line}"

    assert _copilot_reply(answer, monkeypatch) == answer


@pytest.mark.parametrize(
    "footer",
    [
        "\n\nChanges    +0 -0\nAI Credits 0 (12s)\nResume     copilot --resume=68947a59-0d59-4080",
        "\nAI Credits 21.8 (1m 20s)\nTokens ↑ 34.8k",
        "\nAI Credits 3 (2m)\nTokens ↓ 2M ↑ 9",
    ],
)
def test_exact_footer_shapes_are_stripped_after_an_answer_line(monkeypatch, footer):
    assert _copilot_reply("Answer." + footer, monkeypatch) == "Answer."


def test_answer_that_ends_with_changes_prose_keeps_it(monkeypatch):
    assert _copilot_reply("Result\nChanges +12 lines", monkeypatch) == "Result\nChanges +12 lines"


def test_disabled_tools_block_is_stripped(monkeypatch):
    stdout = (
        " \u25cf Disabled tools: 1password-authenticate, bash,\n"
        "   beads-beads_claim, context-mode-ctx_execute,\n"
        "   write_agent\n\nThe answer.\n  indented line stays"
    )

    assert _copilot_reply(stdout, monkeypatch) == "The answer.\n  indented line stays"


def test_disabled_tools_block_and_footer_together(monkeypatch):
    stdout = " \u25cf Disabled tools: bash,\n   write_agent\n\nThe answer." + REAL_FOOTER

    assert _copilot_reply(stdout, monkeypatch) == "The answer."


def test_disabled_tools_text_in_the_middle_of_an_answer_is_preserved(monkeypatch):
    answer = "Intro\n \u25cf Disabled tools: bash\nOutro"

    assert _copilot_reply(answer, monkeypatch) == answer


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
    assert denied - {"read"} == {"shell", "write", "url", "memory"}
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
    seen: list[dict[str, object]] = []

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


# GitHub Models reply validation


def _models_reply(monkeypatch, status, body, reason="OK"):
    FakeConnection.seen = []
    FakeConnection.next_response = FakeResponse(status, body, reason=reason)
    monkeypatch.setattr(backends.http.client, "HTTPSConnection", FakeConnection)
    return backends.call_github_models("tok", "openai/gpt-4.1", "q")


@pytest.mark.parametrize(
    "body",
    [
        b"not json",
        b"",
        b"\xff\xfe",
        b"[]",
        b'"text"',
        b"7",
        b"null",
        b"{}",
        b'{"choices": []}',
        b'{"choices": {}}',
        b'{"choices": "abc"}',
        b'{"choices": [null]}',
        b'{"choices": [{}]}',
        b'{"choices": [{"message": {}}]}',
        b'{"choices": [{"message": null}]}',
        b'{"choices": [{"message": {"content": null}}]}',
        b'{"choices": [{"message": {"content": 42}}]}',
        b'{"choices": [{"message": {"content": ["a"]}}]}',
        b'{"choices": [{"message": {"content": ""}}]}',
        b'{"choices": [{"message": {"content": "  \\n"}}]}',
    ],
)
def test_github_models_malformed_body_raises_runtime_error(monkeypatch, body):
    with pytest.raises(RuntimeError, match="GitHub Models returned a malformed reply"):
        _models_reply(monkeypatch, 200, body)


@pytest.mark.parametrize("status", [199, 301, 302, 304, 399])
def test_github_models_rejects_status_outside_2xx(monkeypatch, status):
    with pytest.raises(RuntimeError, match=f"GitHub Models {status} Found: moved"):
        _models_reply(monkeypatch, status, b"moved", reason="Found")


@pytest.mark.parametrize("status", [200, 201, 299])
def test_github_models_accepts_2xx(monkeypatch, status):
    body = b'{"choices": [{"message": {"content": "hi"}}]}'

    assert _models_reply(monkeypatch, status, body) == "hi"
