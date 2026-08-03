"""Tests for scripts.validation.command_size module.

Issue #4016: the slashcommandcreator SKILL.md states a 200-line ceiling three
times, but nothing previously enforced it. These tests pin the validator so
the ceiling cannot drift silently again.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.validation.command_size import (
    COMMAND_SIZE_LIMIT,
    COMMAND_SIZE_WARNING,
    check_command_size,
    get_command_files,
    has_exception_rationale,
    has_size_exception,
    main,
)

_GOOD_FRONTMATTER = "---\ndescription: test command\nallowed-tools: Read\n---\n\n"
_EXCEPTION_FRONTMATTER = "---\ndescription: test\nsize-exception: true\n---\n\n"
_LONG_RATIONALE = (
    "<!--\nsize-exception rationale. This command carries irreducible protocol "
    "content that cannot be moved to references/ without changing runtime behavior. "
    "Tracked for conversion in issue #9999.\n-->\n"
)


def _body(n_lines: int, content: str = "- item") -> str:
    return "\n".join([content] * n_lines)


@pytest.fixture(autouse=True)
def _isolate_ci_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stop the ambient environment from choosing the assertion.

    ``main`` defaults ``--ci`` to the ``CI`` environment variable, so a call
    that omits the flag inherits whatever the runner exports. Locally ``CI``
    is unset and the lenient branch runs; on GitHub Actions ``CI=true`` and
    the blocking branch runs instead. Clearing the variable makes every test
    in this module assert the branch it names.
    """
    monkeypatch.delenv("CI", raising=False)


class TestHasSizeException:
    def test_true_value_detected(self) -> None:
        content = "---\nsize-exception: true\n---\n"
        assert has_size_exception(content) is True

    def test_false_value_not_detected(self) -> None:
        content = "---\nsize-exception: false\n---\n"
        assert has_size_exception(content) is False

    def test_missing_key_not_detected(self) -> None:
        content = "---\ndescription: test\n---\n"
        assert has_size_exception(content) is False


class TestHasExceptionRationale:
    def test_closed_comment_with_rationale_qualifies(self) -> None:
        content = _EXCEPTION_FRONTMATTER + _LONG_RATIONALE + "# body\n"
        assert has_exception_rationale(content) is True

    def test_open_comment_spanning_past_window_qualifies(self) -> None:
        # Comment that starts within the search window but closes beyond it.
        long_body = "\n".join([f"line {i}" for i in range(40)])
        content = _EXCEPTION_FRONTMATTER + "<!--\nsize-exception rationale. " + long_body
        assert has_exception_rationale(content) is True

    def test_missing_comment_does_not_qualify(self) -> None:
        content = _EXCEPTION_FRONTMATTER + "# body\n"
        assert has_exception_rationale(content) is False

    def test_comment_without_rationale_keyword_does_not_qualify(self) -> None:
        content = _EXCEPTION_FRONTMATTER + "<!-- just a note -->\n"
        assert has_exception_rationale(content) is False

    def test_short_comment_does_not_qualify(self) -> None:
        content = _EXCEPTION_FRONTMATTER + "<!-- rationale: short -->\n"
        assert has_exception_rationale(content) is False


class TestCheckCommandSize:
    def test_under_warning_passes(self, tmp_path: Path) -> None:
        f = tmp_path / "cmd.md"
        f.write_text(_GOOD_FRONTMATTER + _body(COMMAND_SIZE_WARNING - 10))
        result = check_command_size(f)
        assert result.passed is True
        assert result.warning is False

    def test_between_warning_and_limit_warns(self, tmp_path: Path) -> None:
        f = tmp_path / "cmd.md"
        f.write_text(_GOOD_FRONTMATTER + _body(COMMAND_SIZE_WARNING + 5))
        result = check_command_size(f)
        assert result.passed is True
        assert result.warning is True

    def test_at_limit_passes(self, tmp_path: Path) -> None:
        """Exactly 200 total lines must pass: pins the numeric ceiling value."""
        # Use a literal 200 so ceiling mutations (e.g. 200->201) are detected.
        target = 200
        fm_lines = len(_GOOD_FRONTMATTER.splitlines())
        f = tmp_path / "cmd.md"
        f.write_text(_GOOD_FRONTMATTER + _body(target - fm_lines))
        result = check_command_size(f)
        assert result.line_count == target
        assert result.passed is True

    def test_one_over_limit_fails(self, tmp_path: Path) -> None:
        """201 total lines must fail: pins the one-past-ceiling boundary."""
        target = 201
        fm_lines = len(_GOOD_FRONTMATTER.splitlines())
        f = tmp_path / "cmd.md"
        f.write_text(_GOOD_FRONTMATTER + _body(target - fm_lines))
        result = check_command_size(f)
        assert result.line_count == target
        assert result.passed is False

    def test_over_limit_without_exception_fails(self, tmp_path: Path) -> None:
        f = tmp_path / "cmd.md"
        f.write_text(_GOOD_FRONTMATTER + _body(COMMAND_SIZE_LIMIT + 10))
        result = check_command_size(f)
        assert result.passed is False
        assert result.errors

    def test_over_limit_with_exception_and_rationale_passes(self, tmp_path: Path) -> None:
        f = tmp_path / "cmd.md"
        f.write_text(_EXCEPTION_FRONTMATTER + _LONG_RATIONALE + _body(COMMAND_SIZE_LIMIT + 10))
        result = check_command_size(f)
        assert result.passed is True
        assert result.warning is True

    def test_over_limit_with_exception_but_no_rationale_fails(self, tmp_path: Path) -> None:
        f = tmp_path / "cmd.md"
        f.write_text(_EXCEPTION_FRONTMATTER + _body(COMMAND_SIZE_LIMIT + 10))
        result = check_command_size(f)
        assert result.passed is False
        assert any("rationale" in e.lower() for e in result.errors)


class TestGetCommandFiles:
    def test_finds_md_in_commands_dir(self, tmp_path: Path) -> None:
        (tmp_path / "cmd.md").write_text("# cmd")
        files = get_command_files(path=str(tmp_path))
        assert len(files) == 1

    def test_changed_files_filters_to_commands(self, tmp_path: Path) -> None:
        cmd_dir = tmp_path / ".claude" / "commands"
        cmd_dir.mkdir(parents=True)
        f = cmd_dir / "cmd.md"
        f.write_text("# cmd")
        files = get_command_files(changed_files=[str(f)])
        assert len(files) == 1

    def test_changed_files_without_commands_returns_empty(self) -> None:
        files = get_command_files(changed_files=["src/foo.py", "tests/bar.py"])
        assert files == []


class TestMain:
    def test_clean_dir_exits_0(self, tmp_path: Path) -> None:
        f = tmp_path / "small.md"
        f.write_text(_GOOD_FRONTMATTER + _body(50))
        result = main(["--path", str(tmp_path)])
        assert result == 0

    def test_over_limit_ci_mode_exits_1(self, tmp_path: Path) -> None:
        f = tmp_path / "big.md"
        f.write_text(_GOOD_FRONTMATTER + _body(COMMAND_SIZE_LIMIT + 50))
        result = main(["--path", str(tmp_path), "--ci"])
        assert result == 1

    def test_over_limit_no_ci_exits_0(self, tmp_path: Path) -> None:
        f = tmp_path / "big.md"
        f.write_text(_GOOD_FRONTMATTER + _body(COMMAND_SIZE_LIMIT + 50))
        result = main(["--path", str(tmp_path)])
        assert result == 0

    def test_env_ci_true_blocks_without_the_flag(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """CI=true must block an over-size command even with no --ci flag.

        This pins the environment default the autouse fixture clears. Without
        it, a change that stopped reading CI would leave every workflow that
        relies on the exported variable silently advisory.
        """
        monkeypatch.setenv("CI", "true")
        f = tmp_path / "big.md"
        f.write_text(_GOOD_FRONTMATTER + _body(COMMAND_SIZE_LIMIT + 50))
        result = main(["--path", str(tmp_path)])
        assert result == 1

    def test_exception_with_rationale_ci_exits_0(self, tmp_path: Path) -> None:
        f = tmp_path / "big.md"
        f.write_text(_EXCEPTION_FRONTMATTER + _LONG_RATIONALE + _body(COMMAND_SIZE_LIMIT + 50))
        result = main(["--path", str(tmp_path), "--ci"])
        assert result == 0


class TestShippedCommandsPassGate:
    """The two known over-size commands must have valid exceptions.

    Issue #4016: spec.md and pr-autofix.md exceed the 200-line ceiling and are
    grandfathered with documented exceptions.
    """

    @pytest.mark.parametrize("relative", [
        ".claude/commands/spec.md",
        ".claude/commands/pr-autofix.md",
    ])
    def test_shipped_exception_is_valid(self, relative: str) -> None:
        root = Path(__file__).resolve().parents[1]
        p = root / relative
        result = check_command_size(p)
        assert result.passed, (
            f"{relative} fails the command-size gate: {result.errors}. "
            "Either fix the file or update its size-exception rationale."
        )
