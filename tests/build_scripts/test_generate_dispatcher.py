"""Tests for the gated Copilot hook dispatcher emitter (ADR-068, #2295)."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "build" / "scripts"))

import generate_dispatcher as gd  # noqa: E402


class TestDispatcherEntry:
    def test_entry_points_at_event_dispatcher(self):
        entry = gd.dispatcher_entry("preToolUse", 90)
        assert "/hooks/preToolUse/_dispatch.py" in entry["bash"]
        assert "/hooks/preToolUse/_dispatch.py" in entry["powershell"]
        assert entry["timeoutSec"] == 90
        assert entry["type"] == "command"

    def test_entry_prefers_copilot_root_with_claude_fallback(self):
        entry = gd.dispatcher_entry("postToolUse", 30)
        # Same resolution contract as the per-shim entries it replaces.
        assert "COPILOT_PLUGIN_ROOT" in entry["bash"]
        assert "CLAUDE_PLUGIN_ROOT" in entry["bash"]


class TestEmit:
    def test_manifest_is_ordered_and_named(self, tmp_path):
        shims = ["b.py", "a.py", "c.py"]
        gd.write_manifest(tmp_path, "preToolUse", shims)
        data = json.loads((tmp_path / "_manifest.json").read_text())
        # mode defaults to "gate" so an absent mode fails closed (ADR-066).
        assert data == {
            "event": "preToolUse",
            "mode": "gate",
            "shims": ["b.py", "a.py", "c.py"],
        }

    def test_manifest_records_observe_mode(self, tmp_path):
        gd.write_manifest(tmp_path, "postToolUse", ["a.py"], mode="observe")
        data = json.loads((tmp_path / "_manifest.json").read_text())
        assert data["mode"] == "observe"

    def test_manifest_rejects_unknown_mode(self, tmp_path):
        import pytest

        with pytest.raises(ValueError, match="mode must be"):
            gd.write_manifest(tmp_path, "postToolUse", ["a.py"], mode="bogus")

    def test_manifest_can_include_per_shim_timeouts(self, tmp_path):
        shims = ["b.py", "a.py"]
        gd.write_manifest(tmp_path, "preToolUse", shims, {"a.py": 5, "b.py": 90})

        data = json.loads((tmp_path / "_manifest.json").read_text())

        assert data == {
            "event": "preToolUse",
            "mode": "gate",
            "shims": ["b.py", "a.py"],
            "timeouts": {"b.py": 90, "a.py": 5},
        }

    def test_emit_writes_all_artifacts_and_returns_entry(self, tmp_path):
        entry = gd.emit_dispatcher(tmp_path, "preToolUse", ["x.py"], 5)
        assert (tmp_path / "_manifest.json").is_file()
        assert (tmp_path / "_dispatch.py").is_file()
        # The entrypoint imports ensure_plugin_paths from a sibling _bootstrap.py,
        # so emit must drop one into every consolidated event dir (#2342).
        assert (tmp_path / "_bootstrap.py").is_file()
        assert "/hooks/preToolUse/_dispatch.py" in entry["bash"]

    def test_generated_entrypoint_dispatches_real_shims(self, tmp_path):
        """End-to-end: the generated entrypoint + manifest + dispatcher lib run a
        shim set in one process and honor fail-closed (a blocker denies)."""
        # Stage a minimal plugin layout the entrypoint's bootstrap can resolve.
        root = tmp_path / "plugin"
        (root / ".claude-plugin").mkdir(parents=True)
        (root / ".claude-plugin" / "plugin.json").write_text('{"name":"t"}', encoding="utf-8")
        lib = root / "lib"
        lib.mkdir()
        # Copy the real dispatcher lib and a minimal bootstrap into the lib/hooks.
        src_lib = _REPO / ".claude" / "lib" / "hook_dispatch.py"
        (lib / "hook_dispatch.py").write_text(src_lib.read_text(encoding="utf-8"), encoding="utf-8")
        event_dir = root / "hooks" / "preToolUse"
        event_dir.mkdir(parents=True)
        (event_dir / "_bootstrap.py").write_text(
            "import os, sys\n"
            "from pathlib import Path\n"
            "def ensure_plugin_paths():\n"
            "    root = Path(os.environ['CLAUDE_PLUGIN_ROOT']).resolve()\n"
            "    sys.path.insert(0, str(root / 'lib'))\n",
            encoding="utf-8",
        )
        allow = "allow.py"
        block = "block.py"
        (event_dir / allow).write_text("import sys; sys.exit(0)\n", encoding="utf-8")
        (event_dir / block).write_text("import sys; sys.exit(2)\n", encoding="utf-8")
        gd.emit_dispatcher(event_dir, "preToolUse", [allow, block], 5)

        env = dict(__import__("os").environ)
        env["CLAUDE_PLUGIN_ROOT"] = str(root)
        proc = subprocess.run(
            [sys.executable, "-u", str(event_dir / "_dispatch.py")],
            input=b'{"tool_name":"X"}',
            capture_output=True,
            env=env,
            timeout=30,
        )
        # block.py exits 2 -> dispatcher denies (fail-closed) in one process.
        assert proc.returncode == 2, proc.stderr.decode()

    def test_generated_entrypoint_allows_when_all_allow(self, tmp_path):
        root = tmp_path / "plugin"
        (root / ".claude-plugin").mkdir(parents=True)
        (root / ".claude-plugin" / "plugin.json").write_text('{"name":"t"}', encoding="utf-8")
        lib = root / "lib"
        lib.mkdir()
        (lib / "hook_dispatch.py").write_text(
            (_REPO / ".claude" / "lib" / "hook_dispatch.py").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        event_dir = root / "hooks" / "preToolUse"
        event_dir.mkdir(parents=True)
        (event_dir / "_bootstrap.py").write_text(
            "import os, sys\n"
            "from pathlib import Path\n"
            "def ensure_plugin_paths():\n"
            "    lib = Path(os.environ['CLAUDE_PLUGIN_ROOT']).resolve() / 'lib'\n"
            "    sys.path.insert(0, str(lib))\n",
            encoding="utf-8",
        )
        (event_dir / "a.py").write_text("import sys; sys.exit(0)\n", encoding="utf-8")
        gd.emit_dispatcher(event_dir, "preToolUse", ["a.py"], 5)
        env = dict(__import__("os").environ)
        env["CLAUDE_PLUGIN_ROOT"] = str(root)
        proc = subprocess.run(
            [sys.executable, "-u", str(event_dir / "_dispatch.py")],
            input=b"{}",
            capture_output=True,
            env=env,
            timeout=30,
        )
        assert proc.returncode == 0, proc.stderr.decode()

    def test_generated_entrypoint_malformed_manifest_fails_closed(self, tmp_path):
        root = tmp_path / "plugin"
        (root / ".claude-plugin").mkdir(parents=True)
        (root / ".claude-plugin" / "plugin.json").write_text('{"name":"t"}', encoding="utf-8")
        lib = root / "lib"
        lib.mkdir()
        (lib / "hook_dispatch.py").write_text(
            (_REPO / ".claude" / "lib" / "hook_dispatch.py").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        event_dir = root / "hooks" / "preToolUse"
        event_dir.mkdir(parents=True)
        (event_dir / "_bootstrap.py").write_text(
            "import os, sys\n"
            "from pathlib import Path\n"
            "def ensure_plugin_paths():\n"
            "    lib = Path(os.environ['CLAUDE_PLUGIN_ROOT']).resolve() / 'lib'\n"
            "    sys.path.insert(0, str(lib))\n",
            encoding="utf-8",
        )
        gd.write_entrypoint(event_dir)
        (event_dir / "_manifest.json").write_text('{"event":"preToolUse"}\n', encoding="utf-8")
        env = dict(__import__("os").environ)
        env["CLAUDE_PLUGIN_ROOT"] = str(root)

        proc = subprocess.run(
            [sys.executable, "-u", str(event_dir / "_dispatch.py")],
            input=b"{}",
            capture_output=True,
            env=env,
            timeout=30,
        )

        assert proc.returncode == 2
        stderr = proc.stderr.decode()
        assert "hook-dispatch-entrypoint" in stderr
        assert "fail-closed" in stderr

    def test_generated_entrypoint_oversized_stdin_fails_closed(self, tmp_path):
        root = tmp_path / "plugin"
        (root / ".claude-plugin").mkdir(parents=True)
        (root / ".claude-plugin" / "plugin.json").write_text('{"name":"t"}', encoding="utf-8")
        lib = root / "lib"
        lib.mkdir()
        (lib / "hook_dispatch.py").write_text(
            (_REPO / ".claude" / "lib" / "hook_dispatch.py").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        event_dir = root / "hooks" / "preToolUse"
        event_dir.mkdir(parents=True)
        (event_dir / "_bootstrap.py").write_text(
            "import os, sys\n"
            "from pathlib import Path\n"
            "def ensure_plugin_paths():\n"
            "    lib = Path(os.environ['CLAUDE_PLUGIN_ROOT']).resolve() / 'lib'\n"
            "    sys.path.insert(0, str(lib))\n",
            encoding="utf-8",
        )
        gd.write_entrypoint(event_dir)
        gd.write_manifest(event_dir, "preToolUse", [])
        env = dict(__import__("os").environ)
        env["CLAUDE_PLUGIN_ROOT"] = str(root)

        proc = subprocess.run(
            [sys.executable, "-u", str(event_dir / "_dispatch.py")],
            input=b"{" + b'"x":"' + (b"a" * (2 * 1024 * 1024)) + b'"}',
            capture_output=True,
            env=env,
            timeout=30,
        )

        assert proc.returncode == 2
        stderr = proc.stderr.decode()
        assert "stdin exceeds 2097152 bytes" in stderr
        assert "fail-closed" in stderr

    def test_generated_entrypoint_invalid_timeout_manifest_fails_closed(self, tmp_path):
        root = tmp_path / "plugin"
        (root / ".claude-plugin").mkdir(parents=True)
        (root / ".claude-plugin" / "plugin.json").write_text('{"name":"t"}', encoding="utf-8")
        lib = root / "lib"
        lib.mkdir()
        (lib / "hook_dispatch.py").write_text(
            (_REPO / ".claude" / "lib" / "hook_dispatch.py").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        event_dir = root / "hooks" / "preToolUse"
        event_dir.mkdir(parents=True)
        (event_dir / "_bootstrap.py").write_text(
            "import os, sys\n"
            "from pathlib import Path\n"
            "def ensure_plugin_paths():\n"
            "    lib = Path(os.environ['CLAUDE_PLUGIN_ROOT']).resolve() / 'lib'\n"
            "    sys.path.insert(0, str(lib))\n",
            encoding="utf-8",
        )
        gd.write_entrypoint(event_dir)
        gd.write_manifest(event_dir, "preToolUse", ["a.py"], {"a.py": 0})
        env = dict(__import__("os").environ)
        env["CLAUDE_PLUGIN_ROOT"] = str(root)

        proc = subprocess.run(
            [sys.executable, "-u", str(event_dir / "_dispatch.py")],
            input=b"{}",
            capture_output=True,
            env=env,
            timeout=30,
        )

        assert proc.returncode == 2
        assert "manifest timeout for a.py must be positive" in proc.stderr.decode()

    def test_generated_pretooluse_observe_manifest_fails_closed(self, tmp_path):
        root, event_dir = _stage_plugin(tmp_path, "preToolUse")
        (event_dir / "a.py").write_text("import sys; sys.exit(0)\n", encoding="utf-8")
        gd.emit_dispatcher(event_dir, "preToolUse", ["a.py"], 5, mode="gate")
        gd.write_manifest(event_dir, "preToolUse", ["a.py"], mode="observe")

        proc = _run_dispatch_entry(root, event_dir)

        assert proc.returncode == 2
        assert "must be 'gate'" in proc.stderr.decode()


def _stage_plugin(tmp_path, event):
    """Stage a minimal plugin tree the canonical _bootstrap.py can resolve.

    Returns ``(root, event_dir)``. The plugin has ``lib/hook_dispatch.py`` (the
    real lib) and an ``hooks/<event>/`` dir, which is exactly what the canonical
    bootstrap's env-var resolution needs. ``emit_dispatcher`` drops the real
    ``_bootstrap.py`` (and ``_dispatch.py`` + manifest) into the event dir.
    """
    root = tmp_path / "plugin"
    (root / ".claude-plugin").mkdir(parents=True)
    (root / ".claude-plugin" / "plugin.json").write_text('{"name":"t"}', encoding="utf-8")
    lib = root / "lib"
    lib.mkdir()
    (lib / "hook_dispatch.py").write_text(
        (_REPO / ".claude" / "lib" / "hook_dispatch.py").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    event_dir = root / "hooks" / event
    event_dir.mkdir(parents=True)
    return root, event_dir


def _run_dispatch_entry(root, event_dir):
    env = dict(__import__("os").environ)
    env["CLAUDE_PLUGIN_ROOT"] = str(root)
    return subprocess.run(
        [sys.executable, "-u", str(event_dir / "_dispatch.py")],
        input=b'{"tool_name":"X"}',
        capture_output=True,
        env=env,
        timeout=30,
    )


class TestObserveMode:
    """Runtime-contract coverage for observe mode (#2342).

    These run the GENERATED entrypoint as a subprocess under the verified
    plugin-root contract, not a string match against the generator. A marker
    file per shim proves the shim actually executed in the dispatched process.
    """

    def _markered_shim(self, marker_path, exit_code):
        # A shim that touches a marker file, then exits with ``exit_code``.
        return (
            "import sys\n"
            "from pathlib import Path\n"
            f"Path(r'{marker_path}').write_text('ran', encoding='utf-8')\n"
            f"sys.exit({exit_code})\n"
        )

    def test_observe_runs_all_shims_even_when_one_signals(self, tmp_path):
        # A failing observer must NOT stop later observers (the pre-consolidation
        # host ran every observer entry). Dispatcher returns 0 regardless.
        root, event_dir = _stage_plugin(tmp_path, "postToolUse")
        m_a, m_b, m_c = (tmp_path / f"m_{x}" for x in "abc")
        (event_dir / "a.py").write_text(self._markered_shim(m_a, 0), encoding="utf-8")
        (event_dir / "b.py").write_text(
            self._markered_shim(m_b, 7), encoding="utf-8"
        )  # signals
        (event_dir / "c.py").write_text(self._markered_shim(m_c, 0), encoding="utf-8")
        gd.emit_dispatcher(
            event_dir, "postToolUse", ["a.py", "b.py", "c.py"], 15, mode="observe"
        )

        proc = _run_dispatch_entry(root, event_dir)

        # Observe mode never gates: exit 0 even though b.py exited 7.
        assert proc.returncode == 0, proc.stderr.decode()
        # Every shim ran, including the one AFTER the failing one.
        assert m_a.is_file() and m_b.is_file() and m_c.is_file(), (
            "an observer was skipped; observe mode must run all shims"
        )

    def test_observe_continues_past_missing_shim(self, tmp_path):
        # A registered shim missing on disk is logged but does not stop the
        # remaining observers, and the dispatcher still returns 0.
        root, event_dir = _stage_plugin(tmp_path, "sessionStart")
        m_b = tmp_path / "m_b"
        (event_dir / "b.py").write_text(self._markered_shim(m_b, 0), encoding="utf-8")
        # "missing.py" is in the manifest but never written to disk.
        gd.emit_dispatcher(
            event_dir, "sessionStart", ["missing.py", "b.py"], 10, mode="observe"
        )

        proc = _run_dispatch_entry(root, event_dir)

        assert proc.returncode == 0, proc.stderr.decode()
        assert m_b.is_file(), "observer after a missing shim was skipped"
        assert b"missing on disk" in proc.stderr

    def test_gate_still_fails_closed_and_short_circuits(self, tmp_path):
        # Regression: gate mode is unchanged. The blocker denies and the shim
        # AFTER it must NOT run (short-circuit preserved, ADR-066 / #2295).
        root, event_dir = _stage_plugin(tmp_path, "preToolUse")
        m_after = tmp_path / "m_after"
        (event_dir / "block.py").write_text("import sys; sys.exit(2)\n", encoding="utf-8")
        (event_dir / "after.py").write_text(
            self._markered_shim(m_after, 0), encoding="utf-8"
        )
        gd.emit_dispatcher(
            event_dir, "preToolUse", ["block.py", "after.py"], 5, mode="gate"
        )

        proc = _run_dispatch_entry(root, event_dir)

        assert proc.returncode == 2, proc.stderr.decode()
        assert not m_after.is_file(), (
            "gate mode ran a shim after a denial; short-circuit regressed"
        )

    def test_timeout_metadata_does_not_background_observer_work(self, tmp_path):
        # Regression: enforcing per-shim timeouts with daemon threads made
        # observe mode return success before a slow observer finished. The host
        # owns the event timeout; the in-process dispatcher must run the shim
        # synchronously so no child work survives hook success.
        root, event_dir = _stage_plugin(tmp_path, "postToolUse")
        marker = tmp_path / "slow_observer_marker"
        (event_dir / "slow.py").write_text(
            "import sys, time\n"
            "from pathlib import Path\n"
            "time.sleep(1.2)\n"
            f"Path(r'{marker}').write_text('ran', encoding='utf-8')\n"
            "sys.exit(0)\n",
            encoding="utf-8",
        )
        gd.emit_dispatcher(
            event_dir,
            "postToolUse",
            ["slow.py"],
            3,
            {"slow.py": 1},
            mode="observe",
        )

        started = time.monotonic()
        proc = _run_dispatch_entry(root, event_dir)
        elapsed = time.monotonic() - started

        assert proc.returncode == 0, proc.stderr.decode()
        assert marker.is_file(), "dispatcher returned before the observer finished"
        assert elapsed >= 1.0, "per-shim timeout metadata was enforced inside dispatcher"


class TestShimBasename:
    def test_extracts_python_shim_basename(self):
        command = 'python3 -u "${ROOT}/hooks/PreToolUse/guard.py"'

        assert gd._shim_basename(command) == "guard.py"

    def test_rejects_intermediate_extension_match(self):
        command = 'python3 -u "${ROOT}/hooks/PreToolUse/guard.py.tmp"'

        assert gd._shim_basename(command) is None


class TestModeForEvent:
    def test_gating_events_map_to_gate(self):
        assert gd._mode_for_event("PreToolUse") == "gate"
        assert gd._mode_for_event("preToolUse") == "gate"

    def test_other_events_map_to_observe(self):
        for event in ("PostToolUse", "SessionStart", "SessionEnd", "UserPromptSubmit"):
            assert gd._mode_for_event(event) == "observe"


class TestConsolidate:
    def test_consolidates_every_event_with_correct_mode(self, tmp_path):
        # #2342: ALL events consolidate now. PreToolUse is gate; the rest observe.
        hooks_dir = tmp_path / "hooks"
        for event in ("PreToolUse", "PostToolUse"):
            (hooks_dir / event).mkdir(parents=True)
        out = {
            "PreToolUse": [
                {"bash": 'python3 -u "${ROOT}/hooks/PreToolUse/a.py"', "timeoutSec": 5},
                {"bash": 'python3 -u "${ROOT}/hooks/PreToolUse/b.py"', "timeoutSec": 90},
            ],
            "PostToolUse": [
                {"bash": 'python3 -u "${ROOT}/hooks/PostToolUse/c.py"', "timeoutSec": 30},
            ],
        }
        new_out = gd.consolidate(out, hooks_dir)

        # Gating event: one dispatcher entry, cumulative timeout, mode=gate.
        assert len(new_out["PreToolUse"]) == 1
        assert "/hooks/PreToolUse/_dispatch.py" in new_out["PreToolUse"][0]["bash"]
        assert new_out["PreToolUse"][0]["timeoutSec"] == 95
        pre_manifest = json.loads((hooks_dir / "PreToolUse" / "_manifest.json").read_text())
        assert pre_manifest["mode"] == "gate"
        assert pre_manifest["shims"] == ["a.py", "b.py"]
        assert pre_manifest["timeouts"] == {"a.py": 5, "b.py": 90}

        # Observational event: ALSO consolidated, but mode=observe.
        assert len(new_out["PostToolUse"]) == 1
        assert "/hooks/PostToolUse/_dispatch.py" in new_out["PostToolUse"][0]["bash"]
        assert new_out["PostToolUse"][0]["timeoutSec"] == 30
        post_manifest = json.loads((hooks_dir / "PostToolUse" / "_manifest.json").read_text())
        assert post_manifest["mode"] == "observe"
        assert post_manifest["shims"] == ["c.py"]

    def test_consolidate_drops_bootstrap_into_each_event_dir(self, tmp_path):
        hooks_dir = tmp_path / "hooks"
        (hooks_dir / "SessionStart").mkdir(parents=True)
        out = {
            "SessionStart": [
                {"bash": 'python3 -u "${ROOT}/hooks/SessionStart/init.py"', "timeoutSec": 10},
            ],
        }
        gd.consolidate(out, hooks_dir)
        assert (hooks_dir / "SessionStart" / "_bootstrap.py").is_file()
        assert (hooks_dir / "SessionStart" / "_dispatch.py").is_file()

    def test_consolidate_passes_through_event_with_no_shims(self, tmp_path):
        # An entry with no parseable shim path (e.g. a verbatim shell snippet)
        # is left untouched so consolidation never drops a non-shim entry.
        out = {"SessionEnd": [{"bash": 'echo "no script here"', "timeoutSec": 5}]}
        assert gd.consolidate(out, tmp_path) == out

    def test_consolidate_handles_empty_event(self, tmp_path):
        out = {"PreToolUse": []}
        assert gd.consolidate(out, tmp_path) == {"PreToolUse": []}
