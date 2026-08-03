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
    resolve_base_ref,
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



class TestReportBypassHint:
    """Tests that the bypass hint names the verb that can actually bypass.

    Issue #4334: at pre-push the gate blocks the push, so `git commit` cannot
    bypass it. Only `git push` can. `report()` takes `is_push` to branch the
    hint and the remediation steps.
    """

    @staticmethod
    def _blocked() -> ScopeResult:
        return ScopeResult(
            file_count=BLOCK_THRESHOLD + 5,
            merge_base="abc123",
            current_branch="feat/big",
            files=tuple(f"file{i}.py" for i in range(BLOCK_THRESHOLD + 5)),
        )

    def test_block_hint_names_push_when_is_push(
        self, capsys: CaptureFixture[str]
    ) -> None:
        assert report(self._blocked(), is_push=True) == 1
        assert "SKIP_SCOPE_CHECK=1 git push" in capsys.readouterr().out

    def test_block_hint_names_commit_when_not_is_push(
        self, capsys: CaptureFixture[str]
    ) -> None:
        assert report(self._blocked(), is_push=False) == 1
        assert "SKIP_SCOPE_CHECK=1 git commit" in capsys.readouterr().out

    def test_push_hint_does_not_also_name_commit(
        self, capsys: CaptureFixture[str]
    ) -> None:
        # Negative case from issue #4334: the hint must not name both verbs.
        # A hint listing both is as useless as naming the wrong one.
        report(self._blocked(), is_push=True)
        assert "git commit" not in capsys.readouterr().out

    def test_commit_hint_does_not_also_name_push(
        self, capsys: CaptureFixture[str]
    ) -> None:
        report(self._blocked(), is_push=False)
        assert "git push" not in capsys.readouterr().out

    def test_push_remediation_omits_stash_step(
        self, capsys: CaptureFixture[str]
    ) -> None:
        # `git stash` saves uncommitted work. At push time the work is already
        # committed, so the step is noise.
        report(self._blocked(), is_push=True)
        assert "git stash" not in capsys.readouterr().out

    def test_commit_remediation_keeps_stash_step(
        self, capsys: CaptureFixture[str]
    ) -> None:
        report(self._blocked(), is_push=False)
        assert "git stash" in capsys.readouterr().out

    def test_strong_warn_remediation_branches_on_is_push(
        self, capsys: CaptureFixture[str]
    ) -> None:
        # The warn band prints remediation too, and it must branch the same way.
        warned = ScopeResult(
            file_count=STRONG_WARN_THRESHOLD,
            merge_base="abc123",
            current_branch="feat/mid",
            files=tuple(f"file{i}.py" for i in range(STRONG_WARN_THRESHOLD)),
        )
        assert report(warned, is_push=True) == 0
        assert "Commit current work" not in capsys.readouterr().out

    def test_default_is_push_is_false(self, capsys: CaptureFixture[str]) -> None:
        # Callers that predate the flag must keep the commit-context hint.
        report(self._blocked())
        assert "SKIP_SCOPE_CHECK=1 git commit" in capsys.readouterr().out


class TestMainBypassHintRouting:
    """Tests that `main()` derives push context from `--base-branch` presence.

    Only the pre-push hook passes `--base-branch` (lefthook.yml), so its
    presence is the push-context sentinel.
    """

    @staticmethod
    def _blocked() -> ScopeResult:
        return ScopeResult(
            file_count=BLOCK_THRESHOLD + 5,
            merge_base="abc123",
            current_branch="feat/big",
            files=tuple(f"file{i}.py" for i in range(BLOCK_THRESHOLD + 5)),
        )

    def _run(self, argv: list[str]) -> tuple[int, str]:
        env = os.environ.copy()
        env.pop("SKIP_SCOPE_CHECK", None)
        with patch.dict(os.environ, env, clear=True), patch(
            "scripts.detect_scope_explosion.detect_scope",
            return_value=self._blocked(),
        ) as spy, patch("sys.argv", ["detect_scope_explosion.py", *argv]):
            code = main()
        self.last_base_ref = spy.call_args[0][0]
        return code, ""

    def test_base_branch_flag_routes_as_push(
        self, capsys: CaptureFixture[str]
    ) -> None:
        code, _ = self._run(["--base-branch", "main"])
        assert code == 1
        assert "SKIP_SCOPE_CHECK=1 git push" in capsys.readouterr().out

    def test_no_base_branch_flag_routes_as_commit(
        self, capsys: CaptureFixture[str]
    ) -> None:
        code, _ = self._run([])
        assert code == 1
        assert "SKIP_SCOPE_CHECK=1 git commit" in capsys.readouterr().out

    def test_base_branch_value_reaches_detect_scope(
        self, capsys: CaptureFixture[str]
    ) -> None:
        # Discriminating control. A routing fix that reads only the flag's
        # presence and always compares against "main" would pass every other
        # test in this class. This one pins that the value is still honored.
        self._run(["--base-branch", "develop"])
        capsys.readouterr()
        assert self.last_base_ref == "develop"

    def test_absent_base_branch_still_defaults_to_main(
        self, capsys: CaptureFixture[str]
    ) -> None:
        # The argparse default moved from "main" to None, so the "main"
        # fallback now lives in main(). Pin it, or the default silently
        # becomes None and detect_scope compares against nothing.
        self._run([])
        capsys.readouterr()
        assert self.last_base_ref == "main"
