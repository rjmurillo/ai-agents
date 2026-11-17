"""Tests for the Copilot lockdown in council_backends: tools, cwd, temp cleanup, output cleanup.

Every subprocess is a fake. No test reaches a model.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import sys
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

backends = support.load_script("council_backends.py", "council_backends_lockdown_t")


@pytest.fixture(autouse=True)
def _no_cli_on_path(monkeypatch, tmp_path):
    """Hide every vendor CLI and the real Copilot MCP config."""
    monkeypatch.setattr(backends.shutil, "which", lambda name: None)
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path / "copilot-home"))


class Completed:
    def __init__(self, stdout="ok", returncode=0, stderr=""):
        self.stdout, self.returncode, self.stderr = stdout, returncode, stderr


@pytest.fixture
def calls(monkeypatch):
    seen = []

    def fake_run(cmd, **kwargs):
        seen.append((cmd, kwargs))
        return Completed()

    monkeypatch.setattr(backends.subprocess, "run", fake_run)
    return seen


# Copilot lockdown: available tools, cwd, temp cleanup


@pytest.mark.parametrize("long_prompt", [False, True])
def test_copilot_exposes_only_the_view_tool(calls, monkeypatch, long_prompt):
    if long_prompt:
        monkeypatch.setattr(backends, "_COPILOT_ARG_LIMIT", 1)

    backends.call_copilot("gpt-6-sol", "question")

    cmd = calls[0][0]
    assert cmd.count("--available-tools") == 1
    assert cmd[cmd.index("--available-tools") + 1] == "view"
    assert "--deny-tool" in cmd
    assert "--disable-builtin-mcps" in cmd


@pytest.mark.parametrize(("long_prompt", "reads_denied"), [(False, True), (True, False)])
def test_only_a_long_prompt_may_read_files(calls, monkeypatch, long_prompt, reads_denied):
    if long_prompt:
        monkeypatch.setattr(backends, "_COPILOT_ARG_LIMIT", 1)

    backends.call_copilot("gpt-6-sol", "question")

    cmd = calls[0][0]
    denied = {cmd[i + 1] for i, arg in enumerate(cmd) if arg == "--deny-tool"}
    assert ("read" in denied) is reads_denied


def test_short_copilot_call_runs_in_a_fresh_empty_directory(calls):
    backends.call_copilot("gpt-6-sol", "question")

    cwd = Path(calls[0][1]["cwd"])
    assert cwd != Path.cwd()
    assert not cwd.exists()


def test_short_copilot_cwd_is_empty_and_not_the_callers_directory(monkeypatch):
    listing = []

    def fake_run(cmd, **kwargs):
        listing.append(list(Path(kwargs["cwd"]).iterdir()))
        return Completed()

    monkeypatch.setattr(backends.subprocess, "run", fake_run)

    backends.call_copilot("gpt-6-sol", "question")

    assert listing == [[]]


def test_trampoline_copilot_cwd_is_its_private_prompt_dir(calls, monkeypatch):
    monkeypatch.setattr(backends, "_COPILOT_ARG_LIMIT", 1)

    backends.call_copilot("gpt-6-sol", "a long prompt")

    cmd, kwargs = calls[0]
    cwd = Path(kwargs["cwd"])
    assert cwd == Path(cmd[cmd.index("--add-dir") + 1])
    assert cwd != Path.cwd()
    assert not cwd.exists()


def _failing_rmtree(path, ignore_errors=False, onerror=None, *, onexc=None, **kwargs):
    """Fail like shutil.rmtree: report through the handler tempfile passes, inside an except."""
    try:
        raise OSError("device busy")
    except OSError as exc:
        if ignore_errors:
            return
        if onexc is not None:
            onexc(os.rmdir, path, exc)
        elif onerror is not None:
            onerror(os.rmdir, path, sys.exc_info())
        else:
            raise


def test_copilot_reply_survives_a_cleanup_failure(monkeypatch):
    monkeypatch.setattr(backends.subprocess, "run", lambda cmd, **kw: Completed("answer"))
    monkeypatch.setattr(shutil, "rmtree", _failing_rmtree)

    assert backends.call_copilot("gpt-6-sol", "short") == "answer"
    monkeypatch.setattr(backends, "_COPILOT_ARG_LIMIT", 1)
    assert backends.call_copilot("gpt-6-sol", "a long prompt") == "answer"


def test_claude_reply_survives_a_cleanup_failure(monkeypatch):
    monkeypatch.setattr(backends.subprocess, "run", lambda cmd, **kw: Completed("answer"))
    monkeypatch.setattr(shutil, "rmtree", _failing_rmtree)

    assert backends.call_claude("claude-opus-5.5", "q") == "answer"


def test_codex_reply_survives_a_cleanup_failure(monkeypatch):
    def fake_run(cmd, **kwargs):
        Path(cmd[cmd.index("-o") + 1]).write_text("answer", encoding="utf-8")
        return Completed()

    monkeypatch.setattr(backends.subprocess, "run", fake_run)
    monkeypatch.setattr(shutil, "rmtree", _failing_rmtree)

    assert backends.call_codex("gpt-6-sol", "q") == "answer"


def test_cleanup_failure_would_raise_without_ignore_cleanup_errors(monkeypatch):
    """Control: the same failing rmtree breaks a plain TemporaryDirectory."""
    monkeypatch.setattr(shutil, "rmtree", _failing_rmtree)

    with pytest.raises(OSError, match="device busy"), tempfile.TemporaryDirectory():
        pass


def test_codex_decodes_a_reply_file_with_invalid_utf8(monkeypatch):
    def fake_run(cmd, **kwargs):
        Path(cmd[cmd.index("-o") + 1]).write_bytes(b"ok \xff done")
        return Completed()

    monkeypatch.setattr(backends.subprocess, "run", fake_run)

    assert backends.call_codex("gpt-6-sol", "q") == "ok \ufffd done"
