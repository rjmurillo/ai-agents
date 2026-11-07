"""Terminal-stdin guard of validate_findings_scope.py."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script

mod = import_skill_script(
    ".claude/skills/review/scripts/validate_findings_scope.py",
    module_name="validate_findings_scope_stdin",
)
main = mod.main


class _TtyStdin:
    """Stand-in for an interactive terminal stdin that fails the test if read."""

    def isatty(self) -> bool:
        return True

    def read(self) -> str:
        raise AssertionError("must not block reading a terminal")


def test_main_without_text_on_terminal_stdin_exits_two_without_reading(capsys) -> None:
    with patch.object(sys, "stdin", _TtyStdin()):
        rc = main(["--worktree", ".", "--base-branch", "main"])

    captured = capsys.readouterr()
    assert rc == 2
    assert captured.out == ""
    assert "stdin is a terminal" in captured.err


def test_main_with_text_ignores_terminal_stdin(capsys) -> None:
    with patch.object(sys, "stdin", _TtyStdin()):
        with patch.object(mod, "get_diff_files", return_value=None):
            rc = main(["--worktree", ".", "--text", "no findings here"])

    assert rc == 0


def test_main_without_text_and_closed_stdin_exits_two(capsys) -> None:
    with patch.object(sys, "stdin", None):
        rc = main(["--worktree", ".", "--base-branch", "main"])

    assert rc == 2
    assert "terminal or closed" in capsys.readouterr().err
