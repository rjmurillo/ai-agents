#!/usr/bin/env python3
"""Runtime-contract regression guard for issue #2205 (Copilot CLI hook paths).

``test_generate_hooks_plugin_root.py`` asserts the *literal* command the
generator emits. That cannot prove the path RESOLVES at runtime, and it
cannot catch a wrong environment-variable name. A test that pins output to
itself is the canonical-source-mirror anti-pattern (see
``.claude/rules/canonical-source-mirror.md`` and the PR #1887 retro). The
original #2205 fix shipped exactly that kind of guard.

This test exercises the EMPIRICALLY VERIFIED Copilot CLI contract instead.
Measured against GitHub Copilot CLI 1.0.57 by installing a probe plugin
whose hook dumps its environment:

  * Copilot launches a plugin hook with ``cwd`` set to the user's working
    directory, NOT the plugin install dir.
  * It exports ``COPILOT_PLUGIN_ROOT`` and an alias ``CLAUDE_PLUGIN_ROOT``,
    both pointing at the plugin install dir (the directory that contains
    ``hooks/``).

The public hooks reference does not document these variables; the contract
is verified by experiment, not by the docs. This test reproduces that
contract: it generates hooks, then runs each emitted command from a
non-plugin ``cwd`` with the contract environment, and asserts the vendored
script is found. A negative control proves a bare ``./hooks/...`` command
fails the same harness, so the guard has teeth.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "build"))

import generate_hooks  # noqa: E402

# Faithful fixture: ``outputScripts`` ends in ``hooks`` exactly as the real
# ``templates/platforms/copilot-cli.yaml`` does, so the hardcoded ``hooks/``
# path prefix that ``_build_copilot_entry`` emits lines up with the on-disk
# script location. The plugin root is therefore ``<tmp>/plugin``.
_PLATFORM_YAML = """\
schemaVersion: "1.0"
provider: "test"
artifacts:
  hooks:
    settingsSource: "settings.json"
    scriptSource: "hooks_src"
    outputConfig: "plugin/hooks/hooks.json"
    outputScripts: "plugin/hooks"
    eventRemap:
      SessionStart: sessionStart
      PreToolUse: preToolUse
    eventDrop: []
    matcherPolicy: "inline-script-shim"
    versionField: 1
"""

# Prints a marker and exits 0, so a successful launch is observable.
_SCRIPT_BODY = "import sys\nprint('HOOK_RAN')\nsys.exit(0)\n"

_HOOK_SCRIPTS = [
    ("SessionStart", "init.py", None),
    ("PreToolUse", "guard.py", "Bash"),  # matcher -> inline-script-shim
]


def _materialize(tmp_path: Path) -> Path:
    """Write platform config, settings.json, script tree, and a user cwd."""
    cfg = tmp_path / "platform.yaml"
    cfg.write_text(_PLATFORM_YAML, encoding="utf-8")

    settings_hooks: dict[str, list[dict[str, object]]] = {}
    for event, fname, matcher in _HOOK_SCRIPTS:
        script = tmp_path / "hooks_src" / event / fname
        script.parent.mkdir(parents=True, exist_ok=True)
        script.write_text(_SCRIPT_BODY, encoding="utf-8")
        group: dict[str, object] = {
            "hooks": [
                {"type": "command", "command": f"python3 -u .claude/hooks/{event}/{fname}"}
            ]
        }
        if matcher is not None:
            group["matcher"] = matcher
        settings_hooks.setdefault(event, []).append(group)

    (tmp_path / "settings.json").write_text(
        json.dumps({"hooks": settings_hooks}), encoding="utf-8"
    )
    (tmp_path / "userland").mkdir()  # a cwd that is NOT the plugin root
    return cfg


def _generate(tmp_path: Path) -> dict[str, object]:
    cfg = _materialize(tmp_path)
    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)
    assert rc == 0, "generator returned non-zero"
    out = tmp_path / "plugin" / "hooks" / "hooks.json"
    return json.loads(out.read_text(encoding="utf-8"))


def _all_entries(doc: dict[str, object]) -> list[dict[str, str]]:
    hooks = doc["hooks"]
    assert isinstance(hooks, dict), "hooks must be a dict"
    entries: list[dict[str, str]] = []
    for event_entries in hooks.values():
        entries.extend(event_entries)
    assert entries, "fixture produced no hook entries"
    return entries


def _path_arg(command: str) -> str:
    """Return the single double-quoted argument from a generated command.

    Generated commands have exactly one double-quoted token (the script
    path); neither the launcher nor the path expression contains a quote.
    """
    parts = command.split('"')
    assert len(parts) == 3, f"expected one quoted arg in: {command!r}"
    return parts[1]


def _contract_env(*, copilot_root: str | None, claude_root: str | None) -> dict[str, str]:
    env = os.environ.copy()
    env.pop("COPILOT_PLUGIN_ROOT", None)
    env.pop("CLAUDE_PLUGIN_ROOT", None)
    if copilot_root is not None:
        env["COPILOT_PLUGIN_ROOT"] = copilot_root
    if claude_root is not None:
        env["CLAUDE_PLUGIN_ROOT"] = claude_root
    return env


def _bash_resolve(path_expr: str, env: dict[str, str], cwd: Path) -> str:
    """Expand a bash path expression under ``env`` and ``cwd``."""
    proc = subprocess.run(
        ["bash", "-c", f'printf "%s" "{path_expr}"'],
        env=env,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def test_every_bash_command_resolves_to_an_existing_script(tmp_path: Path) -> None:
    """Every emitted bash path resolves to a real file under the contract."""
    doc = _generate(tmp_path)
    plugin_root = str(tmp_path / "plugin")
    userland = tmp_path / "userland"
    env = _contract_env(copilot_root=plugin_root, claude_root=plugin_root)
    for entry in _all_entries(doc):
        resolved = _bash_resolve(_path_arg(entry["bash"]), env, userland)
        assert Path(resolved).is_file(), f"unresolved: {resolved!r} from {entry['bash']!r}"


def test_bash_falls_back_to_claude_plugin_root(tmp_path: Path) -> None:
    """When COPILOT_PLUGIN_ROOT is unset, CLAUDE_PLUGIN_ROOT resolves it."""
    doc = _generate(tmp_path)
    plugin_root = str(tmp_path / "plugin")
    userland = tmp_path / "userland"
    env = _contract_env(copilot_root=None, claude_root=plugin_root)
    for entry in _all_entries(doc):
        resolved = _bash_resolve(_path_arg(entry["bash"]), env, userland)
        assert Path(resolved).is_file(), f"fallback failed: {resolved!r}"


def test_sessionstart_bash_command_launches_the_script(tmp_path: Path) -> None:
    """A non-shim command actually executes the vendored script from a user cwd."""
    doc = _generate(tmp_path)
    plugin_root = str(tmp_path / "plugin")
    userland = tmp_path / "userland"
    env = _contract_env(copilot_root=plugin_root, claude_root=plugin_root)
    entry = doc["hooks"]["sessionStart"][0]  # matcher-less: copied verbatim
    proc = subprocess.run(
        ["bash", "-c", entry["bash"]],
        env=env,
        cwd=userland,
        capture_output=True,
        text=True,
        timeout=20,
        input="",
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "HOOK_RAN" in proc.stdout


def test_negative_control_bare_relative_path_fails(tmp_path: Path) -> None:
    """The pre-fix bare ``./hooks/...`` form fails the same harness (teeth)."""
    _generate(tmp_path)  # materialize the plugin tree; return value unused here
    plugin_root = str(tmp_path / "plugin")
    userland = tmp_path / "userland"
    env = _contract_env(copilot_root=plugin_root, claude_root=plugin_root)
    # Reconstruct the regression: strip the plugin-root anchor, keep the path.
    bare = 'python3 -u "./hooks/sessionStart/init.py"'
    proc = subprocess.run(
        ["bash", "-c", bare],
        env=env,
        cwd=userland,
        capture_output=True,
        text=True,
        timeout=20,
        input="",
        check=False,
    )
    assert proc.returncode != 0, "bare relative path unexpectedly resolved"


@pytest.mark.skipif(shutil.which("pwsh") is None, reason="pwsh not installed")
def test_every_powershell_command_resolves_under_pwsh(tmp_path: Path) -> None:
    """Every emitted powershell path resolves under pwsh, incl. the fallback."""
    doc = _generate(tmp_path)
    plugin_root = str(tmp_path / "plugin")
    userland = tmp_path / "userland"
    scenarios = [
        _contract_env(copilot_root=plugin_root, claude_root=plugin_root),
        _contract_env(copilot_root=None, claude_root=plugin_root),  # fallback
    ]
    for env in scenarios:
        for entry in _all_entries(doc):
            ps_expr = _path_arg(entry["powershell"])
            proc = subprocess.run(
                [
                    "pwsh",
                    "-NoProfile",
                    "-Command",
                    f'if (Test-Path "{ps_expr}") {{ "OK" }} else {{ "MISSING" }}',
                ],
                env=env,
                cwd=userland,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            assert proc.returncode == 0, proc.stderr
            assert "OK" in proc.stdout, f"unresolved powershell path: {ps_expr!r}"
