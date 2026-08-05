"""Tests for new_validated_pr.py PR creation wrapper."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts.github_core.repo import get_repo_root
from scripts.new_validated_pr import (
    SKILL_RELPATH,
    _build_parser,
    _build_skill_args,
    _run_web_mode,
    main,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _fake_repo_with_skill(root: Path) -> Path:
    """Create a repo-shaped tree containing the dispatch target."""
    skill = root / SKILL_RELPATH
    skill.parent.mkdir(parents=True, exist_ok=True)
    skill.write_text("")
    return skill


class TestGetRepoRoot:
    @patch("scripts.github_core.repo.subprocess.run")
    def test_returns_path_on_success(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="/fake/repo\n")
        result = get_repo_root()
        assert result == Path("/fake/repo")

    @patch("scripts.github_core.repo.subprocess.run")
    def test_returns_none_on_failure(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=128, stdout="")
        assert get_repo_root() is None


class TestDispatchTargetExists:
    """Reads the real tree instead of a mocked repo root.

    Every other test in this file points the repo root at an empty tmp_path, so
    the dispatch target is missing by construction and exit 2 is the expected
    result. That shape stayed green for the whole time the wrapper pointed at
    New-PR.ps1, which PR #1144 deleted during the PowerShell to Python
    migration. Mocking the filesystem cannot detect a dispatch target that
    stopped existing, so this test does not mock it.
    """

    def test_dispatch_target_exists_in_this_repo(self) -> None:
        target = REPO_ROOT / SKILL_RELPATH
        assert target.is_file(), f"wrapper dispatches to a missing script: {target}"

    def test_dispatch_target_is_the_expected_script(self) -> None:
        """Pin the identity, not just the existence.

        Existence alone is a weak guard: repointing SKILL_RELPATH at any other
        real script in the same directory, say close_pr.py, keeps the existence
        assertion green while the wrapper silently dispatches to the wrong
        command. Restating the literal here is the point rather than a
        duplication smell, because the pair catches both failures: this test
        fails on a wrong target, and the existence test fails on a deleted one.
        """
        assert SKILL_RELPATH == Path(".claude/skills/github/scripts/pr/new_pr.py")

    def test_dispatch_target_is_not_powershell(self) -> None:
        assert SKILL_RELPATH.suffix == ".py", "ADR-042: new scripts are Python"


class TestWebMode:
    """Covers the `--web` branch, which dispatches to gh rather than to a script.

    This path was extracted into _run_web_mode during the complexity refactor
    and had no coverage at the time, so nothing would have caught a mistake in
    the extraction.
    """

    @patch.dict(os.environ, {"CI": "true", "DISPLAY": ":0"}, clear=True)
    def test_refuses_in_ci(self) -> None:
        assert _run_web_mode("main") == 2

    @patch.dict(os.environ, {"GITHUB_ACTIONS": "true", "DISPLAY": ":0"}, clear=True)
    def test_refuses_under_github_actions(self) -> None:
        assert _run_web_mode("main") == 2

    @patch.dict(os.environ, {}, clear=True)
    def test_refuses_when_headless(self) -> None:
        assert _run_web_mode("main") == 2

    @patch("scripts.new_validated_pr.subprocess.run")
    @patch.dict(os.environ, {"DISPLAY": ":0"}, clear=True)
    def test_invokes_gh_with_base(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0)
        assert _run_web_mode("develop") == 0
        assert mock_run.call_args[0][0] == [
            "gh", "pr", "create", "--web", "--base", "develop",
        ]

    @patch("scripts.new_validated_pr.subprocess.run")
    @patch.dict(os.environ, {"DISPLAY": ":0"}, clear=True)
    def test_omits_base_when_empty(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0)
        _run_web_mode("")
        assert mock_run.call_args[0][0] == ["gh", "pr", "create", "--web"]

    @patch("scripts.new_validated_pr.subprocess.run")
    @patch.dict(os.environ, {"DISPLAY": ":0"}, clear=True)
    def test_propagates_gh_exit_code(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=7)
        assert _run_web_mode("main") == 7

    @patch("scripts.new_validated_pr.subprocess.run")
    @patch("scripts.new_validated_pr.shutil.which", return_value="/usr/bin/gh")
    @patch("scripts.new_validated_pr.get_repo_root", return_value=Path("/fake"))
    @patch.dict(os.environ, {"DISPLAY": ":0"}, clear=True)
    def test_main_routes_web_without_requiring_a_title(
        self, _repo: MagicMock, _which: MagicMock, mock_run: MagicMock,
    ) -> None:
        mock_run.return_value = MagicMock(returncode=0)
        assert main(["--web"]) == 0
        assert mock_run.call_args[0][0][:4] == ["gh", "pr", "create", "--web"]


class TestMain:
    @patch("scripts.new_validated_pr.get_repo_root", return_value=None)
    def test_exits_2_when_not_git_repo(self, _mock: MagicMock) -> None:
        assert main(["--title", "test"]) == 2

    @patch("scripts.new_validated_pr.shutil.which", return_value=None)
    @patch("scripts.new_validated_pr.get_repo_root", return_value=Path("/repo"))
    def test_exits_2_when_gh_not_found(self, _repo: MagicMock, _which: MagicMock) -> None:
        assert main(["--title", "test"]) == 2

    @patch("scripts.new_validated_pr.shutil.which", return_value="/usr/bin/gh")
    @patch("scripts.new_validated_pr.get_repo_root", return_value=Path("/repo"))
    def test_exits_2_when_no_title(self, _repo: MagicMock, _which: MagicMock) -> None:
        assert main([]) == 2

    @patch("scripts.new_validated_pr.subprocess.run")
    @patch("scripts.new_validated_pr.shutil.which", return_value="/usr/bin/gh")
    @patch("scripts.new_validated_pr.get_repo_root")
    def test_exits_2_when_skill_not_found(
        self, mock_root: MagicMock, _which: MagicMock, _run: MagicMock, tmp_path: Path
    ) -> None:
        mock_root.return_value = tmp_path
        assert main(["--title", "test: title"]) == 2


@patch("scripts.new_validated_pr.shutil.which", return_value="/usr/bin/gh")
@patch("scripts.new_validated_pr.get_repo_root")
class TestDispatch:
    """Success path. None of this was covered before."""

    @staticmethod
    def _run(
        mock_root: MagicMock, tmp_path: Path, argv: list[str], returncode: int = 0
    ) -> tuple[int, list[str]]:
        skill = _fake_repo_with_skill(tmp_path)
        mock_root.return_value = tmp_path
        with patch("scripts.new_validated_pr.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=returncode)
            exit_code = main(argv)
            assert mock_run.call_args is not None
            command = list(mock_run.call_args[0][0])
        assert command[1] == str(skill)
        return exit_code, command

    def test_invokes_the_python_skill_with_the_current_interpreter(
        self, mock_root: MagicMock, _which: MagicMock, tmp_path: Path
    ) -> None:
        exit_code, command = self._run(mock_root, tmp_path, ["--title", "fix: t"])
        assert exit_code == 0
        assert command[0] == sys.executable

    def test_does_not_invoke_powershell(
        self, mock_root: MagicMock, _which: MagicMock, tmp_path: Path
    ) -> None:
        _, command = self._run(mock_root, tmp_path, ["--title", "fix: t"])
        assert "pwsh" not in command
        assert not any(arg.endswith(".ps1") for arg in command)

    def test_passes_title_and_default_base(
        self, mock_root: MagicMock, _which: MagicMock, tmp_path: Path
    ) -> None:
        _, command = self._run(mock_root, tmp_path, ["--title", "fix: t"])
        assert command[command.index("--title") + 1] == "fix: t"
        assert command[command.index("--base") + 1] == "main"

    def test_omits_optional_flags_when_unset(
        self, mock_root: MagicMock, _which: MagicMock, tmp_path: Path
    ) -> None:
        _, command = self._run(mock_root, tmp_path, ["--title", "fix: t"])
        for flag in ("--head", "--body", "--body-file", "--draft", "--skip-validation"):
            assert flag not in command

    def test_forwards_every_optional_flag(
        self, mock_root: MagicMock, _which: MagicMock, tmp_path: Path
    ) -> None:
        _, command = self._run(
            mock_root,
            tmp_path,
            [
                "--title", "fix: t", "--base", "release", "--head", "topic",
                "--body", "text", "--body-file", "b.md", "--draft",
                "--skip-validation", "--audit-reason", "hotfix",
            ],
        )
        assert command[command.index("--base") + 1] == "release"
        assert command[command.index("--head") + 1] == "topic"
        assert command[command.index("--body") + 1] == "text"
        assert command[command.index("--body-file") + 1] == "b.md"
        assert command[command.index("--audit-reason") + 1] == "hotfix"
        assert "--draft" in command
        assert "--skip-validation" in command

    def test_audit_reason_is_dropped_without_skip_validation(
        self, mock_root: MagicMock, _which: MagicMock, tmp_path: Path
    ) -> None:
        _, command = self._run(
            mock_root, tmp_path, ["--title", "fix: t", "--audit-reason", "hotfix"]
        )
        assert "--audit-reason" not in command

    def test_propagates_a_nonzero_exit_code(
        self, mock_root: MagicMock, _which: MagicMock, tmp_path: Path
    ) -> None:
        exit_code, _ = self._run(mock_root, tmp_path, ["--title", "fix: t"], returncode=1)
        assert exit_code == 1


class TestFlagContractWithRealTarget:
    """Every flag this wrapper emits must be one the real target accepts.

    TestDispatchTargetExists pins *which* script runs. This pins that the
    command line handed to that script actually parses. The two failures are
    independent: the target can exist, be the right file, and still reject the
    arguments, which is exactly what happens the moment new_pr.py renames a
    flag.

    Nothing else in this file can catch that. Every dispatch test mocks
    subprocess.run, so the argument list is asserted against string literals in
    this file and never reaches a real parser. A rename in new_pr.py would leave
    all of them green and fail only at runtime, which is the same class of
    silent cross-script drift that let the wrapper dispatch to a deleted
    New-PR.ps1 for months.
    """

    @staticmethod
    def _target_accepted_flags(cwd: Path) -> frozenset[str]:
        """Return the options the real target accepts, read from its own --help.

        Deliberately a subprocess. Importing new_pr.py in this process would run
        its top level, which inserts its own directory onto sys.path and imports
        `validate_pr_description` under that bare name. Two different modules
        carry that name, `.claude/skills/github/scripts/pr/` and
        `src/copilot-cli/skills/github/scripts/pr/`, so the import would pin one
        of them in sys.modules for the rest of the session and hand any later
        importer the wrong tree's copy. Restoring sys.path does not undo that.
        In a repo whose premise is those two trees staying in sync, a leak that
        silently substitutes one for the other is worse than the drift this
        class exists to catch.

        Reading --help rather than calling build_parser() also pins the parser
        the script actually runs. A build_parser() left behind as dead code
        after main() starts building its own would still answer an in-process
        call, and the contract would break at runtime with the suite green.

        argparse answers --help and exits before the script does any work, so
        this cannot reach `gh pr create` or touch the repository.
        """
        target = REPO_ROOT / SKILL_RELPATH
        result = subprocess.run(
            [sys.executable, str(target), "--help"],
            capture_output=True,
            text=True,
            check=False,
            cwd=cwd,
        )
        assert result.returncode == 0, (
            f"{SKILL_RELPATH} could not answer --help "
            f"(exit {result.returncode}): {result.stderr}"
        )
        return frozenset(re.findall(r"--[a-z][a-z0-9-]*", result.stdout))

    @staticmethod
    def _emitted_flags(argv: list[str]) -> list[str]:
        """Return the args the wrapper would hand the target, without argv[0:2]."""
        args = _build_parser().parse_args(argv)
        return _build_skill_args(Path("unused.py"), args)[2:]

    def test_help_extraction_finds_the_targets_flags(self, tmp_path: Path) -> None:
        """Guards the check itself.

        The two contract tests below compare against whatever this extraction
        returns. If --help stopped listing options, or the pattern stopped
        matching, they would report every emitted flag as unknown rather than
        passing on an empty set, so the failure is loud either way. This test
        exists to say which of the two broke.
        """
        accepted = self._target_accepted_flags(tmp_path)
        assert "--help" in accepted
        assert "--title" in accepted

    def test_target_accepts_the_maximal_flag_set(self, tmp_path: Path) -> None:
        emitted = self._emitted_flags(
            [
                "--title", "fix: t", "--base", "release", "--head", "topic",
                "--body", "text", "--body-file", "b.md", "--draft",
                "--skip-validation", "--audit-reason", "hotfix",
            ],
        )
        self._assert_all_accepted(emitted, self._target_accepted_flags(tmp_path))

    def test_target_accepts_the_minimal_flag_set(self, tmp_path: Path) -> None:
        emitted = self._emitted_flags(["--title", "fix: t"])
        self._assert_all_accepted(emitted, self._target_accepted_flags(tmp_path))

    @staticmethod
    def _assert_all_accepted(emitted: list[str], accepted: frozenset[str]) -> None:
        """Compare by set membership, never by substring.

        `--body` is a substring of `--body-file`. A containment check against
        the raw help text would keep passing after `--body` was removed, which
        is the same silent pass this class exists to prevent.
        """
        unknown = [a for a in emitted if a.startswith("--") and a not in accepted]
        assert not unknown, (
            f"wrapper emits {unknown}, which {SKILL_RELPATH} does not accept; "
            f"it accepts {sorted(accepted)}"
        )

