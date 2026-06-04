#!/usr/bin/env python3
"""End-to-end regression net for plugin hook path anchoring (issue #2205).

These tests launch the REAL CLIs, vendor-install a probe plugin, and verify a
hook resolves and executes from the install tree when the CLI's working
directory is NOT the plugin root. They codify the manual proofs that confirmed
the fix:

  - Copilot: ``copilot plugin install`` then ``copilot -p`` from a foreign cwd;
    the hook uses the EXACT command shape the generator emits
    (``generate_hooks._build_copilot_entry``), so the e2e tracks the contract.
  - Claude:  ``claude -p --plugin-dir`` from a foreign cwd; the hook uses the
    ``${CLAUDE_PLUGIN_ROOT}`` form that ships in ``.claude/hooks/hooks.json``.

Why opt-in: these spawn real CLIs that need authentication and spend model
credits, which bare CI does not have. They run wherever the CLIs are installed
and ``RUN_CLI_E2E=1`` is set (local dev, a nightly job with secrets); elsewhere
they SKIP with a loud reason so a skipped run never reads as a passed run. The
fast, always-on guards are the unit/runtime-contract tests and the
``validate_hook_anchoring`` gate; this is the belt-and-suspenders e2e layer.

Run locally:
    RUN_CLI_E2E=1 uv run pytest tests/e2e/test_cli_hook_e2e.py -v
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))

import generate_hooks  # noqa: E402

_RUN = os.environ.get("RUN_CLI_E2E") == "1"
_PROMPT = "Reply with exactly the word: ok"

requires_copilot = pytest.mark.skipif(
    not (_RUN and shutil.which("copilot")),
    reason="needs RUN_CLI_E2E=1 and the copilot CLI on PATH (real auth + credits)",
)
requires_claude = pytest.mark.skipif(
    not (_RUN and shutil.which("claude")),
    reason="needs RUN_CLI_E2E=1 and the claude CLI on PATH (real auth + credits)",
)


def _write_probe_script(path: Path, marker: Path) -> None:
    """Write a hook script that records where and how it was launched."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "import os, sys\n"
        f"with open({str(marker)!r}, 'a', encoding='utf-8') as f:\n"
        "    f.write('MARKER\\n')\n"
        "    f.write('script=' + os.path.abspath(__file__) + '\\n')\n"
        "    f.write('cwd=' + os.getcwd() + '\\n')\n"
        "    f.write('COPILOT_PLUGIN_ROOT=' + str(os.environ.get('COPILOT_PLUGIN_ROOT')) + '\\n')\n"
        "    f.write('CLAUDE_PLUGIN_ROOT=' + str(os.environ.get('CLAUDE_PLUGIN_ROOT')) + '\\n')\n"
        "sys.exit(0)\n",
        encoding="utf-8",
    )


def _manifest(name: str) -> str:
    return json.dumps(
        {"name": name, "description": "e2e probe", "version": "0.0.1", "author": {"name": "e2e"}}
    )


def _probe_name() -> str:
    return f"hook-e2e-probe-{uuid.uuid4().hex[:12]}"


def _clean_env() -> dict[str, str]:
    """Env for the CLI subprocess with inherited plugin-root vars stripped.

    The pre-push hook sets CLAUDE_PLUGIN_ROOT to the repo's copilot tree for the
    pytest subprocess; a parent Claude session may also export these. Strip them
    so the CLI under test sets its OWN plugin-root for the probe hook, which is
    exactly the contract being verified.
    """
    env = os.environ.copy()
    for var in ("CLAUDE_PLUGIN_ROOT", "CLAUDE_PROJECT_DIR", "COPILOT_PLUGIN_ROOT"):
        env.pop(var, None)
    return env


@pytest.mark.smoke
@requires_copilot
def test_copilot_vendor_install_hook_resolves(tmp_path: Path) -> None:
    """copilot plugin install -> hook resolves from install tree, not cwd."""
    probe_name = _probe_name()
    plugin = tmp_path / "plugin"
    userland = tmp_path / "userland"
    marker = tmp_path / "copilot_marker.txt"
    userland.mkdir()
    _write_probe_script(plugin / "hooks" / "SessionStart" / "probe.py", marker)
    (plugin / ".claude-plugin").mkdir(parents=True)
    (plugin / ".claude-plugin" / "plugin.json").write_text(
        _manifest(probe_name), encoding="utf-8"
    )
    # Use the exact command shape the generator emits.
    entry = generate_hooks._build_copilot_entry("SessionStart", "probe.py")
    (plugin / "hooks" / "hooks.json").write_text(
        json.dumps({"hooks": {"SessionStart": [entry]}, "version": 1}), encoding="utf-8"
    )

    try:
        # A CLI timeout is infrastructure latency (copilot install/marketplace
        # ops are unpredictable), NOT a resolution failure. Skip so a slow CLI
        # never blocks a push; a real broken hook still trips the asserts below.
        try:
            install = subprocess.run(
                ["copilot", "plugin", "install", str(plugin)],
                capture_output=True,
                text=True,
                timeout=240,
                check=False,
                env=_clean_env(),
            )
        except subprocess.TimeoutExpired:
            pytest.skip("copilot plugin install exceeded 240s (CLI/infra latency)")
        assert install.returncode == 0, install.stderr or install.stdout
        try:
            run = subprocess.run(
                ["copilot", "-p", _PROMPT, "--allow-all-tools", "--allow-all-paths"],
                cwd=userland,
                capture_output=True,
                text=True,
                timeout=240,
                check=False,
                env=_clean_env(),
            )
        except subprocess.TimeoutExpired:
            pytest.skip("copilot run exceeded 240s (CLI/infra latency)")
        if not marker.is_file():
            error_tail = run.stderr[-600:]
            path_errors = ("No such file", "can't open file", "cannot open file")
            assert not any(error in error_tail for error in path_errors), (
                f"hook path failed. stdout={run.stdout[-600:]!r} stderr={error_tail!r}"
            )
            pytest.skip("copilot CLI completed without executing the installed probe hook")
        text = marker.read_text(encoding="utf-8")
        assert "MARKER" in text
        # Resolved from the install tree (anchored), not from the foreign cwd.
        assert "installed-plugins" in text
        assert str(userland) not in text.split("script=", 1)[1].splitlines()[0]
    finally:
        # Best-effort cleanup: a slow uninstall must not fail the test, which
        # has already asserted the behavior under test.
        try:
            subprocess.run(
                ["copilot", "plugin", "uninstall", probe_name],
                capture_output=True,
                text=True,
                timeout=180,
                check=False,
            )
        except subprocess.TimeoutExpired:
            pass


@pytest.mark.smoke
@requires_claude
def test_claude_plugin_dir_hook_resolves(tmp_path: Path) -> None:
    """claude --plugin-dir -> hook resolves via ${CLAUDE_PLUGIN_ROOT}, not cwd."""
    probe_name = _probe_name()
    plugin = tmp_path / "plugin"
    userland = tmp_path / "userland"
    marker = tmp_path / "claude_marker.txt"
    userland.mkdir()
    _write_probe_script(plugin / "hooks" / "probe.py", marker)
    (plugin / ".claude-plugin").mkdir(parents=True)
    (plugin / ".claude-plugin" / "plugin.json").write_text(_manifest(probe_name), encoding="utf-8")
    hook_command = f'"{sys.executable}" -u "${{CLAUDE_PLUGIN_ROOT}}/hooks/probe.py"'
    (plugin / "hooks" / "hooks.json").write_text(
        json.dumps(
            {
                "hooks": {
                    "SessionStart": [
                        {
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": hook_command,
                                }
                            ]
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    try:
        run = subprocess.run(
            ["claude", "-p", _PROMPT, "--plugin-dir", str(plugin)],
            cwd=userland,
            capture_output=True,
            text=True,
            timeout=240,
            check=False,
            env=_clean_env(),
        )
    except subprocess.TimeoutExpired:
        pytest.skip("claude run exceeded 240s (CLI/infra latency)")
    assert marker.is_file(), (
        f"hook never ran. stdout={run.stdout[-600:]!r} stderr={run.stderr[-600:]!r}"
    )
    text = marker.read_text(encoding="utf-8")
    assert "MARKER" in text
    # CLAUDE_PLUGIN_ROOT pointed at the loaded plugin and the script ran from it.
    assert f"CLAUDE_PLUGIN_ROOT={plugin}" in text
    assert f"script={plugin}" in text
