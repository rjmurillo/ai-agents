"""Tests for new_validated_pr.py PR creation wrapper."""

from __future__ import annotations

import json
import os
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

# Runs the dispatch target far enough to reach its parser, captures the flags
# argparse itself agreed to accept, and exits before the target does any work.
#
# Asking argparse rather than reading --help text is the whole point. Help
# output interleaves option declarations with prose, so any pattern over it
# counts a flag named inside a description ("replaces the deprecated
# --body-file") as accepted, and the contract test passes after that flag is
# gone. `_actions[].option_strings` is argparse's own registry of what parses.
#
# Intercepting parse_args rather than importing build_parser() pins the parser
# main() actually runs. A build_parser() left behind as dead code after main()
# started building its own would still answer a direct call, and the contract
# would break at runtime with the suite green.
#
# A subprocess rather than an in-process import: new_pr.py's top level inserts
# its own directory onto sys.path and imports `validate_pr_description` under
# that bare name. Two modules carry that name, one under .claude/ and one under
# src/copilot-cli/, so an in-process import pins one in sys.modules for the
# rest of the session and hands any later importer the wrong tree's copy.
# Restoring sys.path does not undo that. In a repo whose premise is those trees
# staying in sync, a leak that substitutes one for the other is worse than the
# drift this test exists to catch.
_PARSER_PROBE = r"""
import argparse, json, os, runpy, subprocess, sys

target = os.path.realpath(sys.argv[1])
_real_parse_args = argparse.ArgumentParser.parse_args


def _capture(self, args=None, namespace=None):
    # Only the target's own parser counts. Patching parse_args globally would
    # otherwise capture a parser built by an imported dependency and report its
    # flags as the target's. Nothing in the current import chain parses at
    # import time, but a future one might, and it would fail silently.
    caller = sys._getframe(1).f_globals.get("__file__", "")
    if not caller or os.path.realpath(caller) != target:
        return _real_parse_args(self, args, namespace)
    flags = sorted({s for action in self._actions for s in action.option_strings})
    sys.stdout.write("FLAGS_JSON:" + json.dumps(flags) + "\n")
    raise SystemExit(0)


def _blocked(*args, **kwargs):
    raise SystemExit(f"probe blocked a subprocess call before parse_args: {args[:1]!r}")


# main() parses before it does anything else, so the capture above fires first.
# If that ever stops being true, fail loudly here instead of running `gh pr
# create` from a test.
subprocess.run = _blocked
subprocess.Popen = _blocked
subprocess.check_output = _blocked
subprocess.check_call = _blocked
argparse.ArgumentParser.parse_args = _capture

sys.argv = [target]
runpy.run_path(target, run_name="__main__")
raise SystemExit("target finished without calling parse_args")
"""
_FLAGS_SENTINEL = "FLAGS_JSON:"


def _fake_repo_with_skill(root: Path) -> Path:
    """Create a repo-shaped tree containing the dispatch target."""
    skill = root / SKILL_RELPATH
    skill.parent.mkdir(parents=True, exist_ok=True)
    skill.write_text("")
    allocator = skill.with_name("prepare_pr_body.py")
    allocator.write_text(
        (
            REPO_ROOT
            / ".claude"
            / "skills"
            / "github"
            / "scripts"
            / "pr"
            / "prepare_pr_body.py"
        ).read_text(encoding="utf-8"),
        encoding="utf-8",
    )
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
        source_body = tmp_path / "b.md"
        source_body.write_text("body file", encoding="utf-8")
        _, command = self._run(
            mock_root,
            tmp_path,
            [
                "--title", "fix: t", "--base", "release", "--head", "topic",
                "--body-file", str(source_body), "--draft",
                "--skip-validation", "--audit-reason", "hotfix",
            ],
        )
        assert command[command.index("--base") + 1] == "release"
        assert command[command.index("--head") + 1] == "topic"
        assert "--body" not in command
        prepared = command[command.index("--body-file") + 1]
        assert prepared.startswith(".agents/scratch/pr-body-")
        assert command[command.index("--audit-reason") + 1] == "hotfix"
        assert "--draft" in command
        assert "--skip-validation" in command

    def test_forwards_inline_body(
        self, mock_root: MagicMock, _which: MagicMock, tmp_path: Path
    ) -> None:
        _, command = self._run(
            mock_root, tmp_path, ["--title", "fix: t", "--body", "text"]
        )
        assert command[command.index("--body") + 1] == "text"

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
        """Return the options the real target's parser accepts.

        Reads argparse's own action registry through _PARSER_PROBE rather than
        parsing --help text; see that constant for why each of those three
        choices (argparse over text, interception over build_parser, subprocess
        over import) is load-bearing.
        """
        target = REPO_ROOT / SKILL_RELPATH
        result = subprocess.run(
            [sys.executable, "-c", _PARSER_PROBE, str(target)],
            capture_output=True,
            text=True,
            check=False,
            cwd=cwd,
        )
        line = next(
            (
                one
                for one in result.stdout.splitlines()
                if one.startswith(_FLAGS_SENTINEL)
            ),
            None,
        )
        assert line is not None, (
            f"parser probe did not reach {SKILL_RELPATH}'s parse_args "
            f"(exit {result.returncode}). stdout: {result.stdout!r} "
            f"stderr: {result.stderr!r}"
        )
        return frozenset(json.loads(line[len(_FLAGS_SENTINEL) :]))

    @staticmethod
    def _emitted_flags(argv: list[str]) -> list[str]:
        """Return the args the wrapper would hand the target, without argv[0:2]."""
        args = _build_parser().parse_args(argv)
        return _build_skill_args(Path("unused.py"), args)[2:]

    def test_probe_reaches_the_targets_real_parser(self, tmp_path: Path) -> None:
        """Guards the check itself.

        The two contract tests below compare against whatever this probe
        returns. If the probe stopped reaching parse_args it would assert on the
        missing sentinel, and if it reached a parser with no options the two
        tests would report every emitted flag as unknown, so the failure is loud
        either way. This test exists to say which of the two broke.
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
        """Compare by set membership against argparse's registry, never by text.

        `--body` is a substring of `--body-file`, so a containment check against
        raw help output would keep passing after `--body` was removed. Set
        membership over option_strings has no such hole.
        """
        unknown = [a for a in emitted if a.startswith("--") and a not in accepted]
        assert not unknown, (
            f"wrapper emits {unknown}, which {SKILL_RELPATH} does not accept; "
            f"it accepts {sorted(accepted)}"
        )
