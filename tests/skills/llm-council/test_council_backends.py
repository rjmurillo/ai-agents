"""Tests for council_backends: subprocess encoding, Copilot output cleanup, routing.

Ported from the machine-config llm-council unittest suite (encoding, footer,
argument limit), with the subprocess replaced by a fake. No test reaches a model.
"""

from __future__ import annotations

import sys
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
    assert cmd[:3] == ["copilot", "-p", "hello"]
    assert cmd[cmd.index("--model") + 1] == "gpt-6-sol"


def test_long_prompt_goes_through_a_temp_file_that_is_removed(calls, monkeypatch):
    monkeypatch.setattr(backends, "_COPILOT_ARG_LIMIT", 1)

    backends.call_copilot("gpt-6-sol", "a long prompt")

    cmd = calls[0][0]
    assert "--add-dir" in cmd
    prompt_file = cmd[2].split("Read the file at ", 1)[1].split(" verbatim", 1)[0]
    assert not Path(prompt_file).exists()


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
