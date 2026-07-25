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
from typing import Any

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
      SessionStart: SessionStart
      PreCompact: PreCompact
      UserPromptSubmit: UserPromptSubmit
      PreToolUse: PreToolUse
    eventDrop: []
    matcherPolicy: "inline-script-shim"
    versionField: 1
"""

# Writes a marker and emits branch-controlled text on both channels. Direct
# SessionStart rollback must preserve the side effect while suppressing the text.
_SCRIPT_BODY = """\
import os
import sys
from pathlib import Path

marker = os.environ.get("HOOK_MARKER")
if marker:
    Path(marker).write_text("HOOK_RAN", encoding="utf-8")
print("BRANCH_CONTROLLED_STDOUT")
print("BRANCH_CONTROLLED_STDERR", file=sys.stderr)
sys.exit(0)
"""

_USER_PROMPT_SCRIPT_BODY = """\
import json
import os
import sys
from pathlib import Path

raw = sys.stdin.read()
if raw:
    try:
        json.loads(raw)
    except json.JSONDecodeError:
        print("BRANCH_CONTROLLED_PARSE_ERROR", file=sys.stderr)
        sys.exit(2)
marker = os.environ.get("HOOK_MARKER")
if marker:
    Path(marker).write_text("HOOK_RAN", encoding="utf-8")
sys.exit(0)
"""

_HOOK_SCRIPTS = [
    ("SessionStart", "init.py", None),
    ("PreCompact", "compact.py", None),
    ("UserPromptSubmit", "prompt.py", None),
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
        body = _USER_PROMPT_SCRIPT_BODY if event == "UserPromptSubmit" else _SCRIPT_BODY
        script.write_text(body, encoding="utf-8")
        group: dict[str, object] = {
            "hooks": [{"type": "command", "command": f"python3 -u .claude/hooks/{event}/{fname}"}]
        }
        if matcher is not None:
            group["matcher"] = matcher
        settings_hooks.setdefault(event, []).append(group)

    (tmp_path / "settings.json").write_text(json.dumps({"hooks": settings_hooks}), encoding="utf-8")
    (tmp_path / "userland").mkdir()  # a cwd that is NOT the plugin root
    return cfg


def _generate(tmp_path: Path) -> dict[str, Any]:
    cfg = _materialize(tmp_path)
    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)
    assert rc == 0, "generator returned non-zero"
    out = tmp_path / "plugin" / "hooks" / "hooks.json"
    return json.loads(out.read_text(encoding="utf-8"))


def _all_entries(doc: dict[str, Any]) -> list[dict[str, str]]:
    hooks = doc["hooks"]
    assert isinstance(hooks, dict), "hooks must be a dict"
    entries: list[dict[str, str]] = []
    for event_entries in hooks.values():
        entries.extend(event_entries)
    assert entries, "fixture produced no hook entries"
    return entries


def _first_bash_command(doc: dict[str, object], event: str) -> str:
    hooks = doc.get("hooks")
    if not isinstance(hooks, dict):
        raise AssertionError("hooks must be a dict")
    entries = hooks.get(event)
    if not isinstance(entries, list) or not entries:
        raise AssertionError(f"{event} must contain hook entries")
    entry = entries[0]
    if not isinstance(entry, dict):
        raise AssertionError(f"{event} entry must be a dict")
    command = entry.get("bash")
    if not isinstance(command, str):
        raise AssertionError(f"{event} entry must contain a bash command")
    return command


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


@pytest.mark.parametrize("event", ["SessionStart", "PreCompact", "UserPromptSubmit"])
def test_direct_rollback_runs_silently_with_side_effects(
    tmp_path: Path,
    event: str,
) -> None:
    """A direct rollback command retains work without leaking repository prose."""
    doc = _generate(tmp_path)
    plugin_root = str(tmp_path / "plugin")
    userland = tmp_path / "userland"
    env = _contract_env(copilot_root=plugin_root, claude_root=plugin_root)
    marker = tmp_path / f"{event}-ran.txt"
    env["HOOK_MARKER"] = str(marker)
    proc = subprocess.run(
        ["bash", "-c", _first_bash_command(doc, event)],
        env=env,
        cwd=userland,
        capture_output=True,
        text=True,
        timeout=20,
        input="",
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert marker.read_text(encoding="utf-8") == "HOOK_RAN"
    assert proc.stdout == ""
    assert proc.stderr == ""


def test_user_prompt_direct_failure_is_silent_and_nonzero(tmp_path: Path) -> None:
    doc = _generate(tmp_path)
    plugin_root = str(tmp_path / "plugin")
    userland = tmp_path / "userland"
    env = _contract_env(copilot_root=plugin_root, claude_root=plugin_root)

    proc = subprocess.run(
        ["bash", "-c", _first_bash_command(doc, "UserPromptSubmit")],
        env=env,
        cwd=userland,
        capture_output=True,
        text=True,
        timeout=20,
        input="{bad json",
        check=False,
    )

    assert proc.returncode == 2
    assert proc.stdout == ""
    assert proc.stderr == ""


def test_committed_pretooluse_timeout_includes_dispatcher_headroom() -> None:
    """The shipped dispatcher has time beyond its shim budgets."""
    hooks_root = REPO_ROOT / "src" / "copilot-cli" / "hooks"
    hooks_doc = json.loads((hooks_root / "hooks.json").read_text(encoding="utf-8"))
    manifest = json.loads(
        (hooks_root / "PreToolUse" / "_manifest.json").read_text(encoding="utf-8")
    )

    shim_timeouts = list(manifest["timeouts"].values())
    timeout_sec = hooks_doc["hooks"]["PreToolUse"][0]["timeoutSec"]

    assert shim_timeouts
    assert timeout_sec > sum(shim_timeouts)


def test_negative_control_bare_relative_path_fails(tmp_path: Path) -> None:
    """The pre-fix bare ``./hooks/...`` form fails the same harness (teeth)."""
    _generate(tmp_path)  # materialize the plugin tree; return value unused here
    plugin_root = str(tmp_path / "plugin")
    userland = tmp_path / "userland"
    env = _contract_env(copilot_root=plugin_root, claude_root=plugin_root)
    # Reconstruct the regression: strip the plugin-root anchor, keep the path.
    bare = 'python3 -u "./hooks/SessionStart/init.py"'
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


def test_anchor_is_load_bearing_when_no_plugin_root_var_set(tmp_path: Path) -> None:
    """With neither plugin-root var set, the anchored path must NOT resolve.

    This distinguishes "given the variable, the path resolves" (the positive
    tests, which set the variable themselves) from "the variable is what makes it
    resolve". With both vars unset the bash fallback expands to ``/hooks/...``
    (absolute, off the filesystem root), so the anchored suffix is no longer
    under any plugin root. Without this control the suite could pass while
    production breaks if a host CLI stopped exporting the variable (the variable
    would not actually be load-bearing).
    NB: this verifies path resolution, not that the host CLI *sets* the variable;
    only the real-CLI e2e (tests/e2e/test_cli_hook_e2e.py) verifies vendor behavior.
    """
    doc = _generate(tmp_path)
    userland = tmp_path / "userland"
    env = _contract_env(copilot_root=None, claude_root=None)
    command = _first_bash_command(doc, "SessionStart")
    resolved = _bash_resolve(_path_arg(command), env, userland)
    # Assert the fallback EXPANSION VALUE directly rather than probing the host
    # root filesystem (a /hooks/... file on the runner would otherwise flake the
    # test). With no plugin-root var the prefix collapses to empty, so the path
    # is rooted at /hooks/ instead of under the plugin root: that proves the var
    # is the load-bearing prefix.
    assert resolved.startswith("/hooks/"), (
        f"expected fallback to collapse to /hooks/..., got {resolved!r}; "
        "the env var is not load-bearing"
    )
    assert not resolved.startswith(str(userland)), (
        f"anchored path unexpectedly resolved under userland: {resolved!r}"
    )


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


def test_stale_plugin_root_failure_names_the_missing_path(tmp_path: Path) -> None:
    """A stale plugin root fails closed AND the error names the full path.

    ``agent-harness-reference`` documents this failure mode and rejects an
    existence check in the launcher command strings on the grounds that the
    interpreter error already names the missing path (issues #3321, #3332).
    That rejection is only sound while the claim holds. This test makes the
    claim falsifiable: if a future interpreter or launcher shape stopped
    naming the path, the guard argument would have to be revisited and this
    goes red first.

    Uses the committed hooks.json dispatcher command (the shipped artifact)
    instead of generating via _generate(), which omits dispatcher: true.
    This aligns the test with what actually ships (ADR-068).
    """
    # Read the committed hooks.json - the shipped artifact uses the dispatcher
    hooks_root = REPO_ROOT / "src" / "copilot-cli" / "hooks"
    hooks_doc = json.loads((hooks_root / "hooks.json").read_text(encoding="utf-8"))

    stale_root = tmp_path / "moved-away"
    assert not stale_root.exists()
    env = _contract_env(copilot_root=str(stale_root), claude_root=str(stale_root))
    userland = tmp_path / "userland"
    userland.mkdir(parents=True, exist_ok=True)

    command = _first_bash_command(hooks_doc, "PreToolUse")
    proc = subprocess.run(
        ["bash", "-c", command],
        env=env,
        cwd=userland,
        input="{}",
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )

    assert proc.returncode != 0, "a stale plugin root must fail, not pass silently"
    expected_path = _bash_resolve(_path_arg(command), env, userland)
    assert str(stale_root) in expected_path, expected_path
    assert expected_path in proc.stderr, (
        "interpreter error must name the missing path, otherwise the "
        f"launcher-guard rejection is unsound. stderr={proc.stderr!r}"
    )
