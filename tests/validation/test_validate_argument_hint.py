"""Tests for scripts.validation.validate_argument_hint."""

from __future__ import annotations

from pathlib import Path

from scripts.validation import validate_argument_hint as v

REPO_ROOT = Path(__file__).resolve().parents[2]


def _write(path: Path, frontmatter: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{frontmatter}---\n\nBody.\n", encoding="utf-8")


def test_good_quoted_scalar_passes(tmp_path: Path) -> None:
    command = tmp_path / ".claude" / "commands" / "good.md"
    _write(command, "argument-hint: '[BASE_BRANCH]'\n")

    assert v.find_argument_hint_violations([command]) == []


def test_unquoted_flow_sequence_fails(tmp_path: Path) -> None:
    command = tmp_path / ".claude" / "commands" / "bad.md"
    _write(command, "argument-hint: [BASE_BRANCH]\n")

    violations = v.find_argument_hint_violations([command])

    assert len(violations) == 1
    assert violations[0].line == 2
    assert "YAML parsed list" in violations[0].reason
    assert violations[0].suggestion == "argument-hint: '[BASE_BRANCH]'"


def test_unquoted_adjacent_bracket_groups_fail(tmp_path: Path) -> None:
    command = tmp_path / ".claude" / "commands" / "bad.md"
    _write(command, "argument-hint: <PR_NUMBERS> [--parallel] [--cleanup]\n")

    violations = v.find_argument_hint_violations([command])

    assert len(violations) == 1
    assert "adjacent bracket groups" in violations[0].reason
    assert (
        violations[0].suggestion
        == "argument-hint: '<PR_NUMBERS> [--parallel] [--cleanup]'"
    )


def test_default_scan_includes_github_prompts(tmp_path: Path) -> None:
    prompt = tmp_path / ".github" / "prompts" / "pr-review.prompt.md"
    _write(prompt, "argument-hint: <PR_NUMBERS> [--parallel] [--cleanup]\n")

    paths = v.collect_scan_paths(tmp_path, [])
    violations = v.find_argument_hint_violations(paths)

    assert prompt in paths
    assert len(violations) == 1
    assert violations[0].path == prompt


def test_unbalanced_brackets_fail_even_when_quoted(tmp_path: Path) -> None:
    command = tmp_path / ".claude" / "commands" / "bad.md"
    _write(command, "argument-hint: '<PR_NUMBERS> [--parallel'\n")

    violations = v.find_argument_hint_violations([command])

    assert len(violations) == 1
    assert "unbalanced square brackets" in violations[0].reason


def test_indented_block_scalar_argument_hint_text_is_ignored(tmp_path: Path) -> None:
    command = tmp_path / ".claude" / "commands" / "description.md"
    _write(command, "description: |\n  argument-hint: [BASE_BRANCH]\n")

    assert v.find_argument_hint_violations([command]) == []


def test_quoted_scalar_with_trailing_comment_passes(tmp_path: Path) -> None:
    command = tmp_path / ".claude" / "commands" / "safe.md"
    _write(command, "argument-hint: '<PR_NUMBERS> [--parallel]' # safe comment\n")

    assert v.find_argument_hint_violations([command]) == []


def test_unquoted_flow_sequence_with_trailing_comment_suggests_value_only(
    tmp_path: Path,
) -> None:
    command = tmp_path / ".claude" / "commands" / "bad.md"
    _write(command, "argument-hint: [BASE_BRANCH] # optional\n")

    violations = v.find_argument_hint_violations([command])

    assert len(violations) == 1
    assert violations[0].suggestion == "argument-hint: '[BASE_BRANCH]'"


def test_missing_argument_hint_is_fine(tmp_path: Path) -> None:
    command = tmp_path / ".claude" / "commands" / "no-hint.md"
    _write(command, "description: No hint here.\n")

    assert v.find_argument_hint_violations([command]) == []


def test_real_repo_argument_hints_pass(capsys) -> None:
    result = v.main(["--repo-root", str(REPO_ROOT)])

    assert result == 0
    assert "[PASS]" in capsys.readouterr().out
