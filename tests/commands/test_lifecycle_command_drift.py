"""Drift guards for the 6 lifecycle command files.

Refs #1926. These tests catch the configuration drift pattern that
surfaces when a 7th lifecycle command is added without updating the
two parallel exclusion lists in `.markdownlint-cli2.yaml` and
`.githooks/pre-commit`.

The lifecycle commands (`spec`, `plan`, `build`, `test`, `review`, `ship`)
have YAML frontmatter + `@CLAUDE.md` body shape with no H1 heading and
no Triggers/Verification sections. They are excluded from markdownlint
MD041 and SkillForge structural validation. Adding a 7th command without
updating both lists silently re-includes the new file in CI lint and
validator passes.
"""

from __future__ import annotations

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
COMMANDS_DIR = PROJECT_ROOT / ".claude" / "commands"
MARKDOWNLINT_CONFIG = PROJECT_ROOT / ".markdownlint-cli2.yaml"
PRE_COMMIT_HOOK = PROJECT_ROOT / ".githooks" / "pre-commit"

# Canonical set. Update this set + both exclusion lists together when
# a new lifecycle command lands.
LIFECYCLE_COMMANDS = {"spec", "plan", "build", "test", "review", "ship"}


def test_lifecycle_commands_exist_in_claude_commands_dir() -> None:
    """Every lifecycle command name must have a corresponding .md file."""
    for cmd in LIFECYCLE_COMMANDS:
        path = COMMANDS_DIR / f"{cmd}.md"
        assert path.exists(), f"missing {path}"


def test_markdownlint_excludes_match_lifecycle_commands() -> None:
    """`.markdownlint-cli2.yaml` ignores list must include every lifecycle
    command twice: once for `.claude/commands/<name>.md` and once for the
    Copilot CLI mirror at `src/copilot-cli/skills/<name>/SKILL.md`.
    """
    config = MARKDOWNLINT_CONFIG.read_text(encoding="utf-8")
    for cmd in LIFECYCLE_COMMANDS:
        claude_path = f'.claude/commands/{cmd}.md"'
        copilot_path = f'src/copilot-cli/skills/{cmd}/SKILL.md"'
        assert claude_path in config, (
            f"markdownlint ignores missing entry for {cmd} (Claude Code): {claude_path}"
        )
        assert copilot_path in config, (
            f"markdownlint ignores missing entry for {cmd} (Copilot CLI mirror): {copilot_path}"
        )


def test_pre_commit_hook_excludes_match_lifecycle_commands() -> None:
    """`.githooks/pre-commit` skill-validator filter must include every
    lifecycle command in the Copilot CLI exclusion regex.
    """
    hook = PRE_COMMIT_HOOK.read_text(encoding="utf-8")
    match = re.search(
        r"src/copilot-cli/skills/\(([\w|]+)\)/SKILL\\\.md",
        hook,
    )
    assert match is not None, "pre-commit hook lifecycle exclusion regex not found"
    regex_commands = set(match.group(1).split("|"))
    assert regex_commands == LIFECYCLE_COMMANDS, (
        f"pre-commit hook exclusion regex {regex_commands} != "
        f"canonical lifecycle commands {LIFECYCLE_COMMANDS}"
    )
