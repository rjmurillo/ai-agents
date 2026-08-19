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
import subprocess
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


def test_event_is_registered_true_for_a_populated_event(guard, tmp_path: Path) -> None:
    hooks = tmp_path / "hooks.json"
    hooks.write_text('{"hooks": {"PreToolUse": [{"bash": "echo hi"}]}}', encoding="utf-8")
    assert guard.event_is_registered(hooks, "PreToolUse") is True


def test_event_is_registered_false_for_a_missing_key(guard, tmp_path: Path) -> None:
    hooks = tmp_path / "hooks.json"
    hooks.write_text('{"hooks": {}}', encoding="utf-8")
    assert guard.event_is_registered(hooks, "PreToolUse") is False


def test_event_is_registered_false_for_an_empty_list(guard, tmp_path: Path) -> None:
    hooks = tmp_path / "hooks.json"
    hooks.write_text('{"hooks": {"PreToolUse": []}}', encoding="utf-8")
    assert guard.event_is_registered(hooks, "PreToolUse") is False


def test_event_is_registered_raises_on_a_malformed_hooks_mapping(guard, tmp_path: Path) -> None:
    """A non-dict 'hooks' value is a corrupt manifest, not an empty one.

    Reading it as "nothing registered" would let a genuinely broken manifest
    pass the vanilla guard silently instead of failing closed.
    """
    hooks = tmp_path / "hooks.json"
    hooks.write_text('{"hooks": "not-a-mapping"}', encoding="utf-8")
    with pytest.raises(guard.GuardError, match="malformed"):
        guard.event_is_registered(hooks, "PreToolUse")


def test_event_is_registered_raises_when_the_event_value_is_not_a_list(
    guard, tmp_path: Path
) -> None:
    """A present event whose value is a dict, not a list, is malformed too.

    ``{"PreToolUse": {}}`` is not "nothing registered": the key exists but its
    value has the wrong shape for a hook-command list. Before this control,
    `isinstance(entries, list)` on a dict returned False, so this shape read
    as "not registered" and the guard passed vacuously (skipped Docker/
    PowerShell entirely) instead of failing closed on a broken manifest.
    """
    hooks = tmp_path / "hooks.json"
    hooks.write_text('{"hooks": {"PreToolUse": {}}}', encoding="utf-8")
    with pytest.raises(guard.GuardError, match="malformed 'PreToolUse' entry"):
        guard.event_is_registered(hooks, "PreToolUse")


def test_main_passes_vacuously_when_no_pretooluse_hooks_are_registered(
    guard, tmp_path: Path
) -> None:
    """ADR-097: zero tool-use hooks is a valid, deliberately-shipped state.

    Nothing registered means nothing to prove vanilla-safe, and the guard
    must not spin up Docker or drive PowerShell to test an empty manifest.
    """
    install_root = tmp_path / "install"
    (install_root / "hooks").mkdir(parents=True)
    (install_root / "hooks" / "hooks.json").write_text(
        '{"hooks": {}}', encoding="utf-8"
    )
    code = guard.main(
        [
            "--mode", "windows-path",
            "--install-root", str(install_root),
            "--consumer-cwd", str(tmp_path),
        ]
    )
    assert code == 0


def test_main_fails_when_the_manifest_is_missing(guard, tmp_path: Path) -> None:
    """A missing manifest is a real failure, never read as zero-hooks-vacuous."""
    install_root = tmp_path / "install"
    (install_root / "hooks").mkdir(parents=True)
    code = guard.main(
        [
            "--mode", "windows-path",
            "--install-root", str(install_root),
            "--consumer-cwd", str(tmp_path),
        ]
    )
    assert code == 1


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


def test_materialize_installed_plugin_cli_exits_nonzero_on_a_bad_source(tmp_path: Path) -> None:
    """Drive the real CLI so the exit-contract ratchet can see it.

    A missing plugin source must fail loudly. A materializer that silently
    produces an empty install would make every downstream guard row assert
    against nothing.
    """
    script = _REPO_ROOT / "scripts" / "ci" / "materialize_installed_plugin.py"
    proc = subprocess.run(
        [
            sys.executable, str(script),
            "--plugin-source", str(tmp_path / "does-not-exist"),
            "--install-root", str(tmp_path / "install"),
            "--consumer-cwd", str(tmp_path / "consumer"),
        ],
        capture_output=True, text=True, check=False,
    )
    assert proc.returncode != 0
    assert "not a directory" in (proc.stdout + proc.stderr)


def test_materialize_installed_plugin_cli_exits_nonzero_without_a_manifest(tmp_path: Path) -> None:
    source = tmp_path / "plugin"
    (source / "hooks").mkdir(parents=True)
    script = _REPO_ROOT / "scripts" / "ci" / "materialize_installed_plugin.py"
    proc = subprocess.run(
        [
            sys.executable, str(script),
            "--plugin-source", str(source),
            "--install-root", str(tmp_path / "install"),
            "--consumer-cwd", str(tmp_path / "consumer"),
        ],
        capture_output=True, text=True, check=False,
    )
    assert proc.returncode != 0
    assert "manifest" in (proc.stdout + proc.stderr)


def test_vanilla_hook_guard_cli_exits_nonzero_without_an_image(tmp_path: Path) -> None:
    script = _REPO_ROOT / "scripts" / "ci" / "vanilla_hook_guard.py"
    proc = subprocess.run(
        [
            sys.executable, str(script),
            "--mode", "linux-container",
            "--install-root", str(tmp_path),
            "--consumer-cwd", str(tmp_path),
        ],
        capture_output=True, text=True, check=False,
    )
    assert proc.returncode != 0


def test_missing_docker_is_unavailable_not_a_guard_failure(
    guard, monkeypatch, tmp_path: Path
) -> None:
    """An empty result and a failed command are different things.

    This is the defect the first version of this script shipped with. Under
    local act there is no Docker, so `docker run` failed, stdout was empty,
    and the emptiness check reported "image is not vanilla; an interpreter
    resolved: " with nothing after the colon. That sends the reader hunting a
    container-image problem that does not exist.
    """
    monkeypatch.setattr(guard.shutil, "which", lambda name: None)
    with pytest.raises(guard.EnvironmentUnavailableError, match="docker is not available"):
        guard.run_linux_container("debian:example", tmp_path, tmp_path)


def test_failed_docker_probe_is_unavailable_not_not_vanilla(
    guard, monkeypatch, tmp_path: Path
) -> None:
    """A nonzero docker exit must not be read as an interpreter resolving."""
    monkeypatch.setattr(guard.shutil, "which", lambda name: "/usr/bin/docker")

    class _Failed:
        returncode = 125
        stdout = ""
        stderr = "Cannot connect to the Docker daemon"

    monkeypatch.setattr(guard.subprocess, "run", lambda *a, **k: _Failed())
    with pytest.raises(guard.EnvironmentUnavailableError, match="docker exited 125"):
        guard.run_linux_container("debian:example", tmp_path, tmp_path)


def test_a_real_interpreter_in_the_image_is_a_guard_failure(
    guard, monkeypatch, tmp_path: Path
) -> None:
    """The not-vanilla path must still fire when docker genuinely succeeds."""
    monkeypatch.setattr(guard.shutil, "which", lambda name: "/usr/bin/docker")

    class _Resolved:
        returncode = 0
        stdout = "/usr/bin/python3\n"
        stderr = ""

    monkeypatch.setattr(guard.subprocess, "run", lambda *a, **k: _Resolved())
    with pytest.raises(guard.GuardError, match="not vanilla"):
        guard.run_linux_container("debian:example", tmp_path, tmp_path)
