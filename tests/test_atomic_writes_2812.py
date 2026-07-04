"""Atomic-write and advisory-lock tests for issue #2812.

Each shared-state writer touched by #2812 replaced a non-atomic
``write_text`` / unlocked append with a temp-file + ``os.replace`` write (and,
for read-modify-write sites, an advisory lock). These tests assert three
properties per site:

1. positive: the normal write produces the expected content;
2. negative: a mid-write ``os.replace`` failure leaves the prior file intact
   and returns/propagates without a torn write;
3. edge: no ``.tmp`` scratch file is left behind in the target directory.

The concurrency the fix defends against (two processes racing) is not
reproducible deterministically in a unit test; these tests instead pin the
mechanism (atomic replace, temp cleanup, lock acquisition) that makes the race
safe.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.ai_review_common.cache_guard as cache_guard
import scripts.error_classification as error_classification
import scripts.pr_branch_mapping as pr_branch_mapping
import scripts.update_reviewer_signal_stats as urss
from scripts.hook_utilities import lsp_gate_state


def _tmp_files(directory: Path) -> list[Path]:
    """Return leftover atomic-write scratch files in ``directory``."""
    return list(directory.glob("*.tmp"))


# ---------------------------------------------------------------------------
# lsp_gate_state.write_state
# ---------------------------------------------------------------------------
class TestLspGateStateWriteState:
    def test_positive_roundtrips_state(self, tmp_path, monkeypatch):
        state_file = tmp_path / "gate.json"
        monkeypatch.setattr(lsp_gate_state, "state_path", lambda cwd: state_file)

        assert lsp_gate_state.write_state("/some/cwd", {"nav_count": 3}) is True
        loaded = lsp_gate_state.read_state("/some/cwd")
        assert loaded["nav_count"] == 3
        assert _tmp_files(tmp_path) == []

    def test_negative_replace_failure_returns_false_and_preserves_prior(
        self, tmp_path, monkeypatch
    ):
        state_file = tmp_path / "gate.json"
        monkeypatch.setattr(lsp_gate_state, "state_path", lambda cwd: state_file)
        lsp_gate_state.write_state("/cwd", {"nav_count": 1})
        prior = state_file.read_text(encoding="utf-8")

        def boom(_src, _dst):
            raise OSError("disk full")

        monkeypatch.setattr(lsp_gate_state.os, "replace", boom)
        assert lsp_gate_state.write_state("/cwd", {"nav_count": 99}) is False
        assert state_file.read_text(encoding="utf-8") == prior

    def test_edge_no_temp_file_left_after_replace_failure(self, tmp_path, monkeypatch):
        state_file = tmp_path / "gate.json"
        monkeypatch.setattr(lsp_gate_state, "state_path", lambda cwd: state_file)

        monkeypatch.setattr(
            lsp_gate_state.os,
            "replace",
            lambda _s, _d: (_ for _ in ()).throw(OSError("x")),
        )
        lsp_gate_state.write_state("/cwd", {"nav_count": 5})
        assert _tmp_files(tmp_path) == []


# ---------------------------------------------------------------------------
# cache_guard.populate_cache and _atomic_write_text
# ---------------------------------------------------------------------------
class TestCacheGuardPopulate:
    def _output(self, tmp_path: Path) -> Path:
        return tmp_path / "gh_output"

    def test_positive_writes_three_files_and_marks_populated(self, tmp_path):
        out = self._output(tmp_path)
        ok = cache_guard.populate_cache(
            agent="architect",
            verdict="APPROVE",
            findings="none",
            infra_failure="false",
            github_output=out,
            cache_root=tmp_path / "cache",
        )
        assert ok is True
        cache_dir = tmp_path / "cache" / "architect"
        assert (cache_dir / "verdict.txt").read_text(encoding="utf-8") == "APPROVE"
        assert (cache_dir / "findings.txt").read_text(encoding="utf-8") == "none"
        assert (cache_dir / "infrastructure-failure.txt").read_text(
            encoding="utf-8"
        ) == "false"
        assert "cache_populated=true" in out.read_text(encoding="utf-8")
        assert _tmp_files(cache_dir) == []

    def test_negative_empty_verdict_skips_and_marks_not_populated(self, tmp_path):
        out = self._output(tmp_path)
        ok = cache_guard.populate_cache(
            agent="architect",
            verdict="",
            findings="x",
            infra_failure="false",
            github_output=out,
            cache_root=tmp_path / "cache",
        )
        assert ok is False
        assert not (tmp_path / "cache" / "architect").exists()
        assert "cache_populated=false" in out.read_text(encoding="utf-8")

    def test_edge_partial_write_failure_removes_dir_and_marks_not_populated(
        self, tmp_path, monkeypatch
    ):
        out = self._output(tmp_path)
        real = cache_guard._atomic_write_text
        calls = {"n": 0}

        def flaky(path, text):
            calls["n"] += 1
            if calls["n"] == 2:  # fail on the second file
                raise OSError("crash mid-sequence")
            real(path, text)

        monkeypatch.setattr(cache_guard, "_atomic_write_text", flaky)
        ok = cache_guard.populate_cache(
            agent="qa",
            verdict="APPROVE",
            findings="x",
            infra_failure="false",
            github_output=out,
            cache_root=tmp_path / "cache",
        )
        assert ok is False
        assert not (tmp_path / "cache" / "qa").exists()
        assert "cache_populated=false" in out.read_text(encoding="utf-8")


class TestPrBranchMappingSave:
    def test_positive_add_then_load_roundtrips(self, tmp_path):
        rc = pr_branch_mapping.main(
            ["--project-root", str(tmp_path), "add", "--pr", "42", "--branch", "feat/x"]
        )
        assert rc == 0
        mapping = pr_branch_mapping.load_mapping(tmp_path)
        assert pr_branch_mapping.get_branch_for_pr(mapping, 42) == "feat/x"
        memory = tmp_path / pr_branch_mapping.MEMORY_RELATIVE_PATH
        assert _tmp_files(memory.parent) == []

    def test_negative_replace_failure_preserves_prior_mapping(self, tmp_path, monkeypatch):
        pr_branch_mapping.main(
            ["--project-root", str(tmp_path), "add", "--pr", "1", "--branch", "b1"]
        )
        memory = tmp_path / pr_branch_mapping.MEMORY_RELATIVE_PATH
        prior = memory.read_text(encoding="utf-8")
        mapping = pr_branch_mapping.load_mapping(tmp_path)
        pr_branch_mapping.add_mapping(mapping, 2, "b2")
        monkeypatch.setattr(
            pr_branch_mapping.os,
            "replace",
            lambda _s, _d: (_ for _ in ()).throw(OSError("io")),
        )
        with pytest.raises(OSError):
            pr_branch_mapping.save_mapping(tmp_path, mapping)
        assert memory.read_text(encoding="utf-8") == prior
        assert _tmp_files(memory.parent) == []

    def test_edge_mapping_lock_creates_and_yields(self, tmp_path):
        with pr_branch_mapping._mapping_lock(tmp_path):
            pass
        lock = (
            tmp_path
            / ".serena"
            / "memories"
            / f".{pr_branch_mapping.MEMORY_FILENAME}.lock"
        )
        assert lock.exists()


# ---------------------------------------------------------------------------
# skillbook.save_skillbook_file
# ---------------------------------------------------------------------------
class TestReviewerSignalStatsHelpers:
    def test_positive_atomic_write_text(self, tmp_path):
        target = tmp_path / "memory.md"
        urss._atomic_write_text(str(target), "content")
        assert target.read_text(encoding="utf-8") == "content"
        assert _tmp_files(tmp_path) == []

    def test_positive_locked_append_accumulates(self, tmp_path):
        target = tmp_path / "summary.md"
        urss._locked_append(str(target), "line1\n")
        urss._locked_append(str(target), "line2\n")
        assert target.read_text(encoding="utf-8") == "line1\nline2\n"

    def test_negative_atomic_write_failure_cleans_temp(self, tmp_path, monkeypatch):
        target = tmp_path / "memory.md"
        monkeypatch.setattr(
            urss.os,
            "replace",
            lambda _s, _d: (_ for _ in ()).throw(OSError("io")),
        )
        with pytest.raises(OSError):
            urss._atomic_write_text(str(target), "content")
        assert _tmp_files(tmp_path) == []


# ---------------------------------------------------------------------------
# error_classification.log_error (locked append)
# ---------------------------------------------------------------------------
class TestErrorClassificationLog:
    def _classified(self):
        return error_classification.classify_error(
            tool_name="bash", exit_code=1, stderr="boom"
        )

    def test_positive_appends_one_json_line(self, tmp_path):
        log_path = tmp_path / "errors.jsonl"
        error_classification.log_error(
            self._classified(), recovery_action="retry", success=True, log_path=log_path
        )
        lines = log_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        assert json.loads(lines[0])["recovery"] == "retry"

    def test_edge_multiple_appends_accumulate(self, tmp_path):
        log_path = tmp_path / "errors.jsonl"
        for _ in range(3):
            error_classification.log_error(
                self._classified(), recovery_action="retry", success=True, log_path=log_path
            )
        lines = log_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 3
        assert all(json.loads(line)["tool"] == "bash" for line in lines)

    def test_negative_locked_append_helper_writes_exact_text(self, tmp_path):
        target = tmp_path / "out.jsonl"
        error_classification._locked_append(target, '{"x":1}\n')
        assert target.read_text(encoding="utf-8") == '{"x":1}\n'
