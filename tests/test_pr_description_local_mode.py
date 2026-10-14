"""Tests for the local --body-file mode of scripts.validation.pr_description (issue #6405).

The local mode compares a body file to the diff of ``BASE...HEAD`` with no
network call, so an agent finds a "File mentioned but not in diff" failure
before the PR opens.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.validation.pr_description import (
    DEFAULT_LOCAL_BASE,
    get_local_diff_files,
    main,
    run_local,
)

PHANTOM_BODY = "## Changes\n\n- Updated `scripts/build_all.py` and `src/changed.py`\n"
CLEAN_BODY = "## Changes\n\n- Updated `src/changed.py`\n"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.test", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A throwaway repo on branch ``feature`` with one file changed vs ``main``."""
    for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
        monkeypatch.delenv(name, raising=False)
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    _git(root, "init", "-q", "-b", "main")
    (root / "src" / "base.py").write_text("x = 1\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    _git(root, "checkout", "-q", "-b", "feature")
    (root / "src" / "changed.py").write_text("y = 2\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "change")
    monkeypatch.chdir(root)
    return root


def _body(tmp_path: Path, text: str) -> str:
    path = tmp_path / "body.md"
    path.write_text(text, encoding="utf-8")
    return str(path)


class TestGetLocalDiffFiles:
    def test_lists_files_changed_since_base(self, repo: Path) -> None:
        assert get_local_diff_files("main") == ["src/changed.py"]

    def test_empty_when_head_equals_base(self, repo: Path) -> None:
        _git(repo, "checkout", "-q", "main")
        assert get_local_diff_files("main") == []

    def test_unknown_ref_raises(self, repo: Path) -> None:
        with pytest.raises(RuntimeError, match="Could not diff"):
            get_local_diff_files("no-such-ref")

    @pytest.mark.parametrize("ref", ["", "--output=/tmp/x", "-p"])
    def test_option_like_or_empty_ref_rejected_without_running_git(self, ref: str) -> None:
        with patch("scripts.validation.pr_description.subprocess.run") as mock_run:
            with pytest.raises(RuntimeError, match="Invalid base ref"):
                get_local_diff_files(ref)
        mock_run.assert_not_called()

    def test_timeout_raises(self) -> None:
        with patch(
            "scripts.validation.pr_description.subprocess.run",
            side_effect=subprocess.TimeoutExpired("git", 60),
        ):
            with pytest.raises(RuntimeError, match="Could not run git diff"):
                get_local_diff_files("main")

    def test_missing_git_raises(self) -> None:
        with patch(
            "scripts.validation.pr_description.subprocess.run",
            side_effect=FileNotFoundError("git"),
        ):
            with pytest.raises(RuntimeError, match="Could not run git diff"):
                get_local_diff_files("main")

    def test_failure_without_stderr_uses_default_detail(self) -> None:
        failed = MagicMock(returncode=128, stdout="", stderr="")
        with patch("scripts.validation.pr_description.subprocess.run", return_value=failed):
            with pytest.raises(RuntimeError, match="git diff failed"):
                get_local_diff_files("main")


class TestLocalMode:
    def test_body_naming_out_of_diff_file_fails(
        self, repo: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = main(["--body-file", _body(tmp_path, PHANTOM_BODY), "--base", "main"])
        out = capsys.readouterr().out
        assert code == 1
        assert "File mentioned but not in diff" in out
        assert "scripts/build_all.py" in out

    def test_same_body_without_the_path_passes(self, repo: Path, tmp_path: Path) -> None:
        assert main(["--body-file", _body(tmp_path, CLEAN_BODY), "--base", "main"]) == 0

    def test_fails_without_ci_flag(self, repo: Path, tmp_path: Path) -> None:
        """Local mode always exits 1 on CRITICAL; it does not need --ci."""
        assert main(["--body-file", _body(tmp_path, PHANTOM_BODY), "--base", "main"]) == 1

    def test_makes_no_network_or_gh_call(self, repo: Path, tmp_path: Path) -> None:
        with (
            patch("scripts.validation.pr_description.fetch_pr_data") as mock_fetch,
            patch("scripts.validation.pr_description.get_repo_info") as mock_repo,
        ):
            main(["--body-file", _body(tmp_path, CLEAN_BODY), "--base", "main"])
        mock_fetch.assert_not_called()
        mock_repo.assert_not_called()

    def test_warns_on_unmentioned_significant_file_but_exits_zero(
        self, repo: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        (repo / "scripts").mkdir()
        (repo / "scripts" / "extra.py").write_text("z = 3\n", encoding="utf-8")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", "more")
        code = main(["--body-file", _body(tmp_path, CLEAN_BODY), "--base", "main"])
        assert code == 0
        assert "Significant file not mentioned" in capsys.readouterr().out

    def test_default_base_is_origin_main(self, tmp_path: Path) -> None:
        with patch(
            "scripts.validation.pr_description.get_local_diff_files", return_value=[]
        ) as mock_diff:
            main(["--body-file", _body(tmp_path, "")])
        mock_diff.assert_called_once_with(DEFAULT_LOCAL_BASE)
        assert DEFAULT_LOCAL_BASE == "origin/main"

    def test_empty_diff_with_mentions_fails(self, repo: Path, tmp_path: Path) -> None:
        _git(repo, "checkout", "-q", "main")
        assert main(["--body-file", _body(tmp_path, CLEAN_BODY), "--base", "main"]) == 1

    def test_unreadable_body_file_returns_two(
        self, repo: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = main(["--body-file", str(tmp_path / "missing.md"), "--base", "main"])
        assert code == 2
        assert "could not read body file" in capsys.readouterr().err

    def test_non_utf8_body_file_returns_two(self, repo: Path, tmp_path: Path) -> None:
        bad = tmp_path / "bad.md"
        bad.write_bytes(b"\xff\xfe\x00bad")
        assert main(["--body-file", str(bad), "--base", "main"]) == 2

    def test_unknown_base_returns_two(
        self, repo: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = main(["--body-file", _body(tmp_path, CLEAN_BODY), "--base", "nope"])
        assert code == 2
        assert "Could not diff" in capsys.readouterr().err

    def test_run_local_direct_call(self, repo: Path, tmp_path: Path) -> None:
        assert run_local(_body(tmp_path, CLEAN_BODY), "main") == 0
        assert run_local(_body(tmp_path, PHANTOM_BODY), "main") == 1


class TestArgumentRules:
    def test_pr_number_and_body_file_are_mutually_exclusive(self, tmp_path: Path) -> None:
        with pytest.raises(SystemExit) as exc:
            main(["--pr-number", "1", "--body-file", _body(tmp_path, "")])
        assert exc.value.code == 2

    def test_base_without_body_file_is_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("PR_NUMBER", raising=False)
        with pytest.raises(SystemExit) as exc:
            main(["--pr-number", "1", "--base", "origin/main"])
        assert exc.value.code == 2

    def test_neither_source_is_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("PR_NUMBER", raising=False)
        with pytest.raises(SystemExit) as exc:
            main([])
        assert exc.value.code == 2

    def test_pr_number_env_still_selects_pr_mode(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PR_NUMBER", "7")
        monkeypatch.setenv("REPO_OWNER", "o")
        monkeypatch.setenv("REPO_NAME", "r")
        with patch("scripts.validation.pr_description.fetch_pr_data") as mock_fetch:
            mock_fetch.return_value = {"title": "T", "body": "", "files": []}
            assert main([]) == 0
        mock_fetch.assert_called_once_with(7, "o", "r")

    def test_env_pr_number_does_not_block_local_mode(
        self, repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("PR_NUMBER", "7")
        with patch("scripts.validation.pr_description.fetch_pr_data") as mock_fetch:
            code = main(["--body-file", _body(tmp_path, CLEAN_BODY), "--base", "main"])
        assert code == 0
        mock_fetch.assert_not_called()

    def test_pr_number_mode_unchanged(self) -> None:
        with (
            patch("scripts.validation.pr_description.fetch_pr_data") as mock_fetch,
            patch("scripts.validation.pr_description.get_repo_info") as mock_repo,
        ):
            from scripts.github_core.api import RepoInfo

            mock_repo.return_value = RepoInfo(owner="o", repo="r")
            mock_fetch.return_value = {
                "title": "T",
                "body": "## Changes\nChanged `ghost.py`",
                "files": [{"path": "foo.py"}],
            }
            assert main(["--pr-number", "1", "--ci"]) == 1
            assert main(["--pr-number", "1"]) == 0
