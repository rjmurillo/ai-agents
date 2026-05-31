#!/usr/bin/env python3
"""Tests for the invoke_lsp_read_guard PreToolUse hook (ADR-062).

Covers the graduated Read gate (Warmup, Soft-allow, Soft-warn, Hard-block,
Surgical tiers), the always-bypass target set (out-of-repo, dotfile, TMPDIR),
the no-provider degrade-to-allow path, LSP_GATE_MODE=warn, SKIP_LSP_GATE, and
EVERY fail-open path (tty, empty stdin, malformed JSON, missing tool_input,
non-dict tool_input, missing file_path, wrong tool_name, exception).

Exit codes: 0 = allow (incl. fail-open and warn mode), 2 = block.

The guard only READS gate state; the PostToolUse tracker owns writes. State is
injected here by monkeypatching ``read_state`` so each tier is exercised in
isolation and no test depends on a real state file.
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOK_DIR = REPO_ROOT / ".claude" / "hooks" / "PreToolUse"
sys.path.insert(0, str(HOOK_DIR))

import invoke_lsp_read_guard as guard  # noqa: E402

# A real in-repo file path whose extension is overview-capable (python). The
# file need not exist; detect_providers keys on extension + config, and
# is_gated_target resolves the path without requiring it on disk.
PY_TARGET = str(REPO_ROOT / "scripts" / "sample_module.py")
MD_TARGET = str(REPO_ROOT / "docs" / "sample.md")
TXT_TARGET = str(REPO_ROOT / "sample.txt")
DOTFILE_TARGET = str(REPO_ROOT / ".serena" / "scratch.py")
OUTSIDE_TARGET = "/tmp/outside_sample.py"


def _state(
    *,
    warmup_done: bool = False,
    nav_count: int = 0,
    read_files: list[str] | None = None,
    last_tool: str = "",
) -> dict:
    """Build a gate-state dict in the canonical shape."""
    files = list(read_files or [])
    return {
        "cwd": str(REPO_ROOT),
        "warmup_done": warmup_done,
        "nav_count": nav_count,
        "read_count": len(files),
        "read_files": files,
        "last_tool": last_tool,
    }


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure mode/skip env vars never leak between tests."""
    monkeypatch.delenv("SKIP_LSP_GATE", raising=False)
    monkeypatch.delenv("LSP_GATE_MODE", raising=False)


# ---------------------------------------------------------------------------
# is_gated_target
# ---------------------------------------------------------------------------


class TestMain:
    def test_exits_0_on_tty(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr("sys.stdin", MagicMock(isatty=lambda: True))
        assert guard.main() == 0

    def test_exits_0_on_empty_input(self, mock_stdin: Callable[[str], None]):
        mock_stdin("")
        assert guard.main() == 0

    def test_exits_0_on_whitespace_input(self, mock_stdin: Callable[[str], None]):
        mock_stdin("   \n  ")
        assert guard.main() == 0

    def test_exits_0_on_invalid_json(self, mock_stdin: Callable[[str], None]):
        mock_stdin("not json {")
        assert guard.main() == 0

    def test_exits_0_for_non_read_tool(self, mock_stdin: Callable[[str], None]):
        mock_stdin(json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}}))
        assert guard.main() == 0

    def test_exits_0_for_non_dict_tool_input(self, mock_stdin: Callable[[str], None]):
        mock_stdin(json.dumps({"tool_name": "Read", "tool_input": "string"}))
        assert guard.main() == 0

    def test_exits_0_for_missing_tool_input(self, mock_stdin: Callable[[str], None]):
        mock_stdin(json.dumps({"tool_name": "Read"}))
        assert guard.main() == 0

    def test_exits_0_for_missing_file_path(self, mock_stdin: Callable[[str], None]):
        mock_stdin(json.dumps({"tool_name": "Read", "tool_input": {"file_path": ""}}))
        assert guard.main() == 0

    def test_exits_0_for_none_file_path(self, mock_stdin: Callable[[str], None]):
        mock_stdin(json.dumps({"tool_name": "Read", "tool_input": {"file_path": None}}))
        assert guard.main() == 0

    def test_skip_env_allows(self, mock_stdin: Callable[[str], None], monkeypatch):
        monkeypatch.setenv("SKIP_LSP_GATE", "true")
        mock_stdin(json.dumps({"tool_name": "Read", "tool_input": {"file_path": PY_TARGET}}))
        assert guard.main() == 0

    def test_skip_env_case_insensitive(self, mock_stdin: Callable[[str], None], monkeypatch):
        monkeypatch.setenv("SKIP_LSP_GATE", "TRUE")
        mock_stdin(json.dumps({"tool_name": "Read", "tool_input": {"file_path": PY_TARGET}}))
        assert guard.main() == 0

    def test_skip_env_other_value_does_not_skip(
        self, mock_stdin: Callable[[str], None], monkeypatch
    ):
        monkeypatch.setenv("SKIP_LSP_GATE", "yes")
        mock_stdin(json.dumps({"tool_name": "Read", "tool_input": {"file_path": TXT_TARGET}}))
        # txt is non-provider -> allow regardless, but the skip branch was not taken.
        assert guard.main() == 0

    @patch.object(guard, "skip_if_consumer_repo", return_value=True)
    def test_consumer_repo_allows(self, _mock):
        assert guard.main() == 0

    @patch.object(guard, "detect_providers", return_value=["serena"])
    @patch.object(guard, "read_state")
    def test_blocks_on_warmup_via_main(
        self, mock_state, _mock_providers, mock_stdin: Callable[[str], None], capsys
    ):
        mock_state.return_value = _state(warmup_done=False)
        mock_stdin(json.dumps({"tool_name": "Read", "tool_input": {"file_path": PY_TARGET}}))
        assert guard.main() == 2
        assert "Warmup required" in capsys.readouterr().err

    @patch.object(guard, "detect_providers", return_value=["serena"])
    @patch.object(guard, "read_state")
    def test_allows_surgical_via_main(
        self, mock_state, _mock_providers, mock_stdin: Callable[[str], None]
    ):
        mock_state.return_value = _state(warmup_done=True, nav_count=2)
        mock_stdin(json.dumps({"tool_name": "Read", "tool_input": {"file_path": PY_TARGET}}))
        assert guard.main() == 0

    def test_fails_open_on_exception(self, mock_stdin: Callable[[str], None]):
        mock_stdin(json.dumps({"tool_name": "Read", "tool_input": {"file_path": PY_TARGET}}))
        with patch.object(guard, "get_project_directory", side_effect=RuntimeError("boom")):
            assert guard.main() == 0


# ---------------------------------------------------------------------------
# Entry-point coverage: subprocess feeding stdin + runpy __main__
# ---------------------------------------------------------------------------


class TestModuleAsScript:
    def test_allow_via_subprocess(self):
        """Out-of-repo target allows: exit 0 from a real subprocess."""
        hook_path = str(HOOK_DIR / "invoke_lsp_read_guard.py")
        payload = json.dumps(
            {"tool_name": "Read", "tool_input": {"file_path": OUTSIDE_TARGET}}
        )
        result = subprocess.run(
            [sys.executable, hook_path],
            input=payload,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0

    def test_block_via_subprocess(self, tmp_path):
        """In-repo python target with fresh (absent) state blocks: exit 2."""
        hook_path = str(HOOK_DIR / "invoke_lsp_read_guard.py")
        payload = json.dumps(
            {"tool_name": "Read", "tool_input": {"file_path": PY_TARGET}}
        )
        env = dict(os.environ)
        env["XDG_STATE_HOME"] = str(tmp_path)  # isolated, no warmup recorded
        env.pop("SKIP_LSP_GATE", None)
        env.pop("LSP_GATE_MODE", None)
        result = subprocess.run(
            [sys.executable, hook_path],
            input=payload,
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            env=env,
        )
        assert result.returncode == 2
        assert "Warmup required" in result.stderr

    def test_main_guard_via_runpy(self, monkeypatch: pytest.MonkeyPatch):
        """Cover the ``sys.exit(main())`` guard line via runpy."""
        import runpy

        hook_path = str(HOOK_DIR / "invoke_lsp_read_guard.py")
        monkeypatch.setattr(
            "sys.stdin",
            io.StringIO(
                json.dumps({"tool_name": "Read", "tool_input": {"file_path": OUTSIDE_TARGET}})
            ),
        )
        with pytest.raises(SystemExit) as exc_info:
            runpy.run_path(hook_path, run_name="__main__")
        assert exc_info.value.code == 0


# ---------------------------------------------------------------------------
# Bootstrap (module-level lib resolution): exercised in a fresh interpreter
# because it runs at import time and the in-process module is already loaded.
# ---------------------------------------------------------------------------


class TestBootstrap:
    def test_plugin_root_env_resolves_lib(self, tmp_path):
        """CLAUDE_PLUGIN_ROOT set to the real plugin dir: hook runs (exit 0)."""
        hook_path = str(HOOK_DIR / "invoke_lsp_read_guard.py")
        env = dict(os.environ)
        env["CLAUDE_PLUGIN_ROOT"] = str(REPO_ROOT / ".claude")
        env["XDG_STATE_HOME"] = str(tmp_path)
        env.pop("SKIP_LSP_GATE", None)
        env.pop("LSP_GATE_MODE", None)
        result = subprocess.run(
            [sys.executable, hook_path],
            input=json.dumps(
                {"tool_name": "Read", "tool_input": {"file_path": OUTSIDE_TARGET}}
            ),
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            env=env,
        )
        assert result.returncode == 0

    def test_bootstrap_missing_lib_exits_2(self, tmp_path):
        """CLAUDE_PLUGIN_ROOT pointing at an empty dir: lib absent -> exit 2.

        PreToolUse bootstrap fails closed (cannot decide without the lib),
        matching the canonical invoke_skill_first_guard.py bootstrap.
        """
        hook_path = str(HOOK_DIR / "invoke_lsp_read_guard.py")
        env = dict(os.environ)
        env["CLAUDE_PLUGIN_ROOT"] = str(tmp_path)  # no lib/ here
        result = subprocess.run(
            [sys.executable, hook_path],
            input=json.dumps({"tool_name": "Read", "tool_input": {"file_path": PY_TARGET}}),
            capture_output=True,
            text=True,
            env=env,
        )
        assert result.returncode == 2
        assert "Plugin lib directory not found" in result.stderr
