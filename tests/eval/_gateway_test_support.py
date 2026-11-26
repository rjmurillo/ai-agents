"""Shared setup for the Claude CLI gateway tests.

The fixtures that use these helpers live in each test module, so pytest finds
them without a conftest entry.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType

import pytest

from tests.eval import _runtime_parity_test_support  # noqa: F401  (loads _isolated_claude_login)
from tests.eval._cli_transport_test_support import (
    MESSAGES,
    Recorder,
    _claude_cli,
    claude_payload,
    install_runner,
)
from tests.eval._credential_test_support import set_sources

GATEWAY_TOKEN = "gw-" + "G" * 16
GATEWAY_URL = "http://127.0.0.1:8319"
OAUTH_TOKEN = "oauth-" + "O" * 12
MODEL = "claude-sonnet-5-5"

_EVAL_DIR = Path(__file__).resolve().parents[2] / "scripts" / "eval"


def load_prompt_change() -> ModuleType:
    """Load the hyphenated runner module with `scripts/eval` on the path."""
    added = str(_EVAL_DIR) not in sys.path
    if added:
        sys.path.insert(0, str(_EVAL_DIR))
    try:
        spec = importlib.util.spec_from_file_location(
            "eval_prompt_change_gateway", _EVAL_DIR / "eval-prompt-change.py"
        )
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if added and str(_EVAL_DIR) in sys.path:
            sys.path.remove(str(_EVAL_DIR))


def clear_claude_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    """No Claude credential anywhere; the parent's CLAUDE* names cleared."""
    for name in list(os.environ):
        if name.startswith("CLAUDE") or name == "ANTHROPIC_API_KEY":
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("EVAL_DOTENV_FILES", "/nonexistent/ai-agents-eval.env")
    set_sources(monkeypatch, "_claude_cli", probe=False)
    return monkeypatch


def export_gateway(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    monkeypatch.setenv("ANTHROPIC_BASE_URL", GATEWAY_URL)
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", GATEWAY_TOKEN)
    return monkeypatch


def run_once(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[dict[str, str], list[str], _claude_cli._ClaudeCLIProvider]:
    """One fake CLI call; returns the child env, the argv, and the provider."""
    recorder = Recorder(stdout=claude_payload(model=MODEL))
    install_runner(monkeypatch, recorder)
    provider = _claude_cli._ClaudeCLIProvider()
    provider.complete(messages=MESSAGES, model=MODEL)
    return recorder.calls[-1]["env"], recorder.argv, provider
