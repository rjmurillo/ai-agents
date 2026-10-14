"""Added-lines scoping for the measurement-anchoring gate (issue #5771).

The gate judges what a branch adds, so the existing backlog is never
re-policed: that is what lets a new gate pass on day one
(``.claude/rules/ci-scripts.md`` item 13).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.validation.measurement_anchoring_helpers import (
    ANCHORED,
    UNANCHORED,
    _add_doc,
    _git,
    _repo,
    _run,
    checker,
    cite,
)


def _repo_with_base_doc(tmp_path: Path, relpath: str, text: str) -> Path:
    """Create a repo whose main already carries relpath with the given text."""
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test")
    path = root / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    _git(root, "checkout", "-q", "-b", "feature")
    return root


class TestAddedLinesOnly:
    def test_untouched_stale_line_elsewhere_in_the_file_is_ignored(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _repo_with_base_doc(tmp_path, "docs/guide.md", f"{UNANCHORED}\n")
        _add_doc(root, "docs/guide.md", f"{UNANCHORED}\n{ANCHORED}\n")
        code, out = _run(root, capsys)
        assert code == 0
        assert "examined 1 line(s) across 1 file(s)" in out

    def test_editing_the_stale_line_makes_it_new_and_flagged(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _repo_with_base_doc(tmp_path, "docs/guide.md", f"{UNANCHORED}\n")
        _add_doc(root, "docs/guide.md", "This tree holds 48 tracked files.\n")
        code, out = _run(root, capsys)
        assert code == 1
        assert cite("docs/guide.md", 1) in out

    def test_deleting_the_stale_line_is_clean(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _repo_with_base_doc(tmp_path, "docs/guide.md", f"{UNANCHORED}\nkept\n")
        _add_doc(root, "docs/guide.md", "kept\n")
        code, out = _run(root, capsys)
        assert code == 0
        assert "examined 0 line(s) across 0 file(s)" in out

    def test_pure_rename_does_not_reread_the_backlog(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _repo_with_base_doc(tmp_path, "docs/old.md", f"{UNANCHORED}\n")
        _git(root, "mv", "docs/old.md", "docs/new.md")
        _git(root, "commit", "-q", "-m", "rename")
        code, _out = _run(root, capsys)
        assert code == 0

    def test_root_move_respelling_asserts_nothing_new(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        old = "There are 23 agents under `.agents/analysis/`.\n"
        new = "There are 23 agents under `.project-toolkit/analysis/`.\n"
        root = _repo_with_base_doc(tmp_path, "docs/guide.md", old)
        _add_doc(root, "docs/guide.md", new)
        code, _out = _run(root, capsys)
        assert code == 0

    def test_line_number_is_the_head_line_not_the_hunk_offset(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _repo_with_base_doc(tmp_path, "docs/guide.md", "a\nb\nc\n")
        _add_doc(root, "docs/guide.md", f"a\nb\nc\nd\n{UNANCHORED}\n")
        code, out = _run(root, capsys)
        assert code == 1
        assert cite("docs/guide.md", 5) in out


class TestFenceStateComesFromHead:
    def test_added_line_inside_a_fence_opened_by_an_unchanged_line_is_skipped(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _repo_with_base_doc(tmp_path, "docs/guide.md", "```text\n```\n")
        _add_doc(root, "docs/guide.md", f"```text\n{UNANCHORED}\n```\n")
        code, _out = _run(root, capsys)
        assert code == 0

    def test_added_line_after_the_fence_closes_is_flagged(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _repo_with_base_doc(tmp_path, "docs/guide.md", "```text\n```\n")
        _add_doc(root, "docs/guide.md", f"```text\n```\n{UNANCHORED}\n")
        code, out = _run(root, capsys)
        assert code == 1
        assert cite("docs/guide.md", 3) in out


class TestTreeMode:
    def test_tree_mode_reports_the_backlog_the_diff_gate_ignores(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _repo_with_base_doc(tmp_path, "docs/guide.md", f"{UNANCHORED}\n")
        diff_code, _out = _run(root, capsys)
        tree_code, out = _run(root, capsys, "--tree")
        assert diff_code == 0
        assert tree_code == 1
        assert cite("docs/guide.md", 1) in out
        assert "every line at HEAD" in out

    def test_tree_mode_passes_when_every_claim_is_anchored(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _repo_with_base_doc(tmp_path, "docs/guide.md", f"{ANCHORED}\n")
        tree_code, out = _run(root, capsys, "--tree")
        assert tree_code == 0
        assert "examined 1 line(s) across 1 file(s)" in out

    def test_tree_mode_needs_no_base_ref(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _repo(tmp_path)
        code = checker.main(["--repo-root", str(root), "--tree"])
        assert code == 0
        assert "every line at HEAD" in capsys.readouterr().out
