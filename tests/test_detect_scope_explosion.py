"""Tests for detect_scope_explosion module.

Verifies scope explosion detection used in pre-commit hook.
Related: Issue #944, PR #908 (95 files)
"""

from __future__ import annotations

import os
import subprocess
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from scripts.detect_scope_explosion import (
    BLOCK_THRESHOLD,
    STRONG_WARN_THRESHOLD,
    TRUNK_BRANCHES,
    WARN_THRESHOLD,
    ScopeResult,
    detect_scope,
    format_bar,
    get_current_branch,
    get_index_files_against_ref,
    get_merge_base,
    get_merge_head_commit,
    get_ref_commit,
    main,
    report,
    rescope_against_pr_base,
    resolve_base_ref,
    resolve_pr_base_branch,
    strip_remote_prefix,
)

if TYPE_CHECKING:
    from _pytest.capture import CaptureFixture


class TestConstants:
    """Tests for module constants."""

    def test_warn_threshold_is_10(self) -> None:
        assert WARN_THRESHOLD == 10

    def test_strong_warn_threshold_is_20(self) -> None:
        assert STRONG_WARN_THRESHOLD == 20

    def test_block_threshold_is_50(self) -> None:
        assert BLOCK_THRESHOLD == 50

    def test_trunk_branches_contains_main(self) -> None:
        assert "main" in TRUNK_BRANCHES
        assert "master" in TRUNK_BRANCHES


class TestScopeResult:
    """Tests for ScopeResult dataclass."""

    def test_is_frozen(self) -> None:
        result = ScopeResult(
            file_count=5,
            merge_base="abc123",
            current_branch="feat/test",
            files=("a.py", "b.py"),
        )
        with pytest.raises(AttributeError):
            # ruff B010 wants `result.file_count = 10` here, but ScopeResult is a
            # frozen dataclass, so file_count is a read-only field. mypy reports
            # the direct assignment as "Property ... is read-only" and rejects it
            # statically, which defeats a test that must reach runtime to assert
            # the AttributeError. setattr is the intended form: it exercises the
            # runtime frozen-instance enforcement without tripping the static
            # check.
            setattr(result, "file_count", 10)  # noqa: B010


class TestFormatBar:
    """Tests for format_bar function."""

    def test_zero_files(self) -> None:
        bar = format_bar(0, WARN_THRESHOLD)
        assert "0/50" in bar

    def test_at_warn_threshold(self) -> None:
        bar = format_bar(10, WARN_THRESHOLD)
        assert "10/50" in bar

    def test_at_block_threshold(self) -> None:
        bar = format_bar(50, BLOCK_THRESHOLD)
        assert "50/50" in bar

    def test_over_block_threshold(self) -> None:
        bar = format_bar(60, BLOCK_THRESHOLD)
        assert "60/50" in bar


class TestGetCurrentBranch:
    """Tests for get_current_branch function."""

    def test_returns_branch_name(self) -> None:
        branch = get_current_branch()
        # In a git repo, should return a string
        assert branch is None or isinstance(branch, str)

    def test_returns_none_on_failure(self) -> None:
        with patch("scripts.detect_scope_explosion.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            )
            result = get_current_branch()
            assert result is None


class TestResolveBaseRef:
    """Tests for resolve_base_ref function (Issue #2207)."""

    def test_prefers_origin_when_available(self) -> None:
        # origin/main resolves -> use it (worktrees may have stale local main).
        with patch("scripts.detect_scope_explosion.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="abc123\n", stderr=""
            )
            assert resolve_base_ref("main") == "origin/main"
            # First (and only) probe should target origin/<base>.
            first_call_args = mock_run.call_args_list[0].args[0]
            assert "origin/main^{commit}" in first_call_args

    def test_falls_back_to_local_when_origin_missing(self) -> None:
        # origin/main missing, local main present.
        with patch("scripts.detect_scope_explosion.subprocess.run") as mock_run:
            mock_run.side_effect = [
                subprocess.CompletedProcess(args=[], returncode=128, stdout="", stderr=""),
                subprocess.CompletedProcess(args=[], returncode=0, stdout="abc123\n", stderr=""),
            ]
            assert resolve_base_ref("main") == "main"

    def test_returns_none_when_neither_exists(self) -> None:
        with patch("scripts.detect_scope_explosion.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=128, stdout="", stderr=""
            )
            assert resolve_base_ref("main") is None


class TestGetRefCommit:
    """Tests for ref commit resolution helpers."""

    def test_get_ref_commit_returns_sha(self) -> None:
        with patch("scripts.detect_scope_explosion.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="deadbeef\n", stderr=""
            )
            assert get_ref_commit("origin/main") == "deadbeef"

    def test_get_ref_commit_returns_none_on_failure(self) -> None:
        with patch("scripts.detect_scope_explosion.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=128, stdout="", stderr=""
            )
            assert get_ref_commit("missing") is None

    def test_get_merge_head_uses_merge_head_ref(self) -> None:
        with patch(
            "scripts.detect_scope_explosion.get_ref_commit",
            return_value="deadbeef",
        ) as mock_get_ref_commit:
            assert get_merge_head_commit() == "deadbeef"
            mock_get_ref_commit.assert_called_once_with("MERGE_HEAD")


class TestGetMergeBase:
    """Tests for get_merge_base function."""

    def test_returns_none_when_base_ref_unresolvable(self) -> None:
        with patch(
            "scripts.detect_scope_explosion.resolve_base_ref", return_value=None
        ):
            result = get_merge_base("main")
            assert result is None

    def test_returns_none_on_failure(self) -> None:
        # resolve_base_ref succeeds, but merge-base itself fails.
        with patch(
            "scripts.detect_scope_explosion.resolve_base_ref", return_value="origin/main"
        ), patch("scripts.detect_scope_explosion.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=1, stdout="", stderr=""
            )
            result = get_merge_base("main")
            assert result is None

    def test_uses_resolved_ref_for_merge_base(self) -> None:
        # Regression for Issue #2207: must hand origin/main (not bare main) to git merge-base
        # so stale local main in worktrees doesn't poison the diff.
        with patch(
            "scripts.detect_scope_explosion.resolve_base_ref", return_value="origin/main"
        ), patch("scripts.detect_scope_explosion.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="deadbeef1234\n", stderr=""
            )
            result = get_merge_base("main")
            assert result == "deadbeef1234"
            cmd = mock_run.call_args.args[0]
            assert cmd[:3] == ["git", "merge-base", "HEAD"]
            assert cmd[3] == "origin/main"


class TestGetIndexFilesAgainstRef:
    """Tests for staged result diffing against a base ref."""

    def test_parses_file_list(self) -> None:
        with patch("scripts.detect_scope_explosion.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="a.py\nb.py\n", stderr=""
            )
            assert get_index_files_against_ref("origin/main") == ["a.py", "b.py"]

    def test_returns_empty_on_failure(self) -> None:
        with patch("scripts.detect_scope_explosion.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=1, stdout="", stderr=""
            )
            assert get_index_files_against_ref("origin/main") == []

    def test_diffs_cached_index_against_base_ref(self) -> None:
        # The --cached diff against the base ref reflects the final staged tree.
        # A staged deletion of a branch-only file therefore drops out of the
        # count (Issue #3171). Lock in the exact command shape that yields this.
        with patch("scripts.detect_scope_explosion.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="kept.py\n", stderr=""
            )
            assert get_index_files_against_ref("origin/main") == ["kept.py"]
            cmd = mock_run.call_args.args[0]
            assert cmd[:5] == [
                "git",
                "diff",
                "--cached",
                "--name-only",
                "--diff-filter=ACMR",
            ]
            assert cmd[5] == "origin/main"


class TestDetectScope:
    """Tests for detect_scope function."""

    def test_returns_none_on_trunk_branch(self) -> None:
        with patch(
            "scripts.detect_scope_explosion.get_current_branch", return_value="main"
        ):
            result = detect_scope()
            assert result is None

    def test_returns_none_on_no_branch(self) -> None:
        with patch(
            "scripts.detect_scope_explosion.get_current_branch", return_value=None
        ):
            result = detect_scope()
            assert result is None

    def test_returns_none_on_no_merge_base(self) -> None:
        with patch(
            "scripts.detect_scope_explosion.get_current_branch",
            return_value="feat/test",
        ), patch(
            "scripts.detect_scope_explosion.resolve_base_ref", return_value="origin/main"
        ), patch(
            "scripts.detect_scope_explosion.get_merge_head_commit", return_value=None
        ), patch(
            "scripts.detect_scope_explosion.get_merge_base", return_value=None
        ):
            result = detect_scope()
            assert result is None

    def test_returns_scope_result(self) -> None:
        with patch(
            "scripts.detect_scope_explosion.get_current_branch",
            return_value="feat/test",
        ), patch(
            "scripts.detect_scope_explosion.resolve_base_ref", return_value="origin/main"
        ), patch(
            "scripts.detect_scope_explosion.get_merge_head_commit", return_value=None
        ), patch(
            "scripts.detect_scope_explosion.get_merge_base",
            return_value="abc123456789",
        ), patch(
            "scripts.detect_scope_explosion.get_index_files_against_ref",
            return_value=["a.py", "b.py", "c.py"],
        ):
            result = detect_scope()
            assert result is not None
            assert result.file_count == 3
            assert result.current_branch == "feat/test"
            assert "a.py" in result.files
            assert "b.py" in result.files
            assert "c.py" in result.files

    def test_deduplicates_files(self) -> None:
        with patch(
            "scripts.detect_scope_explosion.get_current_branch",
            return_value="feat/test",
        ), patch(
            "scripts.detect_scope_explosion.resolve_base_ref", return_value="origin/main"
        ), patch(
            "scripts.detect_scope_explosion.get_merge_head_commit", return_value=None
        ), patch(
            "scripts.detect_scope_explosion.get_merge_base",
            return_value="abc123456789",
        ), patch(
            "scripts.detect_scope_explosion.get_index_files_against_ref",
            return_value=["a.py", "b.py", "a.py", "c.py"],
        ):
            result = detect_scope()
            assert result is not None
            assert result.file_count == 3

    def test_staged_deletion_of_branch_only_file_subtracts(self) -> None:
        # Regression for Issue #3171 Bug 2: staging the deletion of a
        # branch-only file must lower the count. The non-merge path counts the
        # final staged tree against the merge base via get_index_files_against_ref,
        # so a deleted file simply never appears in that set.
        captured_ref: list[str] = []

        def fake_index_files(ref: str) -> list[str]:
            captured_ref.append(ref)
            # The staged deletion of "removed.py" leaves only these two.
            return ["kept_a.py", "kept_b.py"]

        with patch(
            "scripts.detect_scope_explosion.get_current_branch",
            return_value="feat/test",
        ), patch(
            "scripts.detect_scope_explosion.resolve_base_ref", return_value="origin/main"
        ), patch(
            "scripts.detect_scope_explosion.get_merge_head_commit", return_value=None
        ), patch(
            "scripts.detect_scope_explosion.get_merge_base",
            return_value="base987654321",
        ), patch(
            "scripts.detect_scope_explosion.get_index_files_against_ref",
            side_effect=fake_index_files,
        ):
            result = detect_scope()
            assert result is not None
            assert result.file_count == 2
            assert "removed.py" not in result.files
            # Counted against the merge base, not HEAD or the working tree.
            assert captured_ref == ["base987654321"]

    def test_in_progress_base_merge_counts_index_against_base(self) -> None:
        with patch(
            "scripts.detect_scope_explosion.get_current_branch",
            return_value="feat/test",
        ), patch(
            "scripts.detect_scope_explosion.resolve_base_ref", return_value="origin/main"
        ), patch(
            "scripts.detect_scope_explosion.get_merge_head_commit",
            return_value="base123456789",
        ), patch(
            "scripts.detect_scope_explosion.get_ref_commit",
            return_value="base123456789",
        ), patch(
            "scripts.detect_scope_explosion.is_ancestor",
            return_value=True,
        ), patch(
            "scripts.detect_scope_explosion.get_index_files_against_ref",
            return_value=["pr.py", "tests/test_pr.py"],
        ), patch(
            "scripts.detect_scope_explosion.get_merge_base"
        ) as mock_get_merge_base:
            result = detect_scope()
            assert result is not None
            assert result.file_count == 2
            assert result.files == ("pr.py", "tests/test_pr.py")
            mock_get_merge_base.assert_not_called()

    def test_in_progress_merge_counts_against_merge_head_not_base_ref(self) -> None:
        # Regression for Issue #2376: in a linked-worktree merge where local
        # origin/main has advanced past MERGE_HEAD, counting the staged index
        # against base_ref includes every upstream merge file and surfaces a
        # false scope explosion (observed: 86/50 reported for a 13-file PR).
        # The detector must compare staged result against MERGE_HEAD itself so
        # only the PR's real diff is counted.
        #
        # This case: MERGE_HEAD is newer than the local base ref, so
        # is_ancestor returns False and the MERGE_HEAD path is used.
        captured_args: list[str] = []

        def fake_index_files(ref: str) -> list[str]:
            captured_args.append(ref)
            # Simulate: against MERGE_HEAD only PR files differ (13 files);
            # against base_ref the upstream merge files leak in (86 files).
            if ref == "merge_head_sha":
                return [f"pr_file_{i}.py" for i in range(13)]
            return [f"upstream_{i}.py" for i in range(86)]

        with patch(
            "scripts.detect_scope_explosion.get_current_branch",
            return_value="fix/spec-pipeline-hardening",
        ), patch(
            "scripts.detect_scope_explosion.resolve_base_ref", return_value="origin/main"
        ), patch(
            "scripts.detect_scope_explosion.get_merge_head_commit",
            return_value="merge_head_sha",
        ), patch(
            "scripts.detect_scope_explosion.is_ancestor",
            return_value=False,
        ), patch(
            "scripts.detect_scope_explosion.get_ref_commit",
            return_value="stale_local_main_sha",
        ), patch(
            "scripts.detect_scope_explosion.get_index_files_against_ref",
            side_effect=fake_index_files,
        ), patch(
            "scripts.detect_scope_explosion.get_merge_base"
        ) as mock_get_merge_base:
            result = detect_scope()
            assert result is not None
            # Must reflect the real PR diff against MERGE_HEAD (13), not the
            # staged upstream merge (86).
            assert result.file_count == 13
            assert "merge_head_sha" in captured_args
            mock_get_merge_base.assert_not_called()

    def test_sibling_merge_head_falls_through_to_merge_base(self) -> None:
        # Regression for Issue #4418: when MERGE_HEAD is the branch's own
        # remote tip (behind main), counting staged files against MERGE_HEAD
        # inflates the count by every file main gained since that tip.
        # Observed: 635 reported when 17 were real.
        #
        # This case: MERGE_HEAD is an ancestor of origin/main (the sibling),
        # so is_ancestor returns True and the detector falls through to the
        # normal merge-base path.
        captured_index_args: list[str] = []

        def fake_index_files(ref: str) -> list[str]:
            captured_index_args.append(ref)
            # Against merge_head (behind main): staged index has 635 files
            # because main's delta leaks in as "PR changes".
            if ref == "remote_tip_sha":
                return [f"inflated_{i}.py" for i in range(635)]
            # Against the true merge-base: only the 17 real PR files.
            return [f"real_pr_{i}.py" for i in range(17)]

        with patch(
            "scripts.detect_scope_explosion.get_current_branch",
            return_value="fix/4034-pr-comment-responder",
        ), patch(
            "scripts.detect_scope_explosion.resolve_base_ref", return_value="origin/main"
        ), patch(
            "scripts.detect_scope_explosion.get_merge_head_commit",
            return_value="remote_tip_sha",
        ), patch(
            "scripts.detect_scope_explosion.is_ancestor",
            return_value=True,
        ), patch(
            "scripts.detect_scope_explosion.get_index_files_against_ref",
            side_effect=fake_index_files,
        ), patch(
            "scripts.detect_scope_explosion.get_merge_base",
            return_value="real_merge_base_sha",
        ):
            result = detect_scope()
            assert result is not None
            # Must reflect the real PR diff (17), not the inflated count (635).
            assert result.file_count == 17
            # Must NOT have counted against the remote tip.
            assert "remote_tip_sha" not in captured_index_args

    def test_equal_merge_head_counts_against_merge_head(self) -> None:
        # Regression control: a merge of the current base ref has MERGE_HEAD
        # equal to origin/main. Equal commits are ancestor-or-equal, but this
        # is not the sibling-branch case from Issue #4418.
        captured_index_args: list[str] = []

        def fake_index_files(ref: str) -> list[str]:
            captured_index_args.append(ref)
            if ref == "base_sha":
                return ["real.py"]
            return [f"inflated_{i}.py" for i in range(86)]

        with patch(
            "scripts.detect_scope_explosion.get_current_branch",
            return_value="fix/some-feature",
        ), patch(
            "scripts.detect_scope_explosion.resolve_base_ref", return_value="origin/main"
        ), patch(
            "scripts.detect_scope_explosion.get_merge_head_commit",
            return_value="base_sha",
        ), patch(
            "scripts.detect_scope_explosion.get_ref_commit",
            return_value="base_sha",
        ), patch(
            "scripts.detect_scope_explosion.is_ancestor",
            return_value=True,
        ), patch(
            "scripts.detect_scope_explosion.get_index_files_against_ref",
            side_effect=fake_index_files,
        ), patch(
            "scripts.detect_scope_explosion.get_merge_base"
        ) as mock_get_merge_base:
            result = detect_scope()
            assert result is not None
            assert result.file_count == 1
            assert captured_index_args == ["base_sha"]
            mock_get_merge_base.assert_not_called()

    def test_sibling_merge_head_uses_merge_base_not_merge_head(self) -> None:
        # Isolating control: the sibling path must call get_merge_base, not
        # use MERGE_HEAD as the comparison ref. If get_merge_base is not
        # called, the count is wrong.
        with patch(
            "scripts.detect_scope_explosion.get_current_branch",
            return_value="fix/some-feature",
        ), patch(
            "scripts.detect_scope_explosion.resolve_base_ref", return_value="origin/main"
        ), patch(
            "scripts.detect_scope_explosion.get_merge_head_commit",
            return_value="remote_tip_sha",
        ), patch(
            "scripts.detect_scope_explosion.is_ancestor",
            return_value=True,
        ), patch(
            "scripts.detect_scope_explosion.get_index_files_against_ref",
            return_value=["real.py"],
        ), patch(
            "scripts.detect_scope_explosion.get_merge_base",
            return_value="real_merge_base_sha",
        ) as mock_get_merge_base:
            detect_scope()
            mock_get_merge_base.assert_called_once()


class TestIsAncestor:
    """Tests for is_ancestor helper."""

    def test_returns_true_when_commit_is_ancestor_of_ref(self) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            from scripts.detect_scope_explosion import is_ancestor

            assert is_ancestor("old_sha", "origin/main") is True
            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            assert "--is-ancestor" in args
            assert "old_sha" in args
            assert "origin/main" in args

    def test_returns_false_when_commit_is_not_ancestor(self) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 1
            from scripts.detect_scope_explosion import is_ancestor

            assert is_ancestor("newer_sha", "origin/main") is False

    def test_returns_false_on_error_exit_code(self) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 128
            from scripts.detect_scope_explosion import is_ancestor

            assert is_ancestor("bad_ref", "origin/main") is False

    def test_is_ancestor_true_for_equal_commits(self) -> None:
        # A commit is its own ancestor (git treats equal as ancestor).
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            from scripts.detect_scope_explosion import is_ancestor

            assert is_ancestor("abc123", "abc123") is True


class TestReport:
    """Tests for report function."""

    def test_below_warn_returns_zero(self, capsys: CaptureFixture[str]) -> None:
        result = ScopeResult(
            file_count=5,
            merge_base="abc123",
            current_branch="feat/test",
            files=tuple(f"file{i}.py" for i in range(5)),
        )
        exit_code = report(result)
        assert exit_code == 0

    def test_at_warn_threshold(self, capsys: CaptureFixture[str]) -> None:
        result = ScopeResult(
            file_count=10,
            merge_base="abc123",
            current_branch="feat/test",
            files=tuple(f"file{i}.py" for i in range(10)),
        )
        exit_code = report(result)
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "WARNING" in captured.out

    def test_at_strong_warn_threshold(self, capsys: CaptureFixture[str]) -> None:
        result = ScopeResult(
            file_count=20,
            merge_base="abc123",
            current_branch="feat/test",
            files=tuple(f"file{i}.py" for i in range(20)),
        )
        exit_code = report(result)
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "WARNING" in captured.out
        assert "splitting" in captured.out.lower()

    def test_at_block_threshold_still_allowed(
        self, capsys: CaptureFixture[str]
    ) -> None:
        # Issue #3171 Bug 1: 50 is the inclusive hard limit. It must pass with a
        # strong warning, not block. Blocking begins at 51.
        result = ScopeResult(
            file_count=BLOCK_THRESHOLD,
            merge_base="abc123",
            current_branch="feat/test",
            files=tuple(f"file{i}.py" for i in range(BLOCK_THRESHOLD)),
        )
        exit_code = report(result)
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "WARNING" in captured.out
        assert "BLOCKED" not in captured.out

    def test_just_below_block_threshold_allowed(
        self, capsys: CaptureFixture[str]
    ) -> None:
        result = ScopeResult(
            file_count=BLOCK_THRESHOLD - 1,
            merge_base="abc123",
            current_branch="feat/test",
            files=tuple(f"file{i}.py" for i in range(BLOCK_THRESHOLD - 1)),
        )
        exit_code = report(result)
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "BLOCKED" not in captured.out

    def test_just_over_block_threshold_blocks(
        self, capsys: CaptureFixture[str]
    ) -> None:
        # 51 is the first blocking count.
        result = ScopeResult(
            file_count=BLOCK_THRESHOLD + 1,
            merge_base="abc123",
            current_branch="feat/test",
            files=tuple(f"file{i}.py" for i in range(BLOCK_THRESHOLD + 1)),
        )
        exit_code = report(result)
        assert exit_code == 1
        captured = capsys.readouterr()
        assert "BLOCKED" in captured.out

    def test_over_block_threshold(self, capsys: CaptureFixture[str]) -> None:
        result = ScopeResult(
            file_count=60,
            merge_base="abc123",
            current_branch="feat/test",
            files=tuple(f"file{i}.py" for i in range(60)),
        )
        exit_code = report(result)
        assert exit_code == 1

    def test_quiet_suppresses_below_warn(self, capsys: CaptureFixture[str]) -> None:
        result = ScopeResult(
            file_count=5,
            merge_base="abc123",
            current_branch="feat/test",
            files=tuple(f"file{i}.py" for i in range(5)),
        )
        exit_code = report(result, quiet=True)
        assert exit_code == 0
        captured = capsys.readouterr()
        assert captured.out == ""


class TestMain:
    """Tests for main entry point."""

    def test_bypass_with_env_var(self, capsys: CaptureFixture[str]) -> None:
        with patch.dict(os.environ, {"SKIP_SCOPE_CHECK": "1"}), patch(
            "sys.argv", ["detect_scope_explosion.py"]
        ):
            exit_code = main()
            assert exit_code == 0
            captured = capsys.readouterr()
            assert "bypassed" in captured.out.lower()

    def test_returns_zero_when_no_result(self) -> None:
        with patch.dict(os.environ, {}, clear=False), patch(
            "scripts.detect_scope_explosion.detect_scope", return_value=None
        ), patch(
            "sys.argv", ["detect_scope_explosion.py"]
        ):
            # Remove SKIP_SCOPE_CHECK if set
            env = os.environ.copy()
            env.pop("SKIP_SCOPE_CHECK", None)
            with patch.dict(os.environ, env, clear=True):
                exit_code = main()
                assert exit_code == 0

    def test_returns_one_when_blocked(self) -> None:
        blocked_result = ScopeResult(
            file_count=55,
            merge_base="abc123",
            current_branch="feat/big",
            files=tuple(f"file{i}.py" for i in range(55)),
        )
        env = os.environ.copy()
        env.pop("SKIP_SCOPE_CHECK", None)
        with patch.dict(os.environ, env, clear=True), patch(
            "scripts.detect_scope_explosion.detect_scope",
            return_value=blocked_result,
        ), patch("sys.argv", ["detect_scope_explosion.py"]):
            exit_code = main()
            assert exit_code == 1


class TestBypassHintContext:
    """The bypass hint must match the hook stage where it will be used."""

    def _blocked_result(self) -> ScopeResult:
        return ScopeResult(
            file_count=BLOCK_THRESHOLD + 5,
            merge_base="abc123",
            current_branch="feat/test",
            files=tuple(f"file{i}.py" for i in range(BLOCK_THRESHOLD + 5)),
        )

    def test_pre_commit_hint_says_git_commit(self, capsys: CaptureFixture[str]) -> None:
        """Pre-commit invocation (no --base-branch) prints 'git commit' bypass."""
        report(self._blocked_result(), from_prepush=False)
        out = capsys.readouterr().out
        assert "SKIP_SCOPE_CHECK=1 git commit" in out
        assert "git push" not in out

    def test_pre_push_hint_says_git_push(self, capsys: CaptureFixture[str]) -> None:
        """Pre-push invocation (--base-branch set) prints 'git push' bypass."""
        report(self._blocked_result(), from_prepush=True)
        out = capsys.readouterr().out
        assert "SKIP_SCOPE_CHECK=1 git push" in out
        assert "git commit" not in out.split("Bypass")[1]

    def test_main_without_base_branch_arg_is_pre_commit(
        self, capsys: CaptureFixture[str]
    ) -> None:
        """main() with no --base-branch passes from_prepush=False to report."""
        blocked = self._blocked_result()
        env = {k: v for k, v in os.environ.items() if k != "SKIP_SCOPE_CHECK"}
        with patch.dict(os.environ, env, clear=True), patch(
            "scripts.detect_scope_explosion.detect_scope", return_value=blocked
        ), patch("sys.argv", ["detect_scope_explosion.py"]):
            main()
        out = capsys.readouterr().out
        assert "SKIP_SCOPE_CHECK=1 git commit" in out

    def test_main_with_base_branch_arg_is_pre_push(
        self, capsys: CaptureFixture[str]
    ) -> None:
        """main() with --base-branch origin/main passes from_prepush=True to report."""
        blocked = self._blocked_result()
        env = {k: v for k, v in os.environ.items() if k != "SKIP_SCOPE_CHECK"}
        with patch.dict(os.environ, env, clear=True), patch(
            "scripts.detect_scope_explosion.detect_scope", return_value=blocked
        ), patch(
            "sys.argv",
            ["detect_scope_explosion.py", "--base-branch", "origin/main"],
        ):
            main()
        out = capsys.readouterr().out
        assert "SKIP_SCOPE_CHECK=1 git push" in out

    def test_pre_commit_remediation_mentions_stash(
        self, capsys: CaptureFixture[str]
    ) -> None:
        """Pre-commit block message includes stash-based remediation steps."""
        report(self._blocked_result(), from_prepush=False)
        out = capsys.readouterr().out
        assert "git stash" in out

    def test_pre_push_remediation_omits_stash(
        self, capsys: CaptureFixture[str]
    ) -> None:
        """Pre-push block message does not suggest stash; work is already committed."""
        report(self._blocked_result(), from_prepush=True)
        out = capsys.readouterr().out
        assert "git stash" not in out


class TestStripRemotePrefix:
    """Tests for strip_remote_prefix."""

    def test_strips_origin(self) -> None:
        """A remote-qualified ref loses the remote."""
        assert strip_remote_prefix("origin/main") == "main"

    def test_leaves_plain_name(self) -> None:
        """A plain branch name passes through untouched."""
        assert strip_remote_prefix("main") == "main"

    def test_strips_only_the_leading_occurrence(self) -> None:
        """A branch whose name embeds the prefix keeps the inner text."""
        assert strip_remote_prefix("origin/feat/origin/thing") == "feat/origin/thing"

    def test_leaves_other_remotes(self) -> None:
        """Only origin is stripped; another remote is not this script's base."""
        assert strip_remote_prefix("upstream/main") == "upstream/main"


class TestResolvePrBaseBranch:
    """Tests for resolve_pr_base_branch."""

    @staticmethod
    def _gh(stdout: str, returncode: int = 0):
        return subprocess.CompletedProcess(
            args=[], returncode=returncode, stdout=stdout, stderr=""
        )

    def test_returns_base_ref_name(self) -> None:
        """Exactly one open PR yields its base branch name."""
        with (
            patch(
                "scripts.detect_scope_explosion.shutil.which",
                return_value="/usr/bin/gh",
            ),
            patch(
                "scripts.detect_scope_explosion.subprocess.run",
                return_value=self._gh('[{"baseRefName": "fix/base-branch"}]'),
            ),
        ):
            assert resolve_pr_base_branch("feat/stacked") == "fix/base-branch"

    def test_queries_only_open_prs_for_this_branch(self) -> None:
        """gh pr view falls back to a merged PR, so the query must be explicit.

        Verified against gh 2.97.0: on a branch whose PR had already merged,
        `gh pr view` returned that PR with state=MERGED. A reused branch would
        then be rescoped against a dead PR's base.
        """
        with (
            patch(
                "scripts.detect_scope_explosion.shutil.which",
                return_value="/usr/bin/gh",
            ),
            patch(
                "scripts.detect_scope_explosion.subprocess.run",
                return_value=self._gh('[{"baseRefName": "main"}]'),
            ) as run,
        ):
            resolve_pr_base_branch("feat/stacked")
        argv = run.call_args.args[0]
        assert "view" not in argv
        assert argv[:3] == ["gh", "pr", "list"]
        assert "--state" in argv and argv[argv.index("--state") + 1] == "open"
        assert "--head" in argv and argv[argv.index("--head") + 1] == "feat/stacked"

    def test_returns_none_when_no_open_pr_matches(self) -> None:
        """An empty list means no open PR, which is a normal local state."""
        with (
            patch(
                "scripts.detect_scope_explosion.shutil.which",
                return_value="/usr/bin/gh",
            ),
            patch(
                "scripts.detect_scope_explosion.subprocess.run",
                return_value=self._gh("[]"),
            ),
        ):
            assert resolve_pr_base_branch("feat/stacked") is None

    def test_returns_none_when_several_open_prs_match(self) -> None:
        """Picking one of several open PRs would be a guess that removes a block."""
        with (
            patch(
                "scripts.detect_scope_explosion.shutil.which",
                return_value="/usr/bin/gh",
            ),
            patch(
                "scripts.detect_scope_explosion.subprocess.run",
                return_value=self._gh(
                    '[{"baseRefName": "main"}, {"baseRefName": "fix/other"}]'
                ),
            ),
        ):
            assert resolve_pr_base_branch("feat/stacked") is None

    def test_returns_none_on_malformed_json(self) -> None:
        """Unparseable gh output yields None rather than an exception."""
        with (
            patch(
                "scripts.detect_scope_explosion.shutil.which",
                return_value="/usr/bin/gh",
            ),
            patch(
                "scripts.detect_scope_explosion.subprocess.run",
                return_value=self._gh("not json at all"),
            ),
        ):
            assert resolve_pr_base_branch("feat/stacked") is None

    def test_returns_none_on_non_list_payload(self) -> None:
        """A JSON object where a list is expected yields None."""
        with (
            patch(
                "scripts.detect_scope_explosion.shutil.which",
                return_value="/usr/bin/gh",
            ),
            patch(
                "scripts.detect_scope_explosion.subprocess.run",
                return_value=self._gh('{"baseRefName": "main"}'),
            ),
        ):
            assert resolve_pr_base_branch("feat/stacked") is None

    def test_returns_none_when_gh_missing(self) -> None:
        """No gh on PATH is a normal local state, not an error."""
        with patch("scripts.detect_scope_explosion.shutil.which", return_value=None):
            assert resolve_pr_base_branch("feat/stacked") is None

    def test_returns_none_on_nonzero_exit(self) -> None:
        """A gh failure (auth, offline) yields None."""
        with (
            patch(
                "scripts.detect_scope_explosion.shutil.which",
                return_value="/usr/bin/gh",
            ),
            patch(
                "scripts.detect_scope_explosion.subprocess.run",
                return_value=self._gh("", returncode=1),
            ),
        ):
            assert resolve_pr_base_branch("feat/stacked") is None

    def test_returns_none_on_empty_base_name(self) -> None:
        """A match carrying a blank base name yields None, not an empty string."""
        with (
            patch(
                "scripts.detect_scope_explosion.shutil.which",
                return_value="/usr/bin/gh",
            ),
            patch(
                "scripts.detect_scope_explosion.subprocess.run",
                return_value=self._gh('[{"baseRefName": "  "}]'),
            ),
        ):
            assert resolve_pr_base_branch("feat/stacked") is None

    def test_returns_none_on_timeout(self) -> None:
        """A hung network call must not propagate out of a git hook."""
        with (
            patch(
                "scripts.detect_scope_explosion.shutil.which",
                return_value="/usr/bin/gh",
            ),
            patch(
                "scripts.detect_scope_explosion.subprocess.run",
                side_effect=subprocess.TimeoutExpired(cmd="gh", timeout=5),
            ),
        ):
            assert resolve_pr_base_branch("feat/stacked") is None

    def test_returns_none_on_oserror(self) -> None:
        """A gh binary that cannot execute yields None."""
        with (
            patch(
                "scripts.detect_scope_explosion.shutil.which",
                return_value="/usr/bin/gh",
            ),
            patch(
                "scripts.detect_scope_explosion.subprocess.run",
                side_effect=OSError("exec format error"),
            ),
        ):
            assert resolve_pr_base_branch("feat/stacked") is None

    def test_uses_a_bounded_timeout(self) -> None:
        """The gh call is bounded so a hook cannot hang on it."""
        with (
            patch(
                "scripts.detect_scope_explosion.shutil.which",
                return_value="/usr/bin/gh",
            ),
            patch(
                "scripts.detect_scope_explosion.subprocess.run",
                return_value=self._gh('[{"baseRefName": "main"}]'),
            ) as run,
        ):
            resolve_pr_base_branch("feat/stacked")
        assert run.call_args.kwargs["timeout"] == 5


class TestRescopeAgainstPrBase:
    """Tests for rescope_against_pr_base."""

    @staticmethod
    def _result(count: int, branch: str = "feat/stacked") -> ScopeResult:
        return ScopeResult(
            file_count=count,
            merge_base="abc123def456",
            current_branch=branch,
            files=tuple(f"file{i}.py" for i in range(count)),
        )

    @staticmethod
    def _no_merge():
        """Patch the merge check off so a test exercises the normal path."""
        return patch(
            "scripts.detect_scope_explosion.get_merge_head_commit", return_value=None
        )

    @staticmethod
    def _branch(name: str = "feat/stacked"):
        return patch(
            "scripts.detect_scope_explosion.get_current_branch", return_value=name
        )

    def test_rescopes_to_the_pr_base(self) -> None:
        """A stacked PR is re-measured against its real base."""
        blocked = self._result(52)
        narrowed = self._result(13)
        with (
            self._no_merge(),
            self._branch(),
            patch(
                "scripts.detect_scope_explosion.resolve_pr_base_branch",
                return_value="fix/parent",
            ),
            patch("scripts.detect_scope_explosion.detect_scope", return_value=narrowed),
        ):
            assert rescope_against_pr_base(None, blocked) is narrowed

    def test_passes_the_pr_base_to_detect_scope(self) -> None:
        """The re-measurement uses the resolved base, not the original one."""
        with (
            self._no_merge(),
            self._branch(),
            patch(
                "scripts.detect_scope_explosion.resolve_pr_base_branch",
                return_value="fix/parent",
            ),
            patch(
                "scripts.detect_scope_explosion.detect_scope",
                return_value=self._result(13),
            ) as detect,
        ):
            rescope_against_pr_base(None, self._result(52))
        assert detect.call_args.args[0] == "fix/parent"

    def test_looks_up_the_pr_for_the_current_branch(self) -> None:
        """The lookup is scoped to this branch, not inferred by gh."""
        with (
            self._no_merge(),
            self._branch("feat/stacked"),
            patch(
                "scripts.detect_scope_explosion.resolve_pr_base_branch",
                return_value="fix/parent",
            ) as resolve,
            patch(
                "scripts.detect_scope_explosion.detect_scope",
                return_value=self._result(13),
            ),
        ):
            rescope_against_pr_base(None, self._result(52))
        assert resolve.call_args.args[0] == "feat/stacked"

    def test_skips_rescoping_during_a_merge(self) -> None:
        """detect_scope picks its comparison mode from the base it is given.

        `is_ancestor(MERGE_HEAD, base_ref)` decides between the MERGE_HEAD path
        and the merge-base path, so a second call with a different base can
        compare in a different mode than the first. The two numbers are then
        not comparable and the second can undercount. Skip entirely.
        """
        with (
            patch(
                "scripts.detect_scope_explosion.get_merge_head_commit",
                return_value="deadbeefcafe",
            ),
            patch(
                "scripts.detect_scope_explosion.resolve_pr_base_branch"
            ) as resolve,
        ):
            assert rescope_against_pr_base(None, self._result(52)) is None
        resolve.assert_not_called()

    def test_returns_none_on_detached_head(self) -> None:
        """With no branch name there is no PR to look up."""
        with (
            self._no_merge(),
            self._branch(None),
            patch(
                "scripts.detect_scope_explosion.resolve_pr_base_branch"
            ) as resolve,
        ):
            assert rescope_against_pr_base(None, self._result(52)) is None
        resolve.assert_not_called()

    def test_returns_none_when_no_pr_base(self) -> None:
        """With no PR resolved the caller keeps the original measurement."""
        with (
            self._no_merge(),
            self._branch(),
            patch(
                "scripts.detect_scope_explosion.resolve_pr_base_branch",
                return_value=None,
            ),
        ):
            assert rescope_against_pr_base(None, self._result(52)) is None

    def test_returns_none_when_pr_base_is_already_the_measured_base(self) -> None:
        """A PR that already targets main gains nothing from a second pass."""
        with (
            self._no_merge(),
            self._branch(),
            patch(
                "scripts.detect_scope_explosion.resolve_pr_base_branch",
                return_value="main",
            ),
            patch("scripts.detect_scope_explosion.detect_scope") as detect,
        ):
            assert rescope_against_pr_base(None, self._result(52)) is None
        detect.assert_not_called()

    def test_normalizes_the_remote_prefix_before_comparing(self) -> None:
        """Pre-push passes origin/main, which names the same branch as main."""
        with (
            self._no_merge(),
            self._branch(),
            patch(
                "scripts.detect_scope_explosion.resolve_pr_base_branch",
                return_value="main",
            ),
            patch("scripts.detect_scope_explosion.detect_scope") as detect,
        ):
            assert rescope_against_pr_base("origin/main", self._result(52)) is None
        detect.assert_not_called()

    def test_returns_none_when_remeasurement_fails(self) -> None:
        """An unresolvable re-measurement leaves the original result standing."""
        with (
            self._no_merge(),
            self._branch(),
            patch(
                "scripts.detect_scope_explosion.resolve_pr_base_branch",
                return_value="fix/parent",
            ),
            patch("scripts.detect_scope_explosion.detect_scope", return_value=None),
        ):
            assert rescope_against_pr_base(None, self._result(52)) is None

    def test_refuses_a_zero_file_remeasurement(self) -> None:
        """A failed git diff reads as zero files, which would clear the block.

        get_index_files_against_ref returns [] on any nonzero git diff and
        detect_scope turns that into ScopeResult(file_count=0) rather than
        None. A genuinely empty result is indistinguishable from that failure,
        so both are refused.
        """
        with (
            self._no_merge(),
            self._branch(),
            patch(
                "scripts.detect_scope_explosion.resolve_pr_base_branch",
                return_value="fix/parent",
            ),
            patch(
                "scripts.detect_scope_explosion.detect_scope",
                return_value=self._result(0),
            ),
        ):
            assert rescope_against_pr_base(None, self._result(52)) is None

    def test_refuses_a_remeasurement_naming_unseen_files(self) -> None:
        """A file the first pass never saw means the runs compared differently."""
        blocked = self._result(52)
        foreign = ScopeResult(
            file_count=3,
            merge_base="abc123def456",
            current_branch="feat/stacked",
            files=("file0.py", "file1.py", "not-in-the-first-pass.py"),
        )
        with (
            self._no_merge(),
            self._branch(),
            patch(
                "scripts.detect_scope_explosion.resolve_pr_base_branch",
                return_value="fix/parent",
            ),
            patch("scripts.detect_scope_explosion.detect_scope", return_value=foreign),
        ):
            assert rescope_against_pr_base(None, blocked) is None

    def test_accepts_an_exact_subset(self) -> None:
        """A real stacked-base surface is contained in the main-relative one."""
        blocked = self._result(52)
        narrowed = ScopeResult(
            file_count=2,
            merge_base="abc123def456",
            current_branch="feat/stacked",
            files=("file7.py", "file9.py"),
        )
        with (
            self._no_merge(),
            self._branch(),
            patch(
                "scripts.detect_scope_explosion.resolve_pr_base_branch",
                return_value="fix/parent",
            ),
            patch("scripts.detect_scope_explosion.detect_scope", return_value=narrowed),
        ):
            assert rescope_against_pr_base(None, blocked) is narrowed

    def test_reports_both_counts(self, capsys: CaptureFixture[str]) -> None:
        """The message names both measurements so the swap is auditable."""
        with (
            self._no_merge(),
            self._branch(),
            patch(
                "scripts.detect_scope_explosion.resolve_pr_base_branch",
                return_value="fix/parent",
            ),
            patch(
                "scripts.detect_scope_explosion.detect_scope",
                return_value=self._result(13),
            ),
        ):
            rescope_against_pr_base(None, self._result(52))
        err = capsys.readouterr().err
        assert "origin/fix/parent" in err
        assert "13 files" in err
        assert "52" in err


class TestMainConsultsPrBaseOnlyWhenBlocking:
    """Tests for the main() gate around rescope_against_pr_base."""

    @staticmethod
    def _result(count: int) -> ScopeResult:
        return ScopeResult(
            file_count=count,
            merge_base="abc123def456",
            current_branch="feat/stacked",
            files=tuple(f"file{i}.py" for i in range(count)),
        )

    def test_under_the_limit_skips_the_lookup(self) -> None:
        """The common path pays no gh call."""
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("sys.argv", ["detect_scope_explosion.py"]),
            patch(
                "scripts.detect_scope_explosion.detect_scope",
                return_value=self._result(BLOCK_THRESHOLD),
            ),
            patch("scripts.detect_scope_explosion.rescope_against_pr_base") as rescope,
        ):
            assert main() == 0
        rescope.assert_not_called()

    def test_over_the_limit_consults_the_pr_base(self) -> None:
        """A blocking count triggers exactly one re-measurement attempt."""
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("sys.argv", ["detect_scope_explosion.py"]),
            patch(
                "scripts.detect_scope_explosion.detect_scope",
                return_value=self._result(BLOCK_THRESHOLD + 2),
            ),
            patch(
                "scripts.detect_scope_explosion.rescope_against_pr_base",
                return_value=self._result(13),
            ) as rescope,
        ):
            assert main() == 0
        assert rescope.call_count == 1

    def test_still_blocks_a_genuinely_large_pr(self) -> None:
        """Re-measuring does not rescue a PR that is large against its own base."""
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("sys.argv", ["detect_scope_explosion.py"]),
            patch(
                "scripts.detect_scope_explosion.detect_scope",
                return_value=self._result(BLOCK_THRESHOLD + 40),
            ),
            patch(
                "scripts.detect_scope_explosion.rescope_against_pr_base",
                return_value=self._result(BLOCK_THRESHOLD + 30),
            ),
        ):
            assert main() == 1

    def test_blocks_when_no_pr_base_resolves(self) -> None:
        """Unchanged behavior when gh cannot answer: the main count stands."""
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("sys.argv", ["detect_scope_explosion.py"]),
            patch(
                "scripts.detect_scope_explosion.detect_scope",
                return_value=self._result(BLOCK_THRESHOLD + 2),
            ),
            patch(
                "scripts.detect_scope_explosion.rescope_against_pr_base",
                return_value=None,
            ),
        ):
            assert main() == 1
