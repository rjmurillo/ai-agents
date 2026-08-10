"""Validation-base resolution tests for new_pr.py.

Split from the former single ``tests/test_new_pr.py`` (issue #4764), which had
grown to 1,390 lines and mixed unrelated responsibilities in one module. The
shared import of the script under test and the subprocess helpers live in
``tests/new_pr_harness.py`` so no module re-derives them.
"""

from __future__ import annotations

from unittest.mock import patch

from tests.new_pr_harness import (
    SCRIPTS_DIR,
    _resolve_validation_base,
    build_parser,
    main,
)
from tests.new_pr_harness import (
    completed as _completed,
)
from tests.new_pr_harness import (
    new_pr as _mod,
)

_SCRIPTS_DIR = SCRIPTS_DIR


class TestResolveValidationBase:
    """_resolve_validation_base selects the right git ref for local diffs.

    The defect: in a linked worktree the local branch ref (e.g. ``main``) is
    never advanced, so ``git diff main...HEAD`` over-counts changed files by
    hundreds. ``origin/main`` tracks the remote and is always current.
    """

    def test_returns_explicit_when_provided(self):
        """Explicit --validation-base overrides everything; no git call made."""
        with patch("subprocess.run") as mock_run:
            result = _resolve_validation_base("main", explicit="refs/remotes/upstream/main")
        assert result == "refs/remotes/upstream/main"
        mock_run.assert_not_called()

    def test_returns_origin_ref_when_it_exists(self):
        """When origin/main resolves, return origin/main, not main."""
        with patch("subprocess.run", return_value=_completed(rc=0)) as mock_run:
            result = _resolve_validation_base("main")
        assert result == "origin/main"
        mock_run.assert_called_once()
        argv = mock_run.call_args[0][0]
        assert argv == ["git", "rev-parse", "--verify", "origin/main"]

    def test_falls_back_to_pr_base_when_origin_absent(self):
        """When origin/main does not exist (no remote), fall back to main."""
        with patch("subprocess.run", return_value=_completed(rc=1)):
            result = _resolve_validation_base("main")
        assert result == "main"

    def test_non_main_base_resolves_origin_ref(self):
        """Works for any base branch name, not just main."""
        with patch("subprocess.run", return_value=_completed(rc=0)):
            result = _resolve_validation_base("develop")
        assert result == "origin/develop"

    def test_explicit_empty_string_triggers_auto_resolve(self):
        """Empty string for explicit is treated as absent; auto-resolution runs."""
        with patch("subprocess.run", return_value=_completed(rc=0)):
            result = _resolve_validation_base("main", explicit="")
        assert result == "origin/main"


class TestMainUsesResolvedValidationBase:
    """main() passes the resolved validation base to run_validations, not args.base.

    The gh pr create call still receives the bare branch name.
    """

    def _base_calls(self, branch: str = "feat/x"):
        return [
            _completed(rc=0),        # gh --version
            _completed(stdout=branch + "\n"),  # git branch --show-current
            _completed(rc=0),        # git rev-parse --verify origin/main
        ]

    def test_validation_base_uses_origin_ref_not_local(self, tmp_path):
        """run_validations receives origin/main, not main, when origin resolves."""
        calls = self._base_calls()
        calls.append(_completed(rc=0))  # gh pr create

        with patch("subprocess.run", side_effect=calls):
            with patch.object(_mod, "get_repo_root", return_value=str(tmp_path)):
                with patch.object(_mod, "run_validations") as mock_val:
                    main(["--title", "feat: test", "--base", "main"])

        mock_val.assert_called_once()
        assert mock_val.call_args[0][1] == "origin/main"

    def test_gh_pr_create_still_receives_bare_base(self, tmp_path):
        """gh pr create --base always gets the bare branch name, not origin/main."""
        captured: list[list[str]] = []

        def _side(argv, **kwargs):
            if argv and argv[0] == "gh" and "create" in argv:
                captured.append(list(argv))
                return _completed(rc=0)
            if argv and argv == ["git", "branch", "--show-current"]:
                return _completed(stdout="feat/x\n")
            return _completed(rc=0)

        with patch("subprocess.run", side_effect=_side):
            with patch.object(_mod, "get_repo_root", return_value=str(tmp_path)):
                with patch.object(_mod, "run_validations"):
                    main(["--title", "feat: test", "--base", "main"])

        assert captured, "gh pr create never called"
        gh_argv = captured[-1]
        base_idx = gh_argv.index("--base")
        assert gh_argv[base_idx + 1] == "main"

    def test_explicit_validation_base_overrides_auto_resolve(self, tmp_path):
        """--validation-base bypasses origin/ resolution entirely."""
        calls = [
            _completed(rc=0),         # gh --version
            _completed(stdout="feat/x\n"),  # git branch --show-current
            _completed(rc=0),         # gh pr create
        ]

        with patch("subprocess.run", side_effect=calls):
            with patch.object(_mod, "get_repo_root", return_value=str(tmp_path)):
                with patch.object(_mod, "run_validations") as mock_val:
                    main([
                        "--title", "feat: test",
                        "--base", "main",
                        "--validation-base", "refs/remotes/upstream/main",
                    ])

        mock_val.assert_called_once()
        assert mock_val.call_args[0][1] == "refs/remotes/upstream/main"

    def test_validation_base_falls_back_when_no_remote(self, tmp_path):
        """When origin/<base> does not resolve, validation uses bare base name."""
        calls = [
            _completed(rc=0),         # gh --version
            _completed(stdout="feat/x\n"),  # git branch --show-current
            _completed(rc=1),         # git rev-parse --verify origin/main: absent
            _completed(rc=0),         # gh pr create
        ]

        with patch("subprocess.run", side_effect=calls):
            with patch.object(_mod, "get_repo_root", return_value=str(tmp_path)):
                with patch.object(_mod, "run_validations") as mock_val:
                    main(["--title", "feat: test", "--base", "main"])

        mock_val.assert_called_once()
        assert mock_val.call_args[0][1] == "main"

    def test_build_parser_accepts_validation_base(self):
        args = build_parser().parse_args([
            "--title", "feat: test",
            "--base", "main",
            "--validation-base", "origin/main",
        ])
        assert args.validation_base == "origin/main"

    def test_build_parser_validation_base_defaults_to_empty(self):
        args = build_parser().parse_args(["--title", "feat: test"])
        assert args.validation_base == ""
