#!/usr/bin/env python3
"""End-to-end regression net for plugin hook path anchoring (issue #2205).

These tests launch the REAL CLIs and verify a
hook resolves and executes from the install tree when the CLI's working
directory is NOT the plugin root. They codify the manual proofs that confirmed
the fix:

  - Copilot: isolated ``copilot plugin install`` then plain ``copilot -p`` from
    a foreign cwd;
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
from pathlib import Path, PureWindowsPath

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
# tests/e2e is not on sys.path under --import-mode=importlib (no __init__.py), so
# add it for the sibling copilot_hook_probe import.
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))

import copilot_hook_probe  # noqa: E402
import generate_hooks  # noqa: E402

from scripts.cli_exec import resolve_executable  # noqa: E402

# Fired-hook probe primitives (issue #3148). The synthetic --plugin-dir marker
# probe lives in one place so this file and test_plugin_load_smoke.py share the
# same load signal. _COPILOT_EVENT is UserPromptSubmit because copilot -p does
# not dispatch SessionStart (issue #2378); see module docstring.
_COPILOT_EVENT = copilot_hook_probe.PROBE_EVENT
_PROMPT = copilot_hook_probe.PROBE_PROMPT
_clean_env = copilot_hook_probe.clean_env
_copilot_command = copilot_hook_probe.copilot_command
_manifest = copilot_hook_probe.manifest
_probe_name = copilot_hook_probe.probe_name
_write_probe_script = copilot_hook_probe.write_probe_script
_copilot_run_blocked = copilot_hook_probe.copilot_run_blocked
_copilot_run_blocked_headline = copilot_hook_probe.copilot_run_blocked_headline


def _skip_on_copilot_block(result: subprocess.CompletedProcess[str]) -> None:
    """Skip when an external or credential condition blocks Copilot.

    A rate limit, transport failure, or auth gate is not a branch defect.
    Skipping lets the pre-push proceed. The nightly workflow uses
    assert_smoke_ran.py to detect skipped smokes, so the nightly still fails red
    when the real CLI cannot run (issues #4504, #4483, #3275).

    Using pytest.skip rather than pytest.fail here is the contractual choice:
    fail would block every pre-push on external or auth state. The
    existing timeout paths in this file already follow the same pattern.
    """
    if _copilot_run_blocked(result):
        pytest.skip(_copilot_run_blocked_headline(result))


_RUN = os.environ.get("RUN_CLI_E2E") == "1"

_DIAGNOSTIC_MAX_FILE_CHARS = 4000

requires_copilot = pytest.mark.skipif(
    not (_RUN and shutil.which("copilot")),
    reason="needs RUN_CLI_E2E=1 and the copilot CLI on PATH (real auth + credits)",
)
requires_claude = pytest.mark.skipif(
    not (_RUN and shutil.which("claude")),
    reason="needs RUN_CLI_E2E=1 and the claude CLI on PATH (real auth + credits)",
)


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
    install_root: Path | None = None,
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
    if install_root is not None:
        lines.append(f"install_root={install_root}")
        try:
            installed_hooks = list(install_root.rglob("hooks.json"))
        except OSError as exc:
            lines.append(f"install_root_error={exc}")
        else:
            for path in installed_hooks[:20]:
                lines.append(f"installed_hooks_json={path}")
                _append_text_file_diagnostic(lines, "installed_hooks_content", path)
    lines.append(f"stdout={run.stdout[-600:]!r}")
    lines.append(f"stderr={run.stderr[-600:]!r}")
    return "\n".join(lines)


def _preserve_gh_auth_config(env: dict[str, str]) -> None:
    """Keep gh authentication available while isolating Copilot plugin state."""
    if env.get("GH_CONFIG_DIR"):
        return
    if os.name == "nt":
        config_root = env.get("APPDATA")
        candidate = Path(config_root) / "GitHub CLI" if config_root else None
    else:
        config_root = env.get("XDG_CONFIG_HOME")
        if config_root:
            candidate = Path(config_root) / "gh"
        else:
            home = env.get("HOME")
            candidate = Path(home) / ".config" / "gh" if home else None
    if candidate is not None and candidate.is_dir():
        env["GH_CONFIG_DIR"] = str(candidate)


@pytest.mark.smoke
@requires_copilot
def test_copilot_vendor_install_hook_resolves(tmp_path: Path) -> None:
    """A vendor-installed hook resolves from the copied install tree, not cwd.

    Binds the probe to UserPromptSubmit (not SessionStart): copilot -p does not
    dispatch SessionStart, so a SessionStart marker would never appear under -p
    even when resolution is correct. See module docstring and issue #2378.
    """
    probe_name = _probe_name()
    plugin = tmp_path / "plugin"
    userland = tmp_path / "userland"
    marker = tmp_path / "copilot_marker.txt"
    isolated_home = tmp_path / "copilot-home"
    userland.mkdir()
    isolated_home.mkdir()
    _write_probe_script(plugin / "hooks" / _COPILOT_EVENT / "probe.py", marker)
    (plugin / "plugin.json").write_text(_manifest(probe_name), encoding="utf-8")
    # Use the exact command shape the generator emits, for this event.
    entry = generate_hooks._build_copilot_entry(_COPILOT_EVENT, "probe.py")
    (plugin / "hooks" / "hooks.json").write_text(
        json.dumps({"hooks": {_COPILOT_EVENT: [entry]}, "version": 1}), encoding="utf-8"
    )

    env = _clean_env()
    _preserve_gh_auth_config(env)
    env["HOME"] = str(isolated_home)
    env["USERPROFILE"] = str(isolated_home)
    env["COPILOT_HOME"] = str(isolated_home / ".copilot")
    install_root = isolated_home / ".copilot" / "installed-plugins"
    try:
        install = subprocess.run(
            _copilot_command("plugin", "install", str(plugin)),
            cwd=userland,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=240,
            check=False,
            env=env,
        )
    except subprocess.TimeoutExpired:
        pytest.skip("copilot plugin install exceeded 240s (CLI/infra latency)")
    _skip_on_copilot_block(install)
    assert install.returncode == 0, install.stderr or install.stdout

    try:
        run = subprocess.run(
            _copilot_command(
                "-p",
                _PROMPT,
                "--allow-all-tools",
                "--allow-all-paths",
            ),
            cwd=userland,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=240,
            check=False,
            env=env,
        )
    except subprocess.TimeoutExpired:
        pytest.skip("copilot run exceeded 240s (CLI/infra latency)")
    _skip_on_copilot_block(run)

    assert marker.is_file(), _copilot_failure_diagnostics(
        probe_name, plugin, userland, run, install_root
    )
    text = marker.read_text(encoding="utf-8")
    assert "MARKER" in text
    script_path = _marker_path(text, "script")
    assert "installed-plugins" in script_path.parts
    assert isolated_home in script_path.parents
    assert plugin not in script_path.parents
    assert userland not in script_path.parents


def _marker_path(text: str, key: str) -> Path:
    """Read one ``key=<path>`` line out of the probe marker as a ``Path``.

    The probe writes some values with the separators the CLI handed it, which on
    Windows can be POSIX while ``str(Path)`` is not. Parsing into ``Path`` makes
    the comparison about the location rather than about the byte spelling of the
    separator (issue #3335).
    """
    prefix = f"{key}="
    line = next((line for line in text.splitlines() if line.startswith(prefix)), None)
    assert line is not None, f"marker missing {prefix!r}; tail={text[-500:]!r}"
    value = line[len(prefix) :].strip()
    assert value, f"marker has empty {prefix!r}; tail={text[-500:]!r}"
    return Path(value)


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
            text=True, encoding="utf-8",
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
    # Compare as paths, not strings: Claude exports the root with POSIX
    # separators even on Windows, where str(Path) yields backslashes, so a raw
    # substring test fails on a correct value (issue #3335).
    assert _marker_path(text, "CLAUDE_PLUGIN_ROOT") == plugin
    assert _marker_path(text, "script") == plugin / "hooks" / "probe.py"


def test_marker_path_reads_one_key_and_trims_the_line() -> None:
    """The marker parser picks the right line and tolerates trailing bytes."""
    text = "MARKER\r\nscript=/tmp/p/hooks/probe.py \ncwd=/tmp/u\nCLAUDE_PLUGIN_ROOT=/tmp/p\n"
    assert _marker_path(text, "CLAUDE_PLUGIN_ROOT") == Path("/tmp/p")
    assert _marker_path(text, "script") == Path("/tmp/p/hooks/probe.py")


def test_marker_path_reports_a_missing_key_with_context() -> None:
    """A truncated marker fails with the missing key and marker tail."""
    text = "MARKER\ncwd=/tmp/u\n"
    with pytest.raises(AssertionError, match="marker missing 'script='") as error:
        _marker_path(text, "script")
    assert "cwd=/tmp/u" in str(error.value)


def test_plugin_root_comparison_is_separator_insensitive() -> None:
    """Claude exports CLAUDE_PLUGIN_ROOT with POSIX separators even on Windows.

    Comparing as paths accepts that; comparing as strings does not, which is why
    the Windows leg of this smoke failed on a correct value (issue #3335). The
    string inequality below is the failure the old assertion produced.
    """
    posix_spelling = "C:/Users/runneradmin/AppData/Local/Temp/plugin"
    native_spelling = r"C:\Users\runneradmin\AppData\Local\Temp\plugin"
    assert posix_spelling != native_spelling
    assert PureWindowsPath(posix_spelling) == PureWindowsPath(native_spelling)


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
    tmp_path: Path,
) -> None:
    """Diagnostic failures report partial context instead of masking the marker miss."""
    run = subprocess.CompletedProcess(["copilot"], 1, stdout="out", stderr="err")

    diagnostics = _copilot_failure_diagnostics(
        "probe", tmp_path / "plugin", tmp_path / "userland", run
    )

    assert "authored_hooks_json=" in diagnostics
    assert "stdout='out'" in diagnostics
    assert "stderr='err'" in diagnostics


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
        text=True, encoding="utf-8",
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


@pytest.mark.parametrize("blocked_phase", ["install", "run"])
@pytest.mark.parametrize(
    "stderr",
    [
        "API rate limit exceeded for user ID 12345.",
        "Failed to fetch PAT user login: connection reset by peer.",
    ],
)
def test_copilot_vendor_consumer_skips_classified_block(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    blocked_phase: str,
    stderr: str,
) -> None:
    """The install and prompt calls both stop before hook assertions."""
    success = subprocess.CompletedProcess(["copilot"], 0, stdout="", stderr="")
    blocked = subprocess.CompletedProcess(["copilot"], 1, stdout="", stderr=stderr)

    def fake_run(argv: tuple[str, ...], **_: object) -> subprocess.CompletedProcess[str]:
        is_install = "plugin" in argv and "install" in argv
        if blocked_phase == "install":
            return blocked if is_install else success
        return success if is_install else blocked

    monkeypatch.setattr("tests.e2e.test_cli_hook_e2e._copilot_command", lambda *a: a)
    monkeypatch.setattr("tests.e2e.test_cli_hook_e2e.subprocess.run", fake_run)

    with pytest.raises(pytest.skip.Exception):
        test_copilot_vendor_install_hook_resolves(tmp_path)
