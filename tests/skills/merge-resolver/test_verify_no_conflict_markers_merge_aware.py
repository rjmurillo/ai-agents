#!/usr/bin/env python3
"""Merge-aware base-ref tests for verify_no_conflict_markers.py.

Issue #4058. ``git diff HEAD --check`` compares against the topic tip
while a merge is in progress, so every line arriving from ``MERGE_HEAD``
reads as newly added. A fenced ``<<<<<<<`` example committed on the
incoming branch then fails the Phase 3 BLOCKING gate even though the
resolution is clean.

These tests build real in-progress merges in ``tmp_path`` because the
behavior under test is the exact interaction between ``MERGE_HEAD`` and
``git diff --check``. Only the failure paths mock the ``subprocess``
boundary.

Split from ``test_verify_no_conflict_markers.py`` to keep both modules
under the 500-line file cap.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script  # noqa: E402

mod = import_skill_script(".claude/skills/merge-resolver/scripts/verify_no_conflict_markers.py")
verify = mod.verify
main = mod.main

FENCED_EXAMPLE = "# doc\n\n```text\n<<<<<<< HEAD\nfoo\n=======\nbar\n>>>>>>> other\n```\n"
GENUINE_MARKERS = "a\n<<<<<<< HEAD\nx\n=======\ny\n>>>>>>> main\n"


def _git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run git in ``cwd``. These tests need real git, not a mock."""
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=check,
    )


@pytest.fixture()
def seeded_repo(tmp_path: Path) -> Path:
    """A repo on ``main`` with one committed file."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "shared.txt").write_text("base\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    return repo


@pytest.fixture()
def merge_in_progress(seeded_repo: Path) -> Path:
    """Topic branch mid-merge with main, conflict resolved and staged.

    ``main`` carries two files the topic branch never had: ``doc.md``
    with a committed fenced ``<<<<<<<`` example, and ``ws.txt`` with
    trailing whitespace plus a blank line at EOF. Diffing against topic
    ``HEAD`` makes both read as newly added, which is the issue #4058
    false positive. Diffing against ``MERGE_HEAD`` sees them unchanged.
    """
    _git(seeded_repo, "checkout", "-q", "-b", "topic")
    (seeded_repo / "shared.txt").write_text("topic\n")
    _git(seeded_repo, "commit", "-q", "-am", "topic edit")

    _git(seeded_repo, "checkout", "-q", "main")
    (seeded_repo / "shared.txt").write_text("main\n")
    (seeded_repo / "doc.md").write_text(FENCED_EXAMPLE)
    (seeded_repo / "ws.txt").write_text("trailing ws   \n\n")
    _git(seeded_repo, "add", "-A")
    _git(seeded_repo, "commit", "-q", "-m", "main adds fenced example and whitespace")

    _git(seeded_repo, "checkout", "-q", "topic")
    merge = _git(seeded_repo, "merge", "main", "--no-commit", check=False)
    assert merge.returncode != 0, "expected a merge conflict on shared.txt"

    (seeded_repo / "shared.txt").write_text("resolved\n")
    _git(seeded_repo, "add", "shared.txt")
    return seeded_repo


@pytest.fixture()
def repo_not_merging(seeded_repo: Path) -> Path:
    """A repo with a committed fenced example and no merge in progress."""
    (seeded_repo / "doc.md").write_text(FENCED_EXAMPLE)
    _git(seeded_repo, "add", "-A")
    _git(seeded_repo, "commit", "-q", "-m", "docs: fenced example")
    return seeded_repo


# ---------------------------------------------------------------------------
# The false positive the fix removes
# ---------------------------------------------------------------------------


class TestInheritedContentDoesNotFail:
    def test_fixture_reproduces_the_single_ref_false_positive(
        self,
        merge_in_progress: Path,
    ) -> None:
        """Guard the fixture: the raw single-ref check must still be dirty.

        If this stops failing, the fixture no longer reproduces #4058
        and the regressions below would pass for the wrong reason.
        """
        head_check = _git(merge_in_progress, "diff", "HEAD", "--check", check=False)
        assert head_check.returncode == 2
        assert "doc.md" in head_check.stdout

        incoming_check = _git(merge_in_progress, "diff", "MERGE_HEAD", "--check", check=False)
        assert incoming_check.returncode == 0

    def test_incoming_fenced_example_does_not_fail_the_merge(
        self,
        merge_in_progress: Path,
    ) -> None:
        exit_code, report = verify(merge_in_progress)
        assert exit_code == 0, f"issue #4058 regressed; report={report!r}"
        assert report["ok"] is True
        assert report["leftover_markers"] == []

    def test_incoming_whitespace_does_not_fail_the_merge(
        self,
        merge_in_progress: Path,
    ) -> None:
        """ws.txt arrives from main carrying pre-existing whitespace."""
        assert (merge_in_progress / "ws.txt").read_text() == "trailing ws   \n\n"

        exit_code, report = verify(merge_in_progress)
        assert exit_code == 0
        assert report["leftover_markers"] == []

    def test_topic_side_fenced_example_does_not_fail_the_merge(
        self,
        seeded_repo: Path,
    ) -> None:
        """A fenced example committed on the topic side is excluded too.

        It appears only in the ``MERGE_HEAD`` diff, so the intersection
        drops it the same way it drops the incoming-side one.
        """
        _git(seeded_repo, "checkout", "-q", "-b", "topic")
        (seeded_repo / "doc.md").write_text(FENCED_EXAMPLE)
        (seeded_repo / "shared.txt").write_text("topic\n")
        _git(seeded_repo, "add", "-A")
        _git(seeded_repo, "commit", "-q", "-m", "topic adds fenced example")

        _git(seeded_repo, "checkout", "-q", "main")
        (seeded_repo / "shared.txt").write_text("main\n")
        _git(seeded_repo, "commit", "-q", "-am", "main edit")

        _git(seeded_repo, "checkout", "-q", "topic")
        _git(seeded_repo, "merge", "main", "--no-commit", check=False)
        (seeded_repo / "shared.txt").write_text("resolved\n")
        _git(seeded_repo, "add", "shared.txt")

        exit_code, report = verify(seeded_repo)
        assert exit_code == 0, f"topic-side inherited example flagged; report={report!r}"


# ---------------------------------------------------------------------------
# Real markers still fail
# ---------------------------------------------------------------------------


class TestGenuineMarkersStillFlagged:
    def test_staged_marker_mid_merge_is_flagged(self, merge_in_progress: Path) -> None:
        """The intersection must not mask a marker the resolution introduced."""
        (merge_in_progress / "shared.txt").write_text(GENUINE_MARKERS)
        _git(merge_in_progress, "add", "shared.txt")

        exit_code, report = verify(merge_in_progress)
        assert exit_code == 1
        assert report["ok"] is False
        assert any("shared.txt" in m for m in report["leftover_markers"])
        assert not any("doc.md" in m for m in report["leftover_markers"])

    def test_unstaged_marker_mid_merge_is_flagged(self, merge_in_progress: Path) -> None:
        """Working-tree coverage survives; the fix did not move to --cached."""
        (merge_in_progress / "shared.txt").write_text(GENUINE_MARKERS)

        exit_code, report = verify(merge_in_progress)
        assert exit_code == 1
        assert any("shared.txt" in m for m in report["leftover_markers"])

    def test_marker_outside_a_merge_is_flagged(self, repo_not_merging: Path) -> None:
        """With no MERGE_HEAD, the single-ref HEAD path still decides."""
        assert not (repo_not_merging / ".git" / "MERGE_HEAD").exists()
        (repo_not_merging / "shared.txt").write_text(GENUINE_MARKERS)

        exit_code, report = verify(repo_not_merging)
        assert exit_code == 1
        assert any("shared.txt" in m for m in report["leftover_markers"])


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestMergeHeadProbeEdges:
    def test_missing_merge_head_is_not_an_error(self, repo_not_merging: Path) -> None:
        """A failed MERGE_HEAD probe means "not merging", never exit 3."""
        exit_code, report = verify(repo_not_merging)
        assert exit_code == 0
        assert report["ok"] is True

    def test_merge_head_is_not_probed_when_head_diff_is_clean(
        self,
        repo_not_merging: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A clean HEAD diff short-circuits; no second git call is spent."""
        real_run_git = mod._run_git
        calls: list[list[str]] = []

        def recording_run_git(
            args: list[str],
            cwd: Path | None = None,
        ) -> subprocess.CompletedProcess[str]:
            calls.append(args)
            return real_run_git(args, cwd=cwd)

        monkeypatch.setattr(mod, "_run_git", recording_run_git)

        exit_code, _ = verify(repo_not_merging)
        assert exit_code == 0
        assert not any("MERGE_HEAD" in " ".join(args) for args in calls)

    def test_octopus_merge_falls_back_to_the_head_only_path(
        self,
        seeded_repo: Path,
    ) -> None:
        """Several MERGE_HEAD parents fail ``--verify``, so HEAD alone decides.

        That over-reports rather than under-reports, which is the safe
        direction for a blocking gate.
        """
        for name in ("b1", "b2"):
            _git(seeded_repo, "checkout", "-q", "-b", name, "main")
            (seeded_repo / f"{name}.txt").write_text(f"{name}\n")
            _git(seeded_repo, "add", "-A")
            _git(seeded_repo, "commit", "-q", "-m", f"{name} file")

        _git(seeded_repo, "checkout", "-q", "main")
        merge = _git(seeded_repo, "merge", "--no-commit", "b1", "b2", check=False)
        assert merge.returncode == 0, merge.stderr
        assert (seeded_repo / ".git" / "MERGE_HEAD").read_text().count("\n") == 2

        (seeded_repo / "shared.txt").write_text(GENUINE_MARKERS)

        exit_code, report = verify(seeded_repo)
        assert exit_code == 1
        assert any("shared.txt" in m for m in report["leftover_markers"])

    def test_marker_location_splits_from_the_right(self) -> None:
        """A path containing ": " must not truncate the intersection key."""
        assert mod._marker_location("doc.md:4: leftover conflict marker") == "doc.md:4"
        assert (
            mod._marker_location("odd: name.md:12: leftover conflict marker") == "odd: name.md:12"
        )

    def test_unexpected_git_failure_on_incoming_diff_maps_to_exit_3(
        self,
        merge_in_progress: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A broken ``git diff MERGE_HEAD --check`` surfaces as external error."""
        real_run_git = mod._run_git

        def failing_run_git(
            args: list[str],
            cwd: Path | None = None,
        ) -> subprocess.CompletedProcess[str]:
            if args[:3] == ["diff", "MERGE_HEAD", "--check"]:
                return subprocess.CompletedProcess(
                    ["git", *args], 128, stdout="", stderr="fatal: bad revision"
                )
            return real_run_git(args, cwd=cwd)

        monkeypatch.setattr(mod, "_run_git", failing_run_git)

        exit_code, report = verify(merge_in_progress)
        assert exit_code == 3
        assert report["error"] == "git_failed"
        assert "MERGE_HEAD" in str(report["detail"])


# ---------------------------------------------------------------------------
# CLI exit codes
# ---------------------------------------------------------------------------


class TestCliExitCodesMidMerge:
    def test_main_returns_zero_for_inherited_content(
        self,
        merge_in_progress: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        exit_code = main(["--cwd", str(merge_in_progress), "--json"])
        parsed = json.loads(capsys.readouterr().out)
        assert exit_code == 0
        assert parsed["ok"] is True
        assert parsed["leftover_markers"] == []

    def test_main_returns_one_for_genuine_marker(
        self,
        merge_in_progress: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        (merge_in_progress / "shared.txt").write_text(GENUINE_MARKERS)
        _git(merge_in_progress, "add", "shared.txt")

        exit_code = main(["--cwd", str(merge_in_progress), "--json"])
        parsed = json.loads(capsys.readouterr().out)
        assert exit_code == 1
        assert parsed["ok"] is False
        assert any("shared.txt" in m for m in parsed["leftover_markers"])
