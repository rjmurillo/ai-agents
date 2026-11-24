"""SessionStart hooks use the shared stdio helpers and fail open without them.

Both hooks import ``drain_stdin`` and ``emit_utf8`` from
``hook_utilities.protocol_output``. They carry no copy of those helpers: a copy
in each hook is a duplicated block the duplicate-code gate rejects. When the lib
lacks the module, ``main()`` raises ``NameError`` and the fail-open handler under
``__main__`` prints a warning and exits 0, so session start never blocks.

The hooks render from ``templates/hooks/SessionStart/`` into ``.claude/hooks/``
(repo-only entries, no plugin hop), so these tests run against the rendered copy
that Claude Code executes.
"""

from __future__ import annotations

import importlib.util
import io
import runpy
import sys
from pathlib import Path
from types import ModuleType

import pytest

HOOKS_DIR = Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "SessionStart"
HOOK_NAMES = ["invoke_context_loader", "invoke_checkout_freshness_check"]


def _isolate_plugin_root(monkeypatch: pytest.MonkeyPatch) -> None:
    """Resolve the hook lib from the checkout, not a plugin root the shell inherited."""
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    monkeypatch.delenv("COPILOT_PLUGIN_ROOT", raising=False)


def _load(name: str, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    _isolate_plugin_root(monkeypatch)
    monkeypatch.syspath_prepend(str(HOOKS_DIR))
    spec = importlib.util.spec_from_file_location(f"{name}_stdio", HOOKS_DIR / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)  # dataclasses resolve their module here
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("name", HOOK_NAMES)
def test_hooks_use_the_shared_stdio_helpers(name: str, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load(name, monkeypatch)

    assert module._drain_stdin.__module__ == "hook_utilities.protocol_output"
    assert module._emit_utf8.__module__ == "hook_utilities.protocol_output"


@pytest.mark.parametrize("name", HOOK_NAMES)
def test_missing_protocol_output_fails_open(
    name: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _isolate_plugin_root(monkeypatch)
    monkeypatch.syspath_prepend(str(HOOKS_DIR))
    monkeypatch.setitem(sys.modules, "hook_utilities.protocol_output", None)
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))

    with pytest.raises(SystemExit) as exit_info:
        runpy.run_path(str(HOOKS_DIR / f"{name}.py"), run_name="__main__")

    assert exit_info.value.code == 0
    captured = capsys.readouterr()
    assert "[WARNING]" in captured.err
    assert "_drain_stdin" in captured.err
    assert captured.out == ""
