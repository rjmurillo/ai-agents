#!/usr/bin/env python3
"""Tests for the vanilla hook guard (issue #4672).

The guard's whole value is that it fails when the plugin denies a tool call on
a machine with no Python. So the cases that matter are the refusals: a denying
exit code, an allow with no warning, and a row that is not actually vanilla.

The inline shell this replaced could not be unit tested at all, which is how it
shipped asserting different things on Linux and Windows.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "scripts" / "ci" / "vanilla_hook_guard.py"


def _load():
    spec = importlib.util.spec_from_file_location("vanilla_hook_guard", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["vanilla_hook_guard"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(name="guard")
def guard_fixture():
    return _load()


def test_script_exists() -> None:
    assert _SCRIPT.is_file()


def test_degraded_with_warning_passes(guard) -> None:
    output = (
        "project-toolkit@ai-agents WARNING: hooks DISABLED "
        "(your session is unaffected). No Python interpreter found."
    )
    guard.assert_degraded(0, output)


@pytest.mark.parametrize("code", [1, 2, 127])
def test_any_nonzero_exit_is_a_denial(guard, code: int) -> None:
    """This is the customer defect. Any nonzero exit from PreToolUse denies."""
    output = "project-toolkit@ai-agents WARNING: hooks DISABLED (your session is unaffected)."
    with pytest.raises(guard.GuardError, match="DENIED"):
        guard.assert_degraded(code, output)


def test_allow_without_any_warning_fails(guard) -> None:
    """Exit 0 alone is not enough; a silent skip leaves the user with no clue."""
    with pytest.raises(guard.GuardError, match="did not warn"):
        guard.assert_degraded(0, "")


@pytest.mark.parametrize(
    "missing_fragment",
    ["project-toolkit@ai-agents", "hooks DISABLED", "session is unaffected"],
)
def test_each_warning_fragment_is_required(guard, missing_fragment: str) -> None:
    full = (
        "project-toolkit@ai-agents WARNING: hooks DISABLED "
        "(your session is unaffected). Install Python >= 3.10"
    )
    degraded = full.replace(missing_fragment, "")
    with pytest.raises(guard.GuardError, match="did not warn"):
        guard.assert_degraded(0, degraded)


def test_scrub_path_drops_a_directory_holding_an_interpreter(guard, tmp_path: Path) -> None:
    """Filter by evidence, not by directory name.

    The Windows App Execution Alias directory carries python.exe while its own
    name says nothing about Python, which is what defeated the previous name
    based filter.
    """
    innocent = tmp_path / "bin"
    innocent.mkdir()
    aliases = tmp_path / "WindowsApps"
    aliases.mkdir()
    (aliases / "python3").write_text("stub", encoding="utf-8")

    raw = os.pathsep.join([str(innocent), str(aliases)])
    cleaned = guard.scrub_path(raw)

    assert str(innocent) in cleaned
    assert str(aliases) not in cleaned


def test_scrub_path_drops_empty_entries(guard) -> None:
    assert guard.scrub_path(os.pathsep.join(["", "  "])) == ""


def test_assert_no_interpreter_raises_when_one_resolves(guard, tmp_path: Path) -> None:
    binstub = tmp_path / "python3"
    binstub.write_text("#!/bin/sh\n", encoding="utf-8")
    binstub.chmod(0o755)
    with pytest.raises(guard.GuardError, match="not vanilla"):
        guard.assert_no_interpreter({"PATH": str(tmp_path)})


def test_assert_no_interpreter_passes_on_a_clean_path(guard, tmp_path: Path) -> None:
    guard.assert_no_interpreter({"PATH": str(tmp_path)})


def test_extract_hook_command_survives_escaped_quotes(guard, tmp_path: Path) -> None:
    """The reason grep and sed cannot be used here.

    A `"[^"]*"` pattern truncates at the first escaped quote and yields an
    empty string, and an empty command exits 0, which satisfies a
    did-not-deny assertion while testing nothing.
    """
    command = 'if [ -z "$_ptr" ]; then echo "warn" >&2; exit 0; fi; "$_i" -u "$_ptr/x.py"'
    hooks = tmp_path / "hooks.json"
    hooks.write_text(
        f'{{"hooks": {{"PreToolUse": [{{"bash": {_json_quote(command)}}}]}}}}',
        encoding="utf-8",
    )
    assert guard.extract_hook_command(hooks, "PreToolUse", "bash") == command


def test_extract_hook_command_raises_when_absent(guard, tmp_path: Path) -> None:
    hooks = tmp_path / "hooks.json"
    hooks.write_text('{"hooks": {"PreToolUse": []}}', encoding="utf-8")
    with pytest.raises(guard.GuardError, match="no bash command"):
        guard.extract_hook_command(hooks, "PreToolUse", "bash")


def test_main_rejects_linux_container_mode_without_an_image(guard, tmp_path: Path) -> None:
    code = guard.main(
        [
            "--mode", "linux-container",
            "--install-root", str(tmp_path),
            "--consumer-cwd", str(tmp_path),
        ]
    )
    assert code == 2


def _json_quote(value: str) -> str:
    import json

    return json.dumps(value)
