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

Hook-event choice under ``-p`` (issue #2378). The Copilot probe binds its hook
to ``UserPromptSubmit``, NOT ``SessionStart``. The GitHub Copilot CLI hooks
reference is explicit: "Prompt hooks fire only for new interactive sessions.
They do not fire on resume, and they do not fire in non-interactive prompt mode
(``-p``)." ``SessionStart`` is the one event documented to be skipped in ``-p``;
an earlier probe bound to ``SessionStart`` made the test assert a marker that
``copilot -p`` never dispatches, so it failed even when the CLI returned ``ok``.
``UserPromptSubmit`` fires in ``-p`` (the prompt is submitted) and exercises the
identical path-anchoring contract, because ``_build_copilot_entry`` is
event-name-agnostic: the only difference is the directory segment in the script
path. Source: https://docs.github.com/en/copilot/reference/hooks-configuration
(verified 2026-06-04). The Claude probe keeps ``SessionStart`` because Claude
Code dispatches it under ``claude -p``.

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

from scripts.cli_exec import resolve_executable  # noqa: E402

_RUN = os.environ.get("RUN_CLI_E2E") == "1"
_PROMPT = "Reply with exactly the word: ok"

# Copilot CLI does NOT dispatch SessionStart in non-interactive print mode
# (-p); UserPromptSubmit does fire there. See module docstring and issue #2378.
_COPILOT_EVENT = "UserPromptSubmit"

# The Copilot vendor install tree lives under this path segment. Verified
# empirically (decision-copilot-cli-hook-plugin-root-contract):
# ~/.copilot/installed-plugins/.../<plugin>/hooks/... is where the anchored
# script resolves, so a script that ran from the install tree records it.
_COPILOT_INSTALL_SEGMENT = "installed-plugins"
_DIAGNOSTIC_MAX_INSTALL_HOOKS = 80
_DIAGNOSTIC_MAX_FILE_CHARS = 4000

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


def _copilot_install_roots() -> list[Path]:
    """Candidate Copilot vendor-install roots to dump on failure.

    Copilot installs plugins under ~/.copilot/installed-plugins (and honors
    COPILOT_HOME when set). Both are listed so a marker-miss failure shows the
    on-disk install tree, even when the test does not know the exact path.
    """
    roots: list[Path] = []
    copilot_home = os.environ.get("COPILOT_HOME")
    if copilot_home:
        roots.append(Path(copilot_home) / "installed-plugins")
    roots.append(Path.home() / ".copilot" / "installed-plugins")
    return roots


def _append_text_file_diagnostic(lines: list[str], label: str, path: Path) -> None:
    try:
        content = path.read_text(encoding="utf-8")[-_DIAGNOSTIC_MAX_FILE_CHARS:]
    except (OSError, UnicodeDecodeError) as exc:
        lines.append(f"{label}_error={exc}")
        return
    lines.append(f"{label}={content}")


def _copilot_failure_diagnostics(
    probe_name: str,
    plugin: Path,
    userland: Path,
    run: subprocess.CompletedProcess[str],
) -> str:
    """Build a self-diagnosing message for a Copilot hook marker miss (#2378).

    Surfaces the installed hooks.json files, the authored hooks.json the install
    was built from, and the CLI output, so a failure says WHY the hook did not
    run instead of only that it did not.
    """
    lines: list[str] = [
        "Copilot hook never wrote its marker.",
        f"probe_name={probe_name}",
        f"event={_COPILOT_EVENT}",
        f"foreign_cwd={userland}",
        f"authored_hooks_json={plugin / 'hooks' / 'hooks.json'}",
    ]
    authored = plugin / "hooks" / "hooks.json"
    try:
        authored_is_file = authored.is_file()
    except OSError as exc:
        lines.append(f"authored_hooks_json_error={exc}")
    else:
        if authored_is_file:
            _append_text_file_diagnostic(lines, "authored_hooks_json_content", authored)
    for root in _copilot_install_roots():
        try:
            root_is_dir = root.is_dir()
        except OSError as exc:
            lines.append(f"install_root_error={root}: {exc}")
            continue
        if not root_is_dir:
            lines.append(f"install_root_absent={root}")
            continue
        lines.append(f"install_root={root}")
        try:
            for index, path in enumerate(root.rglob("hooks.json")):
                if index >= _DIAGNOSTIC_MAX_INSTALL_HOOKS:
                    lines.append(f"  install_root_truncated_after={_DIAGNOSTIC_MAX_INSTALL_HOOKS}")
                    break
                lines.append(f"  {path}")
                try:
                    path_is_file = path.is_file()
                except OSError as exc:
                    lines.append(f"    file_error={exc}")
                    continue
                if path_is_file:
                    _append_text_file_diagnostic(lines, "    content", path)
        except OSError as exc:
            lines.append(f"  rglob_error={exc}")
    lines.append(f"stdout={run.stdout[-600:]!r}")
    lines.append(f"stderr={run.stderr[-600:]!r}")
    return "\n".join(lines)


@pytest.mark.smoke
@requires_copilot
def test_copilot_vendor_install_hook_resolves(tmp_path: Path) -> None:
    """copilot plugin install -> hook resolves from install tree, not cwd.

    Binds the probe to UserPromptSubmit (not SessionStart): copilot -p does not
    dispatch SessionStart, so a SessionStart marker would never appear under -p
    even when resolution is correct. See module docstring and issue #2378.
    """
    probe_name = _probe_name()
    plugin = tmp_path / "plugin"
    userland = tmp_path / "userland"
    marker = tmp_path / "copilot_marker.txt"
    userland.mkdir()
    _write_probe_script(plugin / "hooks" / _COPILOT_EVENT / "probe.py", marker)
    (plugin / "plugin.json").write_text(_manifest(probe_name), encoding="utf-8")
    # Use the exact command shape the generator emits, for this event.
    entry = generate_hooks._build_copilot_entry(_COPILOT_EVENT, "probe.py")
    (plugin / "hooks" / "hooks.json").write_text(
        json.dumps({"hooks": {_COPILOT_EVENT: [entry]}, "version": 1}), encoding="utf-8"
    )

    try:
        # A CLI timeout is infrastructure latency (copilot install/marketplace
        # ops are unpredictable), NOT a resolution failure. Skip so a slow CLI
        # never blocks a push; a real broken hook still trips the asserts below.
        try:
            install = subprocess.run(
                [resolve_executable("copilot"), "plugin", "install", str(plugin)],
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
                [
                    resolve_executable("copilot"),
                    "-p",
                    _PROMPT,
                    "--allow-all-tools",
                    "--allow-all-paths",
                ],
                cwd=userland,
                capture_output=True,
                text=True,
                timeout=240,
                check=False,
                env=_clean_env(),
            )
        except subprocess.TimeoutExpired:
            pytest.skip("copilot run exceeded 240s (CLI/infra latency)")
        assert marker.is_file(), _copilot_failure_diagnostics(probe_name, plugin, userland, run)
        text = marker.read_text(encoding="utf-8")
        assert "MARKER" in text
        # Resolved from the install tree (anchored), not from the foreign cwd.
        assert _COPILOT_INSTALL_SEGMENT in text, (
            f"hook ran but not from the vendor install tree. marker={text!r}"
        )
        assert str(userland) not in text.split("script=", 1)[1].splitlines()[0]
    finally:
        # Best-effort cleanup: a slow uninstall must not fail the test, which
        # has already asserted the behavior under test.
        try:
            subprocess.run(
                [resolve_executable("copilot"), "plugin", "uninstall", probe_name],
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
            [resolve_executable("claude"), "-p", _PROMPT, "--plugin-dir", str(plugin)],
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


# Always-on unit checks. They need no real CLI, so they run in bare CI and pin
# the correctness-by-construction facts the gated Copilot e2e depends on:
# the event choice, the generated command shape, and a runnable probe script.
# A break here means the e2e is asserting something that cannot succeed.


def test_copilot_probe_event_fires_in_print_mode() -> None:
    """The Copilot probe binds to an event copilot -p dispatches (#2378).

    SessionStart is the one hook the Copilot CLI hooks reference says does NOT
    fire in non-interactive prompt mode (-p). Binding the probe to it made the
    e2e assert a marker that -p never writes. Guard against a silent regression
    back to SessionStart.
    """
    assert _COPILOT_EVENT != "SessionStart"
    assert _COPILOT_EVENT == "UserPromptSubmit"


def test_copilot_failure_diagnostics_stays_best_effort(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Diagnostic failures report partial context instead of masking the marker miss."""

    class BrokenRoot:
        def __str__(self) -> str:
            return "broken-root"

        def is_dir(self) -> bool:
            return True

        def rglob(self, pattern: str):
            assert pattern == "hooks.json"
            raise OSError("boom")

    class UnreadableHook:
        name = "hooks.json"

        def __str__(self) -> str:
            return "unreadable/hooks.json"

        def is_file(self) -> bool:
            return True

        def read_text(self, encoding: str) -> str:
            raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "bad byte")

    class HookPath:
        name = "hooks.json"

        def __init__(self, index: int) -> None:
            self.index = index

        def __str__(self) -> str:
            return f"hook-{self.index}/hooks.json"

        def is_file(self) -> bool:
            return True

        def read_text(self, encoding: str) -> str:
            return f"content-{self.index}"

    class ManyHooksRoot:
        def __str__(self) -> str:
            return "many-hooks-root"

        def is_dir(self) -> bool:
            return True

        def rglob(self, pattern: str):
            assert pattern == "hooks.json"
            return iter(
                [UnreadableHook()]
                + [HookPath(index) for index in range(_DIAGNOSTIC_MAX_INSTALL_HOOKS + 2)]
            )

    monkeypatch.setattr(
        sys.modules[__name__],
        "_copilot_install_roots",
        lambda: [BrokenRoot(), ManyHooksRoot()],
    )
    run = subprocess.CompletedProcess(["copilot"], 1, stdout="out", stderr="err")

    diagnostics = _copilot_failure_diagnostics(
        "probe", tmp_path / "plugin", tmp_path / "userland", run
    )

    assert "rglob_error=boom" in diagnostics
    assert "content_error=" in diagnostics
    assert f"install_root_truncated_after={_DIAGNOSTIC_MAX_INSTALL_HOOKS}" in diagnostics
    assert f"hook-{_DIAGNOSTIC_MAX_INSTALL_HOOKS}/hooks.json" not in diagnostics


def test_copilot_entry_anchors_script_to_plugin_root() -> None:
    """The generated command resolves the probe from the install tree, not cwd.

    The shell commands must reference the script via the plugin-root env var with
    the COPILOT_PLUGIN_ROOT->CLAUDE_PLUGIN_ROOT fallback, and must NOT use a bare
    relative path (the bug class from issue #2205). This is the contract the
    Copilot e2e proves end to end; pinned here so a generator change that breaks
    anchoring fails in bare CI too.
    """
    entry = generate_hooks._build_copilot_entry(_COPILOT_EVENT, "probe.py")
    bash = entry["bash"]
    powershell = entry["powershell"]

    assert "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT}}" in bash
    assert f"/hooks/{_COPILOT_EVENT}/probe.py" in bash
    assert "$env:COPILOT_PLUGIN_ROOT" in powershell
    assert "$env:CLAUDE_PLUGIN_ROOT" in powershell
    assert f"/hooks/{_COPILOT_EVENT}/probe.py" in powershell
    # Negative control: a bare relative path is the exact shape that wedged
    # customer environments; the anchored form must not collapse to it.
    assert "./hooks/" not in bash
    assert "./hooks/" not in powershell


def test_probe_script_writes_marker_when_run(tmp_path: Path) -> None:
    """The probe the e2e installs actually writes a marker when executed.

    CLI-independent negative control: if the probe script were itself broken,
    the gated e2e marker assertion could never pass and the failure would be
    misattributed to the CLI. Run the probe directly and confirm it records the
    marker, its own path, and the plugin-root vars.
    """
    script = tmp_path / "hooks" / _COPILOT_EVENT / "probe.py"
    marker = tmp_path / "marker.txt"
    _write_probe_script(script, marker)

    env = os.environ.copy()
    env["COPILOT_PLUGIN_ROOT"] = str(tmp_path)
    result = subprocess.run(
        [sys.executable, "-u", str(script)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
        env=env,
    )

    assert result.returncode == 0, result.stderr
    assert marker.is_file()
    text = marker.read_text(encoding="utf-8")
    assert "MARKER" in text
    assert f"script={script}" in text
    assert f"COPILOT_PLUGIN_ROOT={tmp_path}" in text
