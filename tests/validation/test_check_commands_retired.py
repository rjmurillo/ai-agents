"""Tests for scripts/validation/check_commands_retired.py.

ADR-064 (issue #5632) deleted the command-to-skill bridge, so a command file
placed under a plugin root now loads in Claude Code and reaches no other harness.
This guard is what makes that loud. Its tests drive ``main(argv)`` and assert on
the integer it returns, per .claude/rules/testing.md MUST 8: a helper that
returns a findings list proves the helper detected the problem and proves nothing
about whether the program fails.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.validation.check_commands_retired import (
    ALLOWED_BASENAMES,
    EXIT_CONFIG,
    EXIT_OK,
    EXIT_VIOLATION,
    PLUGIN_ROOTS,
    find_commands,
    main,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _git_repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "t@example.invalid"], cwd=tmp_path, check=True
    )
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    return tmp_path


def _add(repo: Path, relative: str, body: str = "# x\n") -> Path:
    path = repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    subprocess.run(["git", "add", "--", relative], cwd=repo, check=True)
    return path


class TestFindCommands:
    def test_an_empty_repo_has_no_commands(self, tmp_path: Path) -> None:
        assert find_commands(_git_repo(tmp_path)) == []

    @pytest.mark.parametrize("root", PLUGIN_ROOTS)
    def test_every_plugin_root_is_scanned(self, tmp_path: Path, root: str) -> None:
        """One root left out is a root a command can hide in."""
        repo = _git_repo(tmp_path)
        _add(repo, f"{root}/commands/thing.md")

        assert find_commands(repo) == [f"{root}/commands/thing.md"]

    @pytest.mark.parametrize("name", sorted(ALLOWED_BASENAMES))
    def test_agent_entrypoints_are_not_commands(self, tmp_path: Path, name: str) -> None:
        repo = _git_repo(tmp_path)
        _add(repo, f".claude/commands/{name}")

        assert find_commands(repo) == []

    def test_a_non_markdown_file_is_not_a_command(self, tmp_path: Path) -> None:
        repo = _git_repo(tmp_path)
        _add(repo, ".claude/commands/config.yaml", "a: b\n")

        assert find_commands(repo) == []

    def test_a_skills_tree_is_not_a_commands_tree(self, tmp_path: Path) -> None:
        """The prefix must be `<root>/commands/`, not any path containing it."""
        repo = _git_repo(tmp_path)
        _add(repo, ".claude/skills/thing/SKILL.md")
        _add(repo, "docs/commands/thing.md")

        assert find_commands(repo) == []

    def test_an_untracked_file_is_not_a_shipped_command(self, tmp_path: Path) -> None:
        """A scratch file under commands/ must not fail anyone's build.

        The scan reads the index rather than walking the directory, per
        .claude/rules/ci-scripts.md MUST 9. Writing the file without `git add`
        is the whole discriminator: the same bytes staged do fail, which the
        parametrized case above proves.
        """
        repo = _git_repo(tmp_path)
        path = repo / ".claude" / "commands" / "scratch.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# scratch\n", encoding="utf-8")

        assert find_commands(repo) == []

    def test_results_are_sorted(self, tmp_path: Path) -> None:
        repo = _git_repo(tmp_path)
        _add(repo, ".claude/commands/zeta.md")
        _add(repo, ".claude/commands/alpha.md")

        assert find_commands(repo) == [
            ".claude/commands/alpha.md",
            ".claude/commands/zeta.md",
        ]


class TestMain:
    def test_a_clean_repo_exits_zero(self, tmp_path: Path) -> None:
        assert main(["--repo-root", str(_git_repo(tmp_path))]) == EXIT_OK

    def test_a_clean_repo_reports_what_it_examined(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A zero-finding run must be distinguishable from a run that did nothing.

        .claude/rules/ci-scripts.md MUST 12: print the examined count next to
        the violation count, or a green result cannot be told from an empty one.
        """
        main(["--repo-root", str(_git_repo(tmp_path))])

        assert f"{len(PLUGIN_ROOTS)} plugin root(s)" in capsys.readouterr().out

    def test_a_command_exits_one(self, tmp_path: Path) -> None:
        repo = _git_repo(tmp_path)
        _add(repo, ".claude/commands/thing.md")

        assert main(["--repo-root", str(repo)]) == EXIT_VIOLATION

    def test_the_failure_names_the_file_and_the_remedy(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        repo = _git_repo(tmp_path)
        _add(repo, ".claude/commands/thing.md")
        main(["--repo-root", str(repo)])

        err = capsys.readouterr().err
        assert ".claude/commands/thing.md" in err
        assert "skills/<name>/SKILL.md" in err

    def test_a_missing_root_exits_two(self, tmp_path: Path) -> None:
        assert main(["--repo-root", str(tmp_path / "absent")]) == EXIT_CONFIG

    def test_a_non_git_directory_exits_two(self, tmp_path: Path) -> None:
        """git ls-files fails outside a work tree; that is config, not a pass."""
        assert main(["--repo-root", str(tmp_path)]) == EXIT_CONFIG


def test_this_repository_ships_no_commands() -> None:
    """The live assertion ADR-064 closes on, driven through the CLI."""
    assert main(["--repo-root", str(_REPO_ROOT)]) == EXIT_OK
