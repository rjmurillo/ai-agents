#!/usr/bin/env python3
"""Installed Copilot plugin hook condition harness (issue #2300).

Opt-in end-to-end check that the INSTALLED ``project-toolkit@ai-agents`` Copilot
plugin's hooks satisfy the runtime contract a real user sees: every registered
command resolves to a real script, matcher shims fire only on matching tools,
and lifecycle hooks launch without error. It spends no model credits and runs no
Copilot prompts; it executes the hook scripts directly with crafted stdin.

Also exercises the in-process dispatcher (ADR-068, issue #2295) against the real
installed shim set: a non-matching tool must drive every registered guard to
skip and the dispatcher to allow, proving the consolidation runs the real guards.

Why opt-in: the marketplace plugin is not installed in bare CI. The harness runs
where the plugin is installed and ``RUN_INSTALLED_PLUGIN_HOOK_E2E=1`` is set, and
SKIPS loudly otherwise so a skipped run never reads as a pass.

Run from the repository root in an isolated Copilot home:
    E2E_HOME="$(mktemp -d)"
    HOME="$E2E_HOME" COPILOT_HOME="$E2E_HOME/.copilot" \
        copilot plugin marketplace add "$PWD"
    HOME="$E2E_HOME" COPILOT_HOME="$E2E_HOME/.copilot" \
        copilot plugin install project-toolkit@ai-agents
    HOME="$E2E_HOME" COPILOT_HOME="$E2E_HOME/.copilot" \
        RUN_INSTALLED_PLUGIN_HOOK_E2E=1 uv run pytest \
        tests/e2e/test_installed_plugin_hook_e2e.py -v

Do not use the live Copilot home. Direct and marketplace installs can share a
plugin name, and an unqualified uninstall can remove the marketplace entry while
leaving a stale direct cache.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

_RUN = os.environ.get("RUN_INSTALLED_PLUGIN_HOOK_E2E") == "1"
_PLUGIN = "project-toolkit@ai-agents"
_INSTALL_BASE = Path.home() / ".copilot" / "installed-plugins"
_SCOPED_ROOT = _INSTALL_BASE / "ai-agents" / "project-toolkit"
_DIRECT_ROOT = _INSTALL_BASE / "_direct" / "project-toolkit"
_PRE_TOOL_EVENT = "PreToolUse"

# The plugin-relative script path inside a generated command. Works for both
# the bash form (``...}}/hooks/preToolUse/foo.py``) and the powershell form
# (``...})/hooks/preToolUse/foo.py``): match the ``hooks/<event>/...py`` tail
# regardless of the preceding shell punctuation.
_REL_RE = re.compile(r"(hooks/[A-Za-z]+/[^\"'\s]+\.py)")

requires_install = pytest.mark.skipif(
    not (_RUN and _SCOPED_ROOT.is_dir()),
    reason=(
        f"needs RUN_INSTALLED_PLUGIN_HOOK_E2E=1 and {_PLUGIN} installed at "
        f"{_SCOPED_ROOT} (run `copilot plugin install`)"
    ),
)


def _load_hooks(root: Path) -> dict:
    return json.loads((root / "hooks" / "hooks.json").read_text())["hooks"]


def _dispatcher_shims(root: Path, event: str) -> list[str]:
    manifest = json.loads(
        (root / "hooks" / event / "_manifest.json").read_text(encoding="utf-8")
    )
    shims = manifest.get("shims")
    assert isinstance(shims, list)
    assert all(isinstance(name, str) for name in shims)
    return shims


def _rel_script(command: str) -> str | None:
    m = _REL_RE.search(command)
    return m.group(1) if m else None


def _run_shim(
    script: Path, payload: dict, cwd: Path, debug: bool = True
) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["CLAUDE_PLUGIN_ROOT"] = str(_SCOPED_ROOT)
    env["COPILOT_PLUGIN_ROOT"] = str(_SCOPED_ROOT)
    if debug:
        env["COPILOT_HOOK_DEBUG"] = "1"
    return subprocess.run(
        [sys.executable, "-u", str(script)],
        input=json.dumps(payload).encode(),
        capture_output=True,
        cwd=str(cwd),
        env=env,
        timeout=30,
    )


def _fired(proc: subprocess.CompletedProcess) -> bool | None:
    m = re.search(rb"matcher-shim \[.*?\]: kind=\S+ fired=(True|False)", proc.stderr)
    if not m:
        return None
    return m.group(1) == b"True"


def _is_shim(script: Path) -> bool:
    try:
        head = script.read_text(encoding="utf-8", errors="replace")[:400]
    except OSError:
        return False
    return "MATCHER SHIM" in head


@pytest.fixture
def user_repo(tmp_path: Path) -> Path:
    """A throwaway git repo cwd: hooks run from here, not the plugin root."""
    repo = tmp_path / "user_repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    (repo / "README.md").write_text("# fixture\n")
    return repo


@requires_install
class TestInstalledPluginHooks:
    def test_scoped_install_present(self):
        # Req 1: locate the scoped marketplace install.
        assert (_SCOPED_ROOT / "hooks" / "hooks.json").is_file(), (
            f"{_PLUGIN} hooks.json not found under {_SCOPED_ROOT}"
        )

    def test_installed_version_matches_worktree(self):
        worktree_manifest = (
            Path(__file__).resolve().parents[2]
            / "src"
            / "copilot-cli"
            / ".claude-plugin"
            / "plugin.json"
        )
        installed_manifest = _SCOPED_ROOT / ".claude-plugin" / "plugin.json"
        expected = json.loads(worktree_manifest.read_text(encoding="utf-8"))["version"]
        actual = json.loads(installed_manifest.read_text(encoding="utf-8"))["version"]
        assert actual == expected, (
            f"installed {_PLUGIN} is {actual}, worktree is {expected}; reinstall "
            "the worktree plugin before running this E2E"
        )

    def test_no_stale_direct_install_shadows(self):
        # Req 3: a stale unscoped direct install can shadow the marketplace one.
        assert not _DIRECT_ROOT.is_dir(), (
            f"Stale direct install present at {_DIRECT_ROOT}; it can shadow the "
            f"marketplace {_PLUGIN}. Remove it: `copilot plugin uninstall project-toolkit`."
        )

    def test_every_command_resolves_to_existing_script(self):
        # Req 4: every bash AND powershell command points to a real script.
        hooks = _load_hooks(_SCOPED_ROOT)
        missing = []
        for event, entries in hooks.items():
            for i, entry in enumerate(entries):
                for shell in ("bash", "powershell"):
                    cmd = entry.get(shell)
                    if not cmd:
                        continue
                    rel = _rel_script(cmd)
                    if rel is None:
                        missing.append(f"{event}[{i}].{shell}: no script path in {cmd!r}")
                        continue
                    if not (_SCOPED_ROOT / rel).is_file():
                        missing.append(f"{event}[{i}].{shell}: missing {rel}")
        assert not missing, "Unresolved hook scripts:\n  " + "\n  ".join(missing)

    def test_matcher_shim_skips_non_match(self, user_repo):
        # Req 5: a non-matching tool exits 0 without firing.
        checked = 0
        event_dir = _SCOPED_ROOT / "hooks" / _PRE_TOOL_EVENT
        for i, shim in enumerate(_dispatcher_shims(_SCOPED_ROOT, _PRE_TOOL_EVENT)):
            script = event_dir / shim
            if not _is_shim(script):
                continue
            proc = _run_shim(script, {"tool_name": "____NoSuchTool____"}, user_repo)
            fired = _fired(proc)
            assert fired is False, (
                f"{_PRE_TOOL_EVENT}[{i}] {shim}: expected fired=False for non-match, "
                f"got fired={fired} rc={proc.returncode}\n{proc.stderr.decode()[:400]}"
            )
            assert proc.returncode == 0, (
                f"{_PRE_TOOL_EVENT}[{i}] {shim}: non-match must exit 0, "
                f"got {proc.returncode}"
            )
            checked += 1
        assert checked > 0, "no PreToolUse matcher shims found to check"

    def test_matcher_shim_fires_on_snake_case_match(self, user_repo):
        # Req 6: snake_case payload whose tool_name matches the shim fires.
        fired_any = 0
        event_dir = _SCOPED_ROOT / "hooks" / _PRE_TOOL_EVENT
        for i, shim in enumerate(_dispatcher_shims(_SCOPED_ROOT, _PRE_TOOL_EVENT)):
            script = event_dir / shim
            if not _is_shim(script):
                continue
            matcher = _shim_matcher(script)
            tool = _matching_tool(matcher)
            if tool is None:
                continue  # command matchers are exercised by dispatcher tests
            proc = _run_shim(script, _payload_for(tool), user_repo)
            fired = _fired(proc)
            assert fired is True, (
                f"{_PRE_TOOL_EVENT}[{i}] {shim} matcher={matcher!r}: expected fired=True "
                f"for tool {tool!r}, got fired={fired}\n{proc.stderr.decode()[:400]}"
            )
            fired_any += 1
        assert fired_any > 0, "no bare-matcher PreToolUse shims fired"

    def test_lifecycle_hooks_launch_without_error(self, user_repo):
        # Req 8: non-matcher lifecycle hooks execute a representative payload
        # without a launcher error or timeout (exit code is hook-defined; we
        # only fail on launch failure / crash, not on a hook's own decision).
        hooks = _load_hooks(_SCOPED_ROOT)
        for event in ("SessionStart", "Stop", "UserPromptSubmit"):
            entries = hooks.get(event)
            assert entries, f"{event}: no installed hook entries"
            for i, entry in enumerate(entries):
                rel = _rel_script(entry.get("bash", ""))
                script = _SCOPED_ROOT / rel if rel else None
                if not script:
                    continue
                try:
                    proc = _run_shim(script, {"cwd": str(user_repo)}, user_repo, debug=False)
                except subprocess.TimeoutExpired:
                    pytest.fail(f"{event}[{i}] {rel}: timed out (launcher/latency error)")
                # A Python traceback on stderr means a launcher/import failure,
                # not a hook decision. Fail on that.
                assert b"Traceback (most recent call last)" not in proc.stderr, (
                    f"{event}[{i}] {rel}: launcher error\n{proc.stderr.decode()[:600]}"
                )


@requires_install
class TestDispatcherAgainstInstalledShims:
    """ADR-068 / #2295: run the in-process dispatcher over the REAL installed
    preToolUse shim set. A non-matching tool must drive every registered guard
    to skip and the dispatcher to allow, proving the consolidation executes the
    real guards in one process without crashing or denying benign tools."""

    def _dispatch(self):
        import importlib.util

        lib = _SCOPED_ROOT / "lib" / "hook_dispatch.py"
        spec = importlib.util.spec_from_file_location("hook_dispatch", lib)
        assert spec is not None and spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.run_dispatch

    def test_dispatcher_allows_non_matching_tool_over_real_shims(self, monkeypatch):
        run_dispatch = self._dispatch()
        event_dir = _SCOPED_ROOT / "hooks" / _PRE_TOOL_EVENT
        manifest = _dispatcher_shims(_SCOPED_ROOT, _PRE_TOOL_EVENT)
        assert manifest, "expected the installed PreToolUse dispatcher manifest"
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(_SCOPED_ROOT))
        monkeypatch.setenv("COPILOT_PLUGIN_ROOT", str(_SCOPED_ROOT))
        payload = b'{"tool_name":"____NoSuchTool____","tool_input":{}}'
        rc = run_dispatch(event_dir, manifest, payload)
        assert rc == 0, (
            f"dispatcher denied a non-matching tool over the real shim set "
            f"(rc={rc}); every guard should have skipped"
        )

    def test_dispatcher_runs_every_registered_shim(self, monkeypatch, capsys):
        # With COPILOT_HOOK_DEBUG each shim prints a fired= line; assert one per
        # registered shim, proving the dispatcher ran the whole manifest.
        run_dispatch = self._dispatch()
        event_dir = _SCOPED_ROOT / "hooks" / _PRE_TOOL_EVENT
        manifest = _dispatcher_shims(_SCOPED_ROOT, _PRE_TOOL_EVENT)
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(_SCOPED_ROOT))
        monkeypatch.setenv("COPILOT_PLUGIN_ROOT", str(_SCOPED_ROOT))
        monkeypatch.setenv("COPILOT_HOOK_DEBUG", "1")
        rc = run_dispatch(event_dir, manifest, b'{"tool_name":"____NoSuchTool____"}')
        assert rc == 0
        fired_lines = re.findall(r"matcher-shim \[.*?\]: kind=\S+ fired=", capsys.readouterr().err)
        assert len(fired_lines) == len(manifest), (
            f"dispatcher ran {len(fired_lines)} shims, expected {len(manifest)}"
        )


def _shim_matcher(script: Path) -> str | None:
    m = re.search(r"^_MATCHER = '(.*)'$", script.read_text(), re.MULTILINE)
    return m.group(1) if m else None


def _matching_tool(matcher: str | None) -> str | None:
    """Return one tool accepted by a tool-only matcher, else None."""
    if not matcher:
        return None
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", matcher):
        return matcher

    alternatives = re.fullmatch(
        r"\^\((?:\?:)?([A-Za-z][A-Za-z0-9_]*(?:\|[A-Za-z][A-Za-z0-9_]*)+)\)\$",
        matcher,
    )
    return alternatives.group(1).split("|", 1)[0] if alternatives else None


def _payload_for(tool: str) -> dict:
    inputs = {
        "Read": {"file_path": "x.py"},
        "Edit": {"file_path": "x.py"},
        "Write": {"file_path": "x.py"},
        "Grep": {"pattern": "foo"},
        "Glob": {"pattern": "*.py"},
    }
    return {"tool_name": tool, "tool_input": inputs.get(tool, {})}
