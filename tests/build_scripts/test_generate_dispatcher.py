"""Tests for the gated Copilot hook dispatcher emitter (ADR-068, #2295)."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
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
        assert data == {"event": "preToolUse", "shims": ["b.py", "a.py", "c.py"]}

    def test_emit_writes_both_artifacts_and_returns_entry(self, tmp_path):
        entry = gd.emit_dispatcher(tmp_path, "preToolUse", ["x.py"], 5)
        assert (tmp_path / "_manifest.json").is_file()
        assert (tmp_path / "_dispatch.py").is_file()
        assert "/hooks/preToolUse/_dispatch.py" in entry["bash"]

    def test_generated_entrypoint_dispatches_real_shims(self, tmp_path):
        """End-to-end: the generated entrypoint + manifest + dispatcher lib run a
        shim set in one process and honor fail-closed (a blocker denies)."""
        # Stage a minimal plugin layout the entrypoint's bootstrap can resolve.
        root = tmp_path / "plugin"
        (root / ".claude-plugin").mkdir(parents=True)
        (root / ".claude-plugin" / "plugin.json").write_text('{"name":"t"}')
        lib = root / "lib"
        lib.mkdir()
        # Copy the real dispatcher lib and a minimal bootstrap into the lib/hooks.
        src_lib = _REPO / ".claude" / "lib" / "hook_dispatch.py"
        (lib / "hook_dispatch.py").write_text(src_lib.read_text())
        event_dir = root / "hooks" / "preToolUse"
        event_dir.mkdir(parents=True)
        (event_dir / "_bootstrap.py").write_text(
            "import os, sys\n"
            "from pathlib import Path\n"
            "def ensure_plugin_paths():\n"
            "    root = Path(os.environ['CLAUDE_PLUGIN_ROOT']).resolve()\n"
            "    sys.path.insert(0, str(root / 'lib'))\n"
        )
        allow = "allow.py"
        block = "block.py"
        (event_dir / allow).write_text("import sys; sys.exit(0)\n")
        (event_dir / block).write_text("import sys; sys.exit(2)\n")
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
        (root / ".claude-plugin" / "plugin.json").write_text('{"name":"t"}')
        lib = root / "lib"
        lib.mkdir()
        (lib / "hook_dispatch.py").write_text(
            (_REPO / ".claude" / "lib" / "hook_dispatch.py").read_text()
        )
        event_dir = root / "hooks" / "preToolUse"
        event_dir.mkdir(parents=True)
        (event_dir / "_bootstrap.py").write_text(
            "import os, sys\n"
            "from pathlib import Path\n"
            "def ensure_plugin_paths():\n"
            "    sys.path.insert(0, str(Path(os.environ['CLAUDE_PLUGIN_ROOT']).resolve() / 'lib'))\n"
        )
        (event_dir / "a.py").write_text("import sys; sys.exit(0)\n")
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
        (root / ".claude-plugin" / "plugin.json").write_text('{"name":"t"}')
        lib = root / "lib"
        lib.mkdir()
        (lib / "hook_dispatch.py").write_text(
            (_REPO / ".claude" / "lib" / "hook_dispatch.py").read_text()
        )
        event_dir = root / "hooks" / "preToolUse"
        event_dir.mkdir(parents=True)
        (event_dir / "_bootstrap.py").write_text(
            "import os, sys\n"
            "from pathlib import Path\n"
            "def ensure_plugin_paths():\n"
            "    sys.path.insert(0, str(Path(os.environ['CLAUDE_PLUGIN_ROOT']).resolve() / 'lib'))\n"
        )
        gd.write_entrypoint(event_dir)
        (event_dir / "_manifest.json").write_text('{"event":"preToolUse"}\n')
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
        (root / ".claude-plugin" / "plugin.json").write_text('{"name":"t"}')
        lib = root / "lib"
        lib.mkdir()
        (lib / "hook_dispatch.py").write_text(
            (_REPO / ".claude" / "lib" / "hook_dispatch.py").read_text()
        )
        event_dir = root / "hooks" / "preToolUse"
        event_dir.mkdir(parents=True)
        (event_dir / "_bootstrap.py").write_text(
            "import os, sys\n"
            "from pathlib import Path\n"
            "def ensure_plugin_paths():\n"
            "    sys.path.insert(0, str(Path(os.environ['CLAUDE_PLUGIN_ROOT']).resolve() / 'lib'))\n"
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


class TestShimBasename:
    def test_extracts_python_shim_basename(self):
        command = 'python3 -u "${ROOT}/hooks/PreToolUse/guard.py"'

        assert gd._shim_basename(command) == "guard.py"

    def test_rejects_intermediate_extension_match(self):
        command = 'python3 -u "${ROOT}/hooks/PreToolUse/guard.py.tmp"'

        assert gd._shim_basename(command) is None


class TestConsolidate:
    def test_consolidates_gating_event_only(self, tmp_path):
        hooks_dir = tmp_path / "hooks"
        (hooks_dir / "PreToolUse").mkdir(parents=True)
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
        # gating event collapsed to one dispatcher entry, max timeout
        assert len(new_out["PreToolUse"]) == 1
        assert "/hooks/PreToolUse/_dispatch.py" in new_out["PreToolUse"][0]["bash"]
        assert new_out["PreToolUse"][0]["timeoutSec"] == 90
        # observational event untouched (still per-shim)
        assert new_out["PostToolUse"] == out["PostToolUse"]
        manifest = json.loads((hooks_dir / "PreToolUse" / "_manifest.json").read_text())
        assert manifest["shims"] == ["a.py", "b.py"]

    def test_consolidate_handles_empty_event(self, tmp_path):
        out = {"PreToolUse": []}
        assert gd.consolidate(out, tmp_path) == {"PreToolUse": []}
