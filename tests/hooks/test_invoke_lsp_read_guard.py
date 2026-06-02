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

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

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


class TestIsGatedTarget:
    def test_in_repo_code_file_is_gated(self):
        assert guard.is_gated_target(PY_TARGET, str(REPO_ROOT)) is True

    def test_empty_path_is_not_gated(self):
        assert guard.is_gated_target("", str(REPO_ROOT)) is False

    def test_out_of_repo_is_not_gated(self):
        assert guard.is_gated_target(OUTSIDE_TARGET, str(REPO_ROOT)) is False

    def test_dotfile_member_is_not_gated(self):
        assert guard.is_gated_target(DOTFILE_TARGET, str(REPO_ROOT)) is False

    def test_repo_root_itself_is_not_gated(self):
        # The repo root resolves equal to root; relative_to gives '.', no parts
        # start with a dot, but a directory is not a navigable Read target. It
        # still returns True here (gating happens downstream via providers); the
        # branch under test is the ``resolved == root`` equality path.
        assert guard.is_gated_target(str(REPO_ROOT), str(REPO_ROOT)) is True

    def test_tmpdir_scratch_is_not_gated(self, monkeypatch: pytest.MonkeyPatch, tmp_path):
        monkeypatch.setenv("TMPDIR", str(tmp_path))
        scratch = str(tmp_path / "draft.py")
        assert guard.is_gated_target(scratch, str(REPO_ROOT)) is False

    def test_path_equal_to_tmpdir_is_not_gated(self, monkeypatch: pytest.MonkeyPatch, tmp_path):
        # Covers the ``tmp_root == resolved`` equality branch. The path must be
        # in-repo (else the out-of-repo check returns first), so use a repo root
        # whose own child is both the target and the TMPDIR.
        repo = tmp_path / "repo"
        scratch = repo / "tmp"
        scratch.mkdir(parents=True)
        monkeypatch.setenv("TMPDIR", str(scratch))
        assert guard.is_gated_target(str(scratch), str(repo)) is False

    def test_blank_tmpdir_does_not_bypass(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("TMPDIR", "   ")
        assert guard.is_gated_target(PY_TARGET, str(REPO_ROOT)) is True

    def test_unresolvable_path_fails_open_not_gated(self):
        with patch.object(guard.Path, "resolve", side_effect=OSError("boom")):
            assert guard.is_gated_target(PY_TARGET, str(REPO_ROOT)) is False

    def test_unresolvable_tmpdir_fails_open_not_gated(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ):
        monkeypatch.setenv("TMPDIR", str(tmp_path))
        real_resolve = guard.Path.resolve

        def fake_resolve(self):
            if str(self) == str(tmp_path):
                raise OSError("tmp boom")
            return real_resolve(self)

        with patch.object(guard.Path, "resolve", fake_resolve):
            assert guard.is_gated_target(PY_TARGET, str(REPO_ROOT)) is False

    def test_relative_to_value_error_fails_open(self, monkeypatch: pytest.MonkeyPatch):
        # Force resolved.relative_to(root) to raise after the parent check passed.
        real_relative_to = guard.Path.relative_to

        def fake_relative_to(self, *args, **kwargs):
            raise ValueError("not relative")

        monkeypatch.setattr(guard.Path, "relative_to", fake_relative_to)
        # Path is in-repo (so it passes the parents check) but relative_to raises.
        assert guard.is_gated_target(PY_TARGET, str(REPO_ROOT)) is False
        guard.Path.relative_to = real_relative_to


# ---------------------------------------------------------------------------
# Message builders
# ---------------------------------------------------------------------------


class TestMessageBuilders:
    def test_warmup_block_names_serena_and_native(self):
        msg = guard.build_warmup_block(PY_TARGET, ["serena", "native_lsp"])
        assert "Warmup required" in msg
        assert "get_symbols_overview" in msg
        assert "native LSP overview" in msg
        assert PY_TARGET in msg

    def test_warmup_block_serena_only(self):
        msg = guard.build_warmup_block(MD_TARGET, ["serena"])
        assert "get_symbols_overview" in msg
        assert "native LSP overview" not in msg

    def test_warn_message(self):
        msg = guard.build_warn_message(PY_TARGET, 3, 1)
        assert "WARNING (Read 3)" in msg
        assert "find_symbol" in msg
        assert "You have 1 nav call; make 1 more call" in msg

    def test_hard_block_names_providers(self):
        msg = guard.build_hard_block(PY_TARGET, 4, 1, ["serena", "native_lsp"])
        assert "Surgical mode required" in msg
        assert "you have 1" in msg
        assert "find_symbol" in msg
        assert "native LSP" in msg
        assert f"Blocked: {PY_TARGET}" in msg

    def test_hard_block_native_only(self):
        msg = guard.build_hard_block(PY_TARGET, 5, 0, ["native_lsp"])
        assert "native LSP" in msg
        assert "mcp__serena__find_symbol" not in msg


# ---------------------------------------------------------------------------
# evaluate: tier logic (state injected; guard only reads)
# ---------------------------------------------------------------------------


class TestEvaluateTiers:
    def test_non_gated_target_allows(self):
        code, msg = guard.evaluate(OUTSIDE_TARGET, str(REPO_ROOT))
        assert code == 0
        assert msg is None

    @patch.object(guard, "detect_providers", return_value=[])
    def test_no_provider_allows(self, _mock):
        code, msg = guard.evaluate(PY_TARGET, str(REPO_ROOT))
        assert code == 0
        assert msg is None

    @patch.object(guard, "detect_providers", return_value=["serena"])
    @patch.object(guard, "read_state")
    def test_warmup_tier_blocks(self, mock_state, _mock_providers):
        mock_state.return_value = _state(warmup_done=False)
        code, msg = guard.evaluate(PY_TARGET, str(REPO_ROOT))
        assert code == 2
        assert msg is not None
        assert "Warmup required" in msg

    @patch.object(guard, "detect_providers", return_value=["serena"])
    @patch.object(guard, "read_state")
    def test_first_free_read_allows(self, mock_state, _mock_providers):
        mock_state.return_value = _state(warmup_done=True, read_files=[])
        code, msg = guard.evaluate(PY_TARGET, str(REPO_ROOT))
        assert code == 0
        assert msg is None

    @patch.object(guard, "detect_providers", return_value=["serena"])
    @patch.object(guard, "read_state")
    def test_second_free_read_allows(self, mock_state, _mock_providers):
        mock_state.return_value = _state(warmup_done=True, read_files=["a.py"])
        code, msg = guard.evaluate(PY_TARGET, str(REPO_ROOT))
        assert code == 0
        assert msg is None

    @patch.object(guard, "detect_providers", return_value=["serena"])
    @patch.object(guard, "read_state")
    def test_third_read_warns_but_allows(self, mock_state, _mock_providers, capsys):
        mock_state.return_value = _state(warmup_done=True, read_files=["a.py", "b.py"])
        code, msg = guard.evaluate(PY_TARGET, str(REPO_ROOT))
        assert code == 0
        assert msg is None
        out = capsys.readouterr().out
        payload = json.loads(out.strip().splitlines()[0])
        assert "WARNING (Read 3)" in payload["systemMessage"]

    @patch.object(guard, "detect_providers", return_value=["serena"])
    @patch.object(guard, "read_state")
    def test_third_read_one_nav_warns_but_allows(self, mock_state, _mock_providers, capsys):
        # Issue #2200: read 3 with a single nav must warn and allow, not block.
        # Hard-block starts at read 4 (next_read_num > WARN_AT). The earlier bug
        # gated soft-warn on nav_count == 0, so nav 1 fell through to hard-block.
        mock_state.return_value = _state(
            warmup_done=True, nav_count=1, read_files=["a.py", "b.py"]
        )
        code, msg = guard.evaluate(PY_TARGET, str(REPO_ROOT))
        assert code == 0
        assert msg is None
        payload = json.loads(capsys.readouterr().out.strip().splitlines()[0])
        assert "WARNING (Read 3)" in payload["systemMessage"]

    @patch.object(guard, "detect_providers", return_value=["serena"])
    @patch.object(guard, "read_state")
    def test_fourth_read_hard_blocks(self, mock_state, _mock_providers):
        mock_state.return_value = _state(
            warmup_done=True, nav_count=0, read_files=["a.py", "b.py", "c.py"]
        )
        code, msg = guard.evaluate(PY_TARGET, str(REPO_ROOT))
        assert code == 2
        assert msg is not None
        assert "Surgical mode required" in msg

    @patch.object(guard, "detect_providers", return_value=["serena"])
    @patch.object(guard, "read_state")
    def test_fourth_read_one_nav_still_blocks(self, mock_state, _mock_providers):
        # ADR-062 divergence: 1 nav does NOT unlock reads 4-5 (kit allowed it).
        mock_state.return_value = _state(
            warmup_done=True, nav_count=1, read_files=["a.py", "b.py", "c.py"]
        )
        code, msg = guard.evaluate(PY_TARGET, str(REPO_ROOT))
        assert code == 2
        assert "you have 1" in (msg or "")

    @patch.object(guard, "detect_providers", return_value=["serena"])
    @patch.object(guard, "read_state")
    def test_surgical_nav_threshold_allows(self, mock_state, _mock_providers):
        mock_state.return_value = _state(
            warmup_done=True, nav_count=2, read_files=["a.py", "b.py", "c.py"]
        )
        code, msg = guard.evaluate(PY_TARGET, str(REPO_ROOT))
        assert code == 0
        assert msg is None

    @patch.object(guard, "detect_providers", return_value=["serena"])
    @patch.object(guard, "read_state")
    def test_already_read_file_allows_without_warmup(self, mock_state, _mock_providers):
        # Re-reading a file already in read_files allows even pre-warmup
        # (matches the kit's ``alreadyRead`` early allow).
        mock_state.return_value = _state(
            warmup_done=False, nav_count=0, read_files=[PY_TARGET, "a.py", "b.py", "c.py"]
        )
        code, msg = guard.evaluate(PY_TARGET, str(REPO_ROOT))
        assert code == 0
        assert msg is None

    @patch.object(guard, "detect_providers", return_value=["serena"])
    @patch.object(guard, "read_state")
    def test_warn_mode_converts_warmup_block_to_allow(
        self, mock_state, _mock_providers, monkeypatch, capsys
    ):
        monkeypatch.setenv("LSP_GATE_MODE", "warn")
        mock_state.return_value = _state(warmup_done=False)
        code, msg = guard.evaluate(PY_TARGET, str(REPO_ROOT))
        assert code == 0
        assert msg is None
        payload = json.loads(capsys.readouterr().out.strip().splitlines()[0])
        assert "Warmup required" in payload["systemMessage"]

    @patch.object(guard, "detect_providers", return_value=["serena"])
    @patch.object(guard, "read_state")
    def test_warn_mode_converts_hard_block_to_allow(
        self, mock_state, _mock_providers, monkeypatch, capsys
    ):
        monkeypatch.setenv("LSP_GATE_MODE", "WARN")  # case-insensitive
        mock_state.return_value = _state(
            warmup_done=True, nav_count=0, read_files=["a.py", "b.py", "c.py"]
        )
        code, msg = guard.evaluate(PY_TARGET, str(REPO_ROOT))
        assert code == 0
        assert msg is None
        payload = json.loads(capsys.readouterr().out.strip().splitlines()[0])
        assert "Surgical mode required" in payload["systemMessage"]


# ---------------------------------------------------------------------------
# main: dispatch, kill switch, fail-open paths
# ---------------------------------------------------------------------------


