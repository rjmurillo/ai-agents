"""Tests for scripts/hook_utilities/lsp_gate_state.py (ADR-062 gate state).

Covers the state-file path scheme (sha256(cwd)[:16], outside the working tree),
read/write/reset, the warmup-then-nav increment, read tracking, threshold
constants, and every fail-open path (missing file, malformed JSON, non-dict
JSON, tampered types, unwritable directory). Tests isolate state to a temp dir
via XDG_STATE_HOME so the real ~/.cache is never touched.
"""

from __future__ import annotations

import hashlib

import pytest

from scripts.hook_utilities import lsp_gate_state
from scripts.hook_utilities.lsp_gate_state import (
    FREE_READS,
    NAV_REQUIRED,
    WARN_AT,
    normalize_path,
    read_state,
    record_nav,
    record_read,
    record_warmup,
    reset_state,
    state_path,
    write_state,
)

_CWD = "/home/user/project"


@pytest.fixture(autouse=True)
def isolate_state(tmp_path, monkeypatch):
    """Point the gate-state dir at a temp dir for every test."""
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    return tmp_path


# ---------------------------------------------------------------------------
# Path scheme
# ---------------------------------------------------------------------------


class TestStatePath:
    def test_uses_sha256_first_16_hex(self, tmp_path):
        expected_key = hashlib.sha256(_CWD.encode("utf-8")).hexdigest()[:16]
        path = state_path(_CWD)
        assert path.name == f"lsp-gate-{expected_key}.json"

    def test_outside_working_tree_under_xdg_state_home(self, tmp_path):
        path = state_path(_CWD)
        assert str(path).startswith(str(tmp_path / "state"))
        assert "ai-agents-lsp-gate" in str(path)

    def test_falls_back_to_cache_without_xdg(self, monkeypatch):
        monkeypatch.delenv("XDG_STATE_HOME", raising=False)
        fake_home = "/home/fakeuser"
        monkeypatch.setattr(
            lsp_gate_state.Path, "home", classmethod(lambda cls: lsp_gate_state.Path(fake_home))
        )
        path = state_path(_CWD)
        key = lsp_gate_state._cwd_key(_CWD)
        assert str(path) == f"{fake_home}/.cache/ai-agents-lsp-gate/lsp-gate-{key}.json"

    def test_empty_xdg_falls_back_to_cache(self, monkeypatch):
        monkeypatch.setenv("XDG_STATE_HOME", "   ")
        fake_home = lsp_gate_state.Path("/home/fakeuser")
        monkeypatch.setattr(lsp_gate_state.Path, "home", classmethod(lambda cls: fake_home))
        assert ".cache/ai-agents-lsp-gate" in str(state_path(_CWD))

    def test_distinct_cwds_distinct_files(self):
        assert state_path("/a") != state_path("/b")


# ---------------------------------------------------------------------------
# Threshold constants
# ---------------------------------------------------------------------------


class TestThresholds:
    def test_constants(self):
        assert NAV_REQUIRED == 2
        assert FREE_READS == 2
        assert WARN_AT == 3


# ---------------------------------------------------------------------------
# read_state: defaults and fail-open
# ---------------------------------------------------------------------------


class TestReadState:
    def test_missing_file_returns_needs_warmup_default(self):
        state = read_state(_CWD)
        assert state == {
            "cwd": _CWD,
            "warmup_done": False,
            "nav_count": 0,
            "read_count": 0,
            "read_files": [],
            "last_tool": "",
        }

    def test_malformed_json_returns_default(self):
        path = state_path(_CWD)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{not json", encoding="utf-8")
        assert read_state(_CWD)["warmup_done"] is False

    def test_non_dict_json_returns_default(self):
        path = state_path(_CWD)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("[1, 2, 3]", encoding="utf-8")
        assert read_state(_CWD)["nav_count"] == 0

    def test_unreadable_file_returns_default(self):
        path = state_path(_CWD)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Make the state file a directory so read_text raises OSError
        path.mkdir()
        assert read_state(_CWD)["warmup_done"] is False

    def test_normalizes_tampered_types(self):
        write_state(_CWD, {"cwd": _CWD})  # establish file then corrupt
        path = state_path(_CWD)
        path.write_text(
            '{"cwd": 5, "warmup_done": "yes", "nav_count": "bad", '
            '"read_count": -3, "read_files": "notalist", "last_tool": 7}',
            encoding="utf-8",
        )
        state = read_state(_CWD)
        assert state["cwd"] == "5"
        assert state["warmup_done"] is True  # bool("yes")
        assert state["nav_count"] == 0  # uncoercible -> 0
        assert state["read_count"] == 0  # negative clamped to 0
        assert state["read_files"] == []
        assert state["last_tool"] == "7"

    def test_read_files_elements_coerced_to_str(self):
        path = state_path(_CWD)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"read_files": [1, "a.py", 2]}', encoding="utf-8")
        assert read_state(_CWD)["read_files"] == ["1", "a.py", "2"]


# ---------------------------------------------------------------------------
# write_state
# ---------------------------------------------------------------------------


class TestWriteState:
    def test_round_trip(self):
        state = {
            "cwd": _CWD,
            "warmup_done": True,
            "nav_count": 3,
            "read_count": 2,
            "read_files": ["a.py", "b.py"],
            "last_tool": "mcp__serena__find_symbol",
        }
        assert write_state(_CWD, state) is True
        assert read_state(_CWD) == state

    def test_creates_state_dir(self):
        path = state_path(_CWD)
        assert not path.parent.exists()
        write_state(_CWD, {"cwd": _CWD})
        assert path.parent.is_dir()

    def test_returns_false_on_oserror(self, monkeypatch):
        def boom(self, *a, **k):
            raise OSError("disk full")

        monkeypatch.setattr(lsp_gate_state.Path, "mkdir", boom)
        assert write_state(_CWD, {"cwd": _CWD}) is False


# ---------------------------------------------------------------------------
# reset_state (SessionStart, idempotent)
# ---------------------------------------------------------------------------


class TestResetState:
    def test_removes_existing(self):
        write_state(_CWD, {"cwd": _CWD, "warmup_done": True})
        assert state_path(_CWD).exists()
        assert reset_state(_CWD) is True
        assert not state_path(_CWD).exists()

    def test_idempotent_when_absent(self):
        assert not state_path(_CWD).exists()
        assert reset_state(_CWD) is True
        assert reset_state(_CWD) is True

    def test_returns_false_on_oserror(self, monkeypatch):
        def boom(self, *a, **k):
            raise OSError("locked")

        monkeypatch.setattr(lsp_gate_state.Path, "unlink", boom)
        assert reset_state(_CWD) is False


# ---------------------------------------------------------------------------
# record_warmup / record_nav (kit warmup-then-nav semantics)
# ---------------------------------------------------------------------------


class TestRecordWarmupAndNav:
    def test_warmup_sets_flag_keeps_nav_zero(self):
        state = record_warmup(_CWD)
        assert state["warmup_done"] is True
        assert state["nav_count"] == 0

    def test_warmup_idempotent_on_flag(self):
        record_warmup(_CWD)
        state = record_warmup(_CWD)
        assert state["warmup_done"] is True
        assert state["nav_count"] == 0

    def test_first_nav_performs_warmup_no_increment(self):
        state = record_nav(_CWD)
        assert state["warmup_done"] is True
        assert state["nav_count"] == 0

    def test_subsequent_navs_increment(self):
        record_nav(_CWD)  # warmup
        record_nav(_CWD)  # nav 1
        state = record_nav(_CWD)  # nav 2
        assert state["nav_count"] == 2
        assert state["warmup_done"] is True

    def test_nav_after_explicit_warmup_increments(self):
        record_warmup(_CWD)
        state = record_nav(_CWD)
        assert state["nav_count"] == 1


# ---------------------------------------------------------------------------
# record_read
# ---------------------------------------------------------------------------


class TestRecordRead:
    def test_appends_unique_files(self):
        record_read(_CWD, "a.py")
        state = record_read(_CWD, "b.py")
        assert state["read_files"] == [
            normalize_path("a.py", _CWD),
            normalize_path("b.py", _CWD),
        ]
        assert state["read_count"] == 2

    def test_dedupes(self):
        record_read(_CWD, "a.py")
        state = record_read(_CWD, "a.py")
        assert state["read_files"] == [normalize_path("a.py", _CWD)]
        assert state["read_count"] == 1

    def test_empty_file_path_not_appended(self):
        state = record_read(_CWD, "")
        assert state["read_files"] == []
        assert state["read_count"] == 0

    def test_read_count_tracks_unique_set(self):
        record_read(_CWD, "a.py")
        record_read(_CWD, "b.py")
        record_read(_CWD, "a.py")
        state = record_read(_CWD, "c.py")
        assert state["read_count"] == 3


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


class TestInternals:
    def test_coerce_int_valid(self):
        assert lsp_gate_state._coerce_int(5) == 5

    def test_coerce_int_string_number(self):
        assert lsp_gate_state._coerce_int("4") == 4

    def test_coerce_int_invalid(self):
        assert lsp_gate_state._coerce_int(None) == 0
        assert lsp_gate_state._coerce_int("abc") == 0

    def test_coerce_int_negative_clamped(self):
        assert lsp_gate_state._coerce_int(-2) == 0

    def test_cwd_key_length(self):
        assert len(lsp_gate_state._cwd_key(_CWD)) == 16


# ---------------------------------------------------------------------------
# is_gated_target — merge/rebase + conflict-marker bypass (Issue #2454)
# ---------------------------------------------------------------------------


class TestMergeInProgressHelper:
    """Direct unit tests for ``_merge_in_progress`` (Issue #2454).

    The helper checks for sentinel paths under the active git admin directory:
    any filesystem error degrades to ``False`` so the helper does not synthesize
    a bypass when the state cannot be observed.
    """

    def test_returns_false_with_no_marker(self, tmp_path):
        repo = tmp_path / "repo"
        (repo / ".git").mkdir(parents=True)
        assert lsp_gate_state._merge_in_progress(str(repo)) is False

    def test_returns_true_for_merge_head(self, tmp_path):
        repo = tmp_path / "repo"
        (repo / ".git").mkdir(parents=True)
        (repo / ".git" / "MERGE_HEAD").write_text("sha", encoding="utf-8")
        assert lsp_gate_state._merge_in_progress(str(repo)) is True

    def test_returns_true_for_rebase_merge_dir(self, tmp_path):
        repo = tmp_path / "repo"
        (repo / ".git").mkdir(parents=True)
        (repo / ".git" / "rebase-merge").mkdir()
        assert lsp_gate_state._merge_in_progress(str(repo)) is True

    def test_returns_true_for_rebase_apply_dir(self, tmp_path):
        repo = tmp_path / "repo"
        (repo / ".git").mkdir(parents=True)
        (repo / ".git" / "rebase-apply").mkdir()
        assert lsp_gate_state._merge_in_progress(str(repo)) is True

    def test_returns_true_for_linked_worktree_gitdir_file(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        gitdir = tmp_path / "main.git" / "worktrees" / "repo"
        gitdir.mkdir(parents=True)
        (repo / ".git").write_text(f"gitdir: {gitdir}\n", encoding="utf-8")
        (gitdir / "MERGE_HEAD").write_text("sha", encoding="utf-8")
        assert lsp_gate_state._merge_in_progress(str(repo)) is True

    def test_returns_true_for_relative_linked_worktree_gitdir_file(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        gitdir = tmp_path / "main.git" / "worktrees" / "repo"
        gitdir.mkdir(parents=True)
        (repo / ".git").write_text("gitdir: ../main.git/worktrees/repo\n", encoding="utf-8")
        (gitdir / "rebase-merge").mkdir()
        assert lsp_gate_state._merge_in_progress(str(repo)) is True

    def test_returns_false_for_malformed_gitdir_file(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / ".git").write_text("not a gitdir pointer\n", encoding="utf-8")
        assert lsp_gate_state._merge_in_progress(str(repo)) is False

    def test_returns_false_for_empty_project_dir(self):
        assert lsp_gate_state._merge_in_progress("") is False

    def test_returns_false_when_git_dir_missing(self, tmp_path):
        # No ``.git`` at all (e.g. a bare directory not under version control).
        repo = tmp_path / "repo"
        repo.mkdir()
        assert lsp_gate_state._merge_in_progress(str(repo)) is False

    def test_does_not_bypass_on_oserror(self, tmp_path, monkeypatch):
        # If ``Path.exists`` raises, the helper must not raise or bypass.
        repo = tmp_path / "repo"
        (repo / ".git").mkdir(parents=True)

        def fake_exists(self):
            raise OSError("simulated stat failure")

        monkeypatch.setattr(lsp_gate_state.Path, "exists", fake_exists)
        assert lsp_gate_state._merge_in_progress(str(repo)) is False


class TestHasConflictMarkersHelper:
    """Direct unit tests for ``_has_conflict_markers`` (Issue #2454).

    Detects only line-start anchored markers (``^<<<<<<<``, ``^=======``,
    ``^>>>>>>>``). Binary files and read errors degrade to ``False``.
    """

    def test_detects_open_marker(self, tmp_path):
        target = tmp_path / "f.py"
        target.write_text("<<<<<<< HEAD\nfoo\n", encoding="utf-8")
        assert lsp_gate_state._has_conflict_markers(str(target)) is True

    def test_detects_separator_marker(self, tmp_path):
        target = tmp_path / "f.py"
        target.write_text("foo\n=======\nbar\n", encoding="utf-8")
        assert lsp_gate_state._has_conflict_markers(str(target)) is True

    def test_detects_close_marker(self, tmp_path):
        target = tmp_path / "f.py"
        target.write_text("bar\n>>>>>>> origin/main\n", encoding="utf-8")
        assert lsp_gate_state._has_conflict_markers(str(target)) is True

    def test_clean_file_returns_false(self, tmp_path):
        target = tmp_path / "f.py"
        target.write_text("def foo():\n    return 1\n", encoding="utf-8")
        assert lsp_gate_state._has_conflict_markers(str(target)) is False

    def test_marker_chars_mid_line_return_false(self, tmp_path):
        # Regression: ``<<<<<<< HEAD`` embedded inside a string literal must
        # NOT trigger the bypass. Conflict markers anchor at column 0.
        target = tmp_path / "f.py"
        target.write_text(
            'PATTERN = "<<<<<<< HEAD"  # docstring example\n'
            "VALUE = 1  # =====  marker chars in comment, no anchor\n",
            encoding="utf-8",
        )
        assert lsp_gate_state._has_conflict_markers(str(target)) is False

    def test_empty_file_returns_false(self, tmp_path):
        target = tmp_path / "f.py"
        target.write_text("", encoding="utf-8")
        assert lsp_gate_state._has_conflict_markers(str(target)) is False

    def test_empty_path_returns_false(self):
        assert lsp_gate_state._has_conflict_markers("") is False

    def test_binary_file_returns_false(self, tmp_path):
        target = tmp_path / "bin.bin"
        target.write_bytes(b"\x89PNG\r\n\x1a\n\xff\xfe\xfd<<<<<<<")
        # Invalid UTF-8 returns False, so the helper does not synthesize a bypass.
        assert lsp_gate_state._has_conflict_markers(str(target)) is False

    def test_missing_file_returns_false(self, tmp_path):
        assert lsp_gate_state._has_conflict_markers(str(tmp_path / "missing.py")) is False

    def test_only_scans_leading_window(self, tmp_path, monkeypatch):
        # Bound the scan window to a small size, then write a file whose conflict
        # marker lives past that window. The helper must NOT detect it (proving
        # bounded I/O on huge files).
        monkeypatch.setattr(lsp_gate_state, "_CONFLICT_MARKER_SCAN_BYTES", 64)
        target = tmp_path / "f.py"
        target.write_text(
            ("x = 1\n" * 100)  # well past 64 bytes
            + "<<<<<<< HEAD\n",
            encoding="utf-8",
        )
        assert lsp_gate_state._has_conflict_markers(str(target)) is False

    def test_marker_inside_scan_window_is_detected(self, tmp_path, monkeypatch):
        # Pair with the previous test: prove the helper DOES detect markers
        # that land inside the bounded window.
        monkeypatch.setattr(lsp_gate_state, "_CONFLICT_MARKER_SCAN_BYTES", 4096)
        target = tmp_path / "f.py"
        target.write_text("<<<<<<< HEAD\n" + ("x = 1\n" * 100), encoding="utf-8")
        assert lsp_gate_state._has_conflict_markers(str(target)) is True

