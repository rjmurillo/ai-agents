"""Drift guards for the lifecycle command files.

Refs #1926. These tests catch the configuration drift pattern that
surfaces when a new lifecycle command is added without updating the
two parallel exclusion lists in `.markdownlint-cli2.yaml` and
`.githooks/pre-commit`.

A "lifecycle command" is a `.claude/commands/<name>.md` file whose body
opens with `@CLAUDE.md` (the marker that distinguishes lifecycle slash-
commands from ordinary command files). Lifecycle commands have YAML
frontmatter + `@CLAUDE.md` body shape with no H1 heading and no
Triggers/Verification sections. They are excluded from markdownlint
MD041 and SkillForge structural validation.

The canonical set is derived from the filesystem at test time, so adding
a new lifecycle command (a new file under `.claude/commands/` whose body
starts with `@CLAUDE.md`) automatically extends the drift checks. The
test set is no longer a hand-maintained constant.
"""

from __future__ import annotations

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
COMMANDS_DIR = PROJECT_ROOT / ".claude" / "commands"
MARKDOWNLINT_CONFIG = PROJECT_ROOT / ".markdownlint-cli2.yaml"
PRE_COMMIT_HOOK = PROJECT_ROOT / ".githooks" / "pre-commit"


def _discover_lifecycle_commands() -> set[str]:
    """Discover lifecycle commands by scanning `.claude/commands/*.md` for
    files whose body opens with `@CLAUDE.md`. The first non-frontmatter,
    non-blank line of the body is the marker."""
    discovered: set[str] = set()
    for path in COMMANDS_DIR.glob("*.md"):
        text = path.read_text(encoding="utf-8")
        # Strip YAML frontmatter if present.
        body = re.sub(r"^---\r?\n.*?\r?\n---\r?\n", "", text, count=1, flags=re.DOTALL)
        for line in body.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("@CLAUDE.md"):
                discovered.add(path.stem)
            break
    return discovered


# Canonical set, derived from filesystem at import time. If the discovery
# logic itself drifts, `test_canonical_set_matches_known_lifecycle_commands`
# below pins it against the documented set.
LIFECYCLE_COMMANDS = _discover_lifecycle_commands()


def test_canonical_set_matches_known_lifecycle_commands() -> None:
    """Sanity: the auto-discovered set matches the documented set as of
    issue #1926. If a new lifecycle command lands, update this expected
    set in the same PR. That signals the author has consciously taken
    on the additional drift-guard surface."""
    expected = {"spec", "plan", "build", "test", "ship"}
    assert LIFECYCLE_COMMANDS == expected, (
        f"discovered lifecycle commands {LIFECYCLE_COMMANDS} != "
        f"documented {expected}; update both this set and the exclusion "
        f"lists in `.markdownlint-cli2.yaml` and `.githooks/pre-commit`"
    )


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
    # Match the path inside any YAML quoting (single, double, or
    # unquoted) by anchoring on the path string itself with surrounding
    # boundary chars (line break, comment, list marker, quote).
    # Per coderabbit PR #1931 comment 3213980868: the previous trailing-
    # double-quote anchor failed if the YAML formatter switched style.
    config = MARKDOWNLINT_CONFIG.read_text(encoding="utf-8")
    for cmd in LIFECYCLE_COMMANDS:
        claude_path = f".claude/commands/{cmd}.md"
        copilot_path = f"src/copilot-cli/skills/{cmd}/SKILL.md"
        # Use a regex that allows surrounding quotes (any style) or no
        # quotes; anchored on path-component boundary (start of line,
        # whitespace, list marker, or quote char).
        claude_re = rf"(?:^|[\s\-\"'])\.claude/commands/{re.escape(cmd)}\.md(?:[\s\"']|$)"
        copilot_re = rf"(?:^|[\s\-\"'])src/copilot-cli/skills/{re.escape(cmd)}/SKILL\.md(?:[\s\"']|$)"
        assert re.search(claude_re, config, re.MULTILINE), (
            f"markdownlint ignores missing entry for {cmd} (Claude Code): {claude_path}"
        )
        assert re.search(copilot_re, config, re.MULTILINE), (
            f"markdownlint ignores missing entry for {cmd} (Copilot CLI mirror): {copilot_path}"
        )


def test_pre_commit_hook_excludes_match_lifecycle_commands() -> None:
    """`.githooks/pre-commit` skill-validator filter must include every
    lifecycle command in the Copilot CLI exclusion regex.

    Per gemini-code-assist review (PR #1931 comment 3213946213): the
    extraction regex anchors on path-component boundaries (`(?<=^| )` /
    leading whitespace before `src/`, end-of-pattern `$/SKILL\\.md$`)
    so the matched alternation cannot accidentally span an unrelated
    portion of the hook text.
    """
    # Allow `[\w-]` in alternatives so a hyphenated lifecycle name (e.g.
    # `foo-bar`) does not break extraction. Per coderabbit PR #1931
    # comment 3213980871.
    hook = PRE_COMMIT_HOOK.read_text(encoding="utf-8")
    match = re.search(
        r"\^src/copilot-cli/skills/\(([\w|\-]+)\)/SKILL\\\.md\$",
        hook,
    )
    assert match is not None, (
        "pre-commit hook lifecycle exclusion regex not found "
        "(expected anchored `^src/copilot-cli/skills/(...)/SKILL\\.md$` literal)"
    )
    regex_commands = set(match.group(1).split("|"))
    # Issue #2743: the exclusion regex covers two kinds of command-mirror skill.
    # The `@CLAUDE.md`-led lifecycle commands (LIFECYCLE_COMMANDS) plus four
    # additional command-mirrors (checkpoint, pr-review, retro, sync) that use
    # the slash-command frontmatter shape and also fail SkillForge structural
    # validation. The regex must include every lifecycle command and equal the
    # documented full command-mirror exclusion set.
    additional_command_mirrors = {"checkpoint", "pr-review", "retro", "sync"}
    expected_exclusions = LIFECYCLE_COMMANDS | additional_command_mirrors
    assert LIFECYCLE_COMMANDS <= regex_commands, (
        f"pre-commit hook exclusion regex {regex_commands} is missing "
        f"lifecycle commands {LIFECYCLE_COMMANDS - regex_commands}"
    )
    assert regex_commands == expected_exclusions, (
        f"pre-commit hook exclusion regex {regex_commands} != "
        f"documented command-mirror exclusions {expected_exclusions}"
    )
