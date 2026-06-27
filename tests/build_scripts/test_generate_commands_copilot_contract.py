"""Copilot CLI runtime-contract tests for the command-to-skill bridge.

Issue #2743. Verifies the translation that `generate_commands` applies to
Claude Code conventions when emitting Copilot CLI skill bodies, plus a gate
over the committed `src/copilot-cli/skills/*/SKILL.md` artifacts so a
hand-edit or merge cannot resurrect the broken tokens.

The runtime contract these conventions violate was verified empirically
against GitHub Copilot CLI 1.0.66-1 (recorded in Serena memory
`decisions/decision-copilot-cli-skill-task-arguments-claude-import-contract`):

  - `$ARGUMENTS`               -> UNRECOGNIZED-TOKEN (no argument vector)
  - `@CLAUDE.md` first line    -> LITERAL-TEXT (not auto-inlined)
  - `Skill(skill="X")`         -> not callable; real tool is `skill`
  - `Task(subagent_type="Y")`  -> not callable; real tool is `task`,
                                  agent_type `project-toolkit:Y`

Each positive assertion is paired with a negative control proving the test
fails when the translation is wrong (a raw body still carries the tokens).
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "build"))

import copilot_body_translation  # noqa: E402

_COPILOT_SKILLS = REPO_ROOT / "src" / "copilot-cli" / "skills"

_CLAUDE_BODY = (
    "@CLAUDE.md\n"
    "\n"
    "Spec: $ARGUMENTS\n"
    "\n"
    "If $ARGUMENTS is empty, ask the user.\n"
    "\n"
    '1. chestertons-fence: invoke `Skill(skill="chestertons-fence")`.\n'
    '9. Task(subagent_type="critic"): review the spec.\n'
)


# Translation unit -----------------------------------------------------------


def test_arguments_token_removed(tmp_path: Path) -> None:
    """`$ARGUMENTS` must not survive translation (Copilot has no arg vector)."""
    out = copilot_body_translation.translate_body(_CLAUDE_BODY, tmp_path)
    assert "$ARGUMENTS" not in out
    # Negative control: the raw body still carries the token.
    assert "$ARGUMENTS" in _CLAUDE_BODY


def test_include_line_replaced_with_note(tmp_path: Path) -> None:
    """`@CLAUDE.md` standalone include becomes a Copilot note, not literal text."""
    out = copilot_body_translation.translate_body(_CLAUDE_BODY, tmp_path)
    assert "\n@CLAUDE.md\n" not in f"\n{out}"
    assert not out.startswith("@CLAUDE.md")
    assert "load via the plugin instructions tree" in out
    # Negative control: the raw body starts with the literal include.
    assert _CLAUDE_BODY.startswith("@CLAUDE.md")


def test_skill_call_mapped_in_appendix(tmp_path: Path) -> None:
    """Every inline Skill() call gets a `skill` tool row in the appendix."""
    out = copilot_body_translation.translate_body(_CLAUDE_BODY, tmp_path)
    assert "## Copilot CLI invocation reference" in out
    assert '| `Skill(skill="chestertons-fence")` | `skill` tool, ' in out
    # Negative control: a body with no Skill/Task calls gets no appendix.
    plain = copilot_body_translation.translate_body("No calls here.\n", tmp_path)
    assert "Copilot CLI invocation reference" not in plain


def test_task_call_mapped_with_plugin_namespace(tmp_path: Path) -> None:
    """Task() maps to the `task` tool with the plugin-namespaced agent_type."""
    out = copilot_body_translation.translate_body(_CLAUDE_BODY, tmp_path)
    assert (
        '| `Task(subagent_type="critic")` | `task` tool, '
        '`agent_type: "project-toolkit:critic"` |' in out
    )


def test_inline_calls_preserved_for_parity(tmp_path: Path) -> None:
    """Inline Skill()/Task() syntax stays in the body (parity blocks intact).

    The Step 0 / Step 9 byte-identity tests require the inline calls to match
    the Claude source. The appendix is additive, not a rewrite.
    """
    out = copilot_body_translation.translate_body(_CLAUDE_BODY, tmp_path)
    assert 'Skill(skill="chestertons-fence")' in out
    assert 'Task(subagent_type="critic")' in out


def test_plugin_name_read_from_manifest(tmp_path: Path) -> None:
    """The agent_type namespace is sourced from the output tree's plugin.json."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    manifest_dir = tmp_path / ".claude-plugin"
    manifest_dir.mkdir()
    (manifest_dir / "plugin.json").write_text('{"name": "acme-kit"}\n')

    out = copilot_body_translation.translate_body(_CLAUDE_BODY, skills_dir)
    assert '`agent_type: "acme-kit:critic"`' in out


def test_plugin_name_reads_top_level_name_when_author_name_comes_first(tmp_path: Path) -> None:
    """Nested author.name must not override the top-level plugin name."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    manifest_dir = tmp_path / ".claude-plugin"
    manifest_dir.mkdir()
    (manifest_dir / "plugin.json").write_text(
        '{"author": {"name": "wrong"}, "name": "acme-kit"}\n',
        encoding="utf-8",
    )

    out = copilot_body_translation.translate_body(_CLAUDE_BODY, skills_dir)
    assert '`agent_type: "acme-kit:critic"`' in out


def test_plugin_name_falls_back_when_manifest_absent(tmp_path: Path) -> None:
    """Without a manifest, the default plugin name is used."""
    out = copilot_body_translation.translate_body(_CLAUDE_BODY, tmp_path / "skills")
    assert '`agent_type: "project-toolkit:critic"`' in out


# Full SKILL.md (frontmatter-preserving) path --------------------------------


def test_translate_skill_file_preserves_frontmatter(tmp_path: Path) -> None:
    """translate_skill_file leaves frontmatter untouched, translates the body."""
    content = (
        "---\n"
        "name: demo\n"
        "description: A demo skill.\n"
        "---\n"
        + _CLAUDE_BODY
    )
    out = copilot_body_translation.translate_skill_file(content, tmp_path)
    assert out.startswith("---\nname: demo\ndescription: A demo skill.\n---\n")
    assert "$ARGUMENTS" not in out
    assert "## Copilot CLI invocation reference" in out


def test_translate_skill_file_preserves_crlf_frontmatter(tmp_path: Path) -> None:
    """CRLF frontmatter remains frontmatter instead of being translated as body."""
    content = (
        "---\r\n"
        "name: demo\r\n"
        "description: A demo skill.\r\n"
        "---\r\n"
        + _CLAUDE_BODY
    )
    out = copilot_body_translation.translate_skill_file(content, tmp_path)
    assert out.startswith("---\r\nname: demo\r\ndescription: A demo skill.\r\n---\r\n")
    assert "$ARGUMENTS" not in out
    assert "## Copilot CLI invocation reference" in out


def test_translate_skill_file_matches_call_with_extra_args(tmp_path: Path) -> None:
    """Task()/Skill() calls with trailing args (e.g. prompt=) are still mapped."""
    body = 'Task(subagent_type="architect", prompt="Create ADR")\n'
    out = copilot_body_translation.translate_body(body, tmp_path)
    assert '`agent_type: "project-toolkit:architect"`' in out


def test_inline_calls_allow_spaces_and_single_quotes(tmp_path: Path) -> None:
    """Formatted Skill()/Task() calls still appear in the appendix."""
    body = "Skill( skill = 'memory')\nTask( subagent_type = 'critic')\n"
    out = copilot_body_translation.translate_body(body, tmp_path)
    assert '| `Skill(skill="memory")` | `skill` tool, `skill: "memory"` |' in out
    assert '`agent_type: "project-toolkit:critic"`' in out


# Committed-artifact gate ----------------------------------------------------


# The committed-artifact gate covers every translated Copilot SKILL.md this
# branch ships clean:
#   1. The nine lifecycle command-mirrors at .claude/commands/<name>.md mirrored
#      into src/copilot-cli/skills/<name>/SKILL.md.
#   2. The three skill-tree mirrors whose SOURCE skills pass SkillForge after
#      translation: orphan-ref-validator, review, security-detection.
# The two skill-tree mirrors whose SOURCE skills fail SkillForge independently
# (cva-analysis, slashcommandcreator: unsafe trigger characters, and an
# unexpected `trigger` frontmatter key on slashcommandcreator) are out of scope:
# their translated output is intentionally not committed and is deferred to
# #2755. Gating them would assert over artifacts this PR does not ship.
# Refs #2743. Refs #2755.
_GATED_COMMAND_MIRRORS = frozenset(
    {
        "spec",
        "plan",
        "build",
        "test",
        "ship",
        "checkpoint",
        "pr-review",
        "retro",
        "sync",
    }
)
_GATED_SKILL_MIRRORS = frozenset(
    {
        "orphan-ref-validator",
        "review",
        "security-detection",
    }
)
_GATED_MIRRORS = _GATED_COMMAND_MIRRORS | _GATED_SKILL_MIRRORS


def _committed_bodies() -> list[tuple[str, str]]:
    return [
        (p.parent.name, p.read_text(encoding="utf-8"))
        for p in sorted(_COPILOT_SKILLS.glob("*/SKILL.md"))
        if p.parent.name in _GATED_MIRRORS
    ]


def test_committed_skills_have_no_arguments_token() -> None:
    """No shipped Copilot skill body may carry the unresolved `$ARGUMENTS`."""
    offenders = [name for name, body in _committed_bodies() if "$ARGUMENTS" in body]
    assert not offenders, f"$ARGUMENTS present in: {offenders}"


def test_committed_skills_have_no_bare_claude_include() -> None:
    """No shipped Copilot skill body may carry a bare `@CLAUDE.md` include line."""
    offenders = [
        name
        for name, body in _committed_bodies()
        if any(line.strip() == "@CLAUDE.md" for line in body.splitlines())
    ]
    assert not offenders, f"bare @CLAUDE.md include present in: {offenders}"


def test_committed_skills_with_calls_have_appendix() -> None:
    """Any shipped Copilot skill with inline Skill()/Task() carries the appendix."""
    missing = [
        name
        for name, body in _committed_bodies()
        if ('Skill(skill="' in body or "Task(subagent_type=" in body)
        and "## Copilot CLI invocation reference" not in body
    ]
    assert not missing, f"invocation appendix missing in: {missing}"


def test_gated_skill_mirrors_are_committed() -> None:
    """The three clean skill-tree mirrors this branch ships exist on disk."""
    committed = {name for name, _ in _committed_bodies()}
    missing = _GATED_SKILL_MIRRORS - committed
    assert not missing, f"expected committed skill-mirrors absent: {missing}"


def test_deferred_skill_mirrors_excluded_from_gate() -> None:
    """The two #2755-deferred mirrors are not asserted by the committed gate."""
    deferred = {"cva-analysis", "slashcommandcreator"}
    assert not (deferred & _GATED_MIRRORS), (
        "cva-analysis/slashcommandcreator carry pre-existing SkillForge defects "
        "(#2755); their translated output is not committed, so the gate must "
        "not assert over them"
    )
