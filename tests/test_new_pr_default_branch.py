"""Default-branch detection tests for new_pr.py."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

from tests.new_pr_harness import (
    build_parser,
    completed,
    main,
    new_pr,
    subprocess_dispatcher,
)


def _git_run(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.stdout.strip()


def _git_repo(tmp_path: Path) -> Path:
    _git_run(tmp_path, "init", "-q")
    _git_run(tmp_path, "config", "user.email", "test@example.com")
    _git_run(tmp_path, "config", "user.name", "Test")
    (tmp_path / "seed.txt").write_text("seed\n", encoding="utf-8")
    _git_run(tmp_path, "add", "seed.txt")
    _git_run(tmp_path, "commit", "-qm", "seed")
    return tmp_path


class TestDetectDefaultBranch:
    def test_parser_uses_detection_when_base_is_omitted(self):
        args = build_parser().parse_args(["--title", "fix: test"])

        assert args.base == ""

    def test_returns_main_outside_a_git_repository(self, tmp_path):
        with patch("subprocess.run") as mock_run:
            assert new_pr._detect_default_branch(str(tmp_path)) == "main"

        mock_run.assert_not_called()

    def test_preserves_ambiguous_origin_head_branch_name(self, tmp_path):
        repo = _git_repo(tmp_path)
        _git_run(repo, "update-ref", "refs/remotes/origin/release/v2", "HEAD")
        _git_run(repo, "update-ref", "refs/heads/origin/release/v2", "HEAD")
        _git_run(
            repo,
            "symbolic-ref",
            "refs/remotes/origin/HEAD",
            "refs/remotes/origin/release/v2",
        )

        assert new_pr._detect_default_branch(str(repo)) == "release/v2"

    def test_returns_valid_origin_head_branch(self, tmp_path):
        (tmp_path / ".git").mkdir()

        def fake_run(argv, **_kwargs):
            if argv[:2] == ["git", "symbolic-ref"]:
                return completed(stdout="refs/remotes/origin/master\n")
            if argv[-1] == "refs/remotes/origin/master":
                return completed()
            return completed(rc=1)

        with patch("subprocess.run", side_effect=fake_run):
            assert new_pr._detect_default_branch(str(tmp_path)) == "master"

    def test_skips_dangling_origin_head_for_remote_fallback(self, tmp_path):
        (tmp_path / ".git").mkdir()

        def fake_run(argv, **_kwargs):
            if argv[:2] == ["git", "symbolic-ref"]:
                return completed(stdout="refs/remotes/origin/main\n")
            if argv[-1] == "refs/remotes/origin/master":
                return completed()
            return completed(rc=1)

        with patch("subprocess.run", side_effect=fake_run):
            assert new_pr._detect_default_branch(str(tmp_path)) == "master"

    def test_prefers_remote_candidates_before_local_candidates(self, tmp_path):
        (tmp_path / ".git").mkdir()

        def fake_run(argv, **_kwargs):
            if argv[:2] == ["git", "symbolic-ref"]:
                return completed(rc=1)
            if argv[-1] == "refs/remotes/origin/master":
                return completed()
            if argv[-1] == "refs/heads/main":
                return completed()
            return completed(rc=1)

        with patch("subprocess.run", side_effect=fake_run):
            assert new_pr._detect_default_branch(str(tmp_path)) == "master"

    def test_falls_back_to_known_local_candidate(self, tmp_path):
        (tmp_path / ".git").mkdir()

        def fake_run(argv, **_kwargs):
            if argv[:2] == ["git", "symbolic-ref"]:
                return completed(rc=1)
            if argv[-1] == "refs/heads/dev":
                return completed()
            return completed(rc=1)

        with patch("subprocess.run", side_effect=fake_run):
            assert new_pr._detect_default_branch(str(tmp_path)) == "dev"

    def test_returns_main_when_no_candidate_exists(self, tmp_path):
        (tmp_path / ".git").mkdir()

        with patch("subprocess.run", return_value=completed(rc=1)):
            assert new_pr._detect_default_branch(str(tmp_path)) == "main"


class TestMainDefaultBranch:
    def test_omitted_base_uses_detected_branch_for_validation_and_creation(self, tmp_path):
        created: list[list[str]] = []

        def create_pr(argv: list[str]) -> bool:
            return argv[:3] == ["gh", "pr", "create"]

        def resolve_origin_master(argv: list[str]) -> bool:
            return argv == ["git", "rev-parse", "--verify", "origin/master"]

        def gh_version(argv: list[str]) -> bool:
            return argv == ["gh", "--version"]

        dispatcher = subprocess_dispatcher(
            [
                (gh_version, completed()),
                (resolve_origin_master, completed()),
                (create_pr, completed()),
            ]
        )

        def fake_run(argv, **kwargs):
            if create_pr(argv):
                created.append(list(argv))
            return dispatcher(argv, **kwargs)

        with (
            patch("subprocess.run", side_effect=fake_run),
            patch.object(new_pr, "get_repo_root", return_value=str(tmp_path)),
            patch.object(new_pr, "_detect_default_branch", return_value="master") as detect,
            patch.object(new_pr, "run_validations") as validate,
        ):
            assert main(["--title", "fix: test", "--head", "feature/test"]) == 0

        detect.assert_called_once_with(str(tmp_path))
        assert validate.call_args.args[1] == "origin/master"
        assert created[0][created[0].index("--base") + 1] == "master"

    def test_explicit_base_bypasses_detection(self, tmp_path):
        def create_pr(argv: list[str]) -> bool:
            return argv[:3] == ["gh", "pr", "create"]

        dispatcher = subprocess_dispatcher(
            [
                (lambda argv: argv == ["gh", "--version"], completed()),
                (
                    lambda argv: argv
                    == ["git", "rev-parse", "--verify", "origin/main"],
                    completed(),
                ),
                (create_pr, completed()),
            ]
        )

        with (
            patch("subprocess.run", side_effect=dispatcher),
            patch.object(new_pr, "get_repo_root", return_value=str(tmp_path)),
            patch.object(new_pr, "_detect_default_branch") as detect,
            patch.object(new_pr, "run_validations") as validate,
        ):
            assert (
                main([
                    "--title",
                    "fix: test",
                    "--head",
                    "feature/test",
                    "--base",
                    "main",
                ])
                == 0
            )

        detect.assert_not_called()
        assert validate.call_args.args[1] == "origin/main"
