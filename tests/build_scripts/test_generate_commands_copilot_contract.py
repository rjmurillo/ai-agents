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

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "build"))

import copilot_body_translation  # noqa: E402

_COPILOT_SKILLS = REPO_ROOT / "src" / "copilot-cli" / "skills"
_FENCED_CODE_BLOCK_RE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE_SPAN_RE = re.compile(r"`+[^`\n]*`+")

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


def test_arguments_token_preserved_inside_inline_code_span(tmp_path: Path) -> None:
    """Literal authoring docs keep `$ARGUMENTS` inside inline code spans."""
    body = "- Simple commands: use `$ARGUMENTS`\n"

    out = copilot_body_translation.translate_body(body, tmp_path)

    assert out == body


def test_arguments_token_preserved_inside_fenced_code_block(tmp_path: Path) -> None:
    """Literal slash-command examples keep `$ARGUMENTS` inside fenced code."""
    body = "```text\nUse $ARGUMENTS here.\n```\n"

    out = copilot_body_translation.translate_body(body, tmp_path)

    assert out == body


def test_arguments_token_translated_in_prose(tmp_path: Path) -> None:
    """Invocation contracts still translate prose `$ARGUMENTS` references."""
    body = "Spec: $ARGUMENTS\n"

    out = copilot_body_translation.translate_body(body, tmp_path)

    assert "$ARGUMENTS" not in out
    assert "the problem statement from the conversation" in out


def test_include_line_replaced_with_note(tmp_path: Path) -> None:
    """`@CLAUDE.md` standalone include becomes a Copilot note, not literal text."""
    out = copilot_body_translation.translate_body(_CLAUDE_BODY, tmp_path)
    assert "\n@CLAUDE.md\n" not in f"\n{out}"
    assert not out.startswith("@CLAUDE.md")
    assert "load via the plugin instructions tree" in out
    # Negative control: the raw body starts with the literal include.
    assert _CLAUDE_BODY.startswith("@CLAUDE.md")


def test_standalone_decorator_line_is_preserved(tmp_path: Path) -> None:
    """Standalone Python decorator lines are not Claude include directives."""
    body = "```python\n@dataclass\nclass Config:\n    pass\n```\n"

    out = copilot_body_translation.translate_body(body, tmp_path)

    assert out == body


def test_markdown_include_line_still_replaced(tmp_path: Path) -> None:
    """Markdown include directives remain the only translated @ lines."""
    body = "@CLAUDE.md\n"

    out = copilot_body_translation.translate_body(body, tmp_path)

    assert "@CLAUDE.md" not in out
    assert "load via the plugin instructions tree" in out


def test_skill_call_translated_inline(tmp_path: Path) -> None:
    """Every inline Skill() call becomes its Copilot `skill:` tool-input span."""
    out = copilot_body_translation.translate_body(_CLAUDE_BODY, tmp_path)
    assert '`skill: "chestertons-fence"`' in out
    assert 'Skill(skill=' not in out
    # The structural rework (#2743) drops the appended reference section.
    assert "## Copilot CLI invocation reference" not in out
    # Negative control: the raw body still carries the untranslated call.
    assert 'Skill(skill="chestertons-fence")' in _CLAUDE_BODY


def test_task_call_translated_with_plugin_namespace(tmp_path: Path) -> None:
    """Task() becomes the plugin-namespaced `agent_type:` tool-input span."""
    out = copilot_body_translation.translate_body(_CLAUDE_BODY, tmp_path)
    assert '`agent_type: "project-toolkit:critic"`' in out
    assert "Task(subagent_type=" not in out
    # Negative control: the raw body still carries the untranslated call.
    assert 'Task(subagent_type="critic")' in _CLAUDE_BODY


def test_inline_calls_translated_not_preserved(tmp_path: Path) -> None:
    """Calls are rewritten in place, not preserved (structural rework, #2743).

    The earlier design kept raw Skill()/Task() syntax in the body and appended
    a reference table to protect the Step 0 / Step 9 byte-parity tests. The
    rework translates each call where it sits, and those parity tests now apply
    the same translation to the source block before comparing, so no raw
    Claude call syntax ships in the Copilot mirror.
    """
    out = copilot_body_translation.translate_body(_CLAUDE_BODY, tmp_path)
    assert 'Skill(skill="chestertons-fence")' not in out
    assert 'Task(subagent_type="critic")' not in out
    # Negative control: the raw body still carries both calls.
    assert 'Skill(skill="chestertons-fence")' in _CLAUDE_BODY
    assert 'Task(subagent_type="critic")' in _CLAUDE_BODY


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
    """translate_skill_file passes frontmatter through, translates the body.

    Every key but `allowed-tools` is untouched; that one is respelled by the
    MCP-name transform covered below.
    """
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
    assert '`agent_type: "project-toolkit:critic"`' in out
    assert "## Copilot CLI invocation reference" not in out


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
    assert '`agent_type: "project-toolkit:critic"`' in out
    assert "## Copilot CLI invocation reference" not in out


def test_allowed_tools_mcp_names_respelled_for_copilot(tmp_path: Path) -> None:
    """`mcp__github__*` names nothing Copilot exposes; it spells it `github/*`.

    Copied across unchanged, the grant is inert and every MCP-routed step in
    the mirror fails for a reason that has nothing to do with the PR
    (Copilot review on PR #5509). `templates/toolsets.yaml` is the canonical
    spelling: `github/pull_request_read`, `serena/*`.
    """
    content = (
        "---\n"
        "name: demo\n"
        "allowed-tools: Bash, Read, mcp__github__*, mcp__serena__find_symbol\n"
        "---\n"
        "body\n"
    )

    out = copilot_body_translation.translate_skill_file(content, tmp_path)

    assert "allowed-tools: Bash, Read, github/*, serena/find_symbol\n" in out
    assert "mcp__" not in out


def test_allowed_tools_respelling_handles_the_yaml_list_form(tmp_path: Path) -> None:
    """The key also takes a block list, which a single-line pattern would miss."""
    content = (
        "---\n"
        "allowed-tools:\n"
        "  - Read\n"
        "  - mcp__github__issue_read\n"
        "---\n"
        "body\n"
    )

    out = copilot_body_translation.translate_skill_file(content, tmp_path)

    assert "  - github/issue_read\n" in out


def test_the_allowed_tools_match_stops_at_the_closing_fence(tmp_path: Path) -> None:
    """Control: the continuation class must not swallow `---` and keep going.

    A leading `-` in that class matched the closing fence, and from there every
    following list line, so a call on a whole document respelled body prose and
    broke the one-key promise. The body line here starts with `-` and shares no
    blank line with the fence, which is the shape that reproduced it.
    """
    document = (
        "---\n"
        "allowed-tools:\n"
        "  - mcp__github__issue_read\n"
        "---\n"
        "- Claude Code spells it mcp__github__get_me.\n"
    )

    out = copilot_body_translation.translate_allowed_tools(document)

    assert "  - github/issue_read\n" in out
    assert "- Claude Code spells it mcp__github__get_me.\n" in out


def test_mcp_names_outside_allowed_tools_are_left_alone(tmp_path: Path) -> None:
    """Control: the transform must not rewrite every occurrence of the token.

    Body prose and the `description` deliberately contrast the two spellings so
    a reader on either harness knows which one is theirs. Rewriting those turns
    a per-harness table into two identical rows, and no assertion above would
    fail. Without this case the transform could drop its `allowed-tools` anchor
    and still pass.
    """
    content = (
        "---\n"
        "description: routes through mcp__github__get_me\n"
        "allowed-tools: Read\n"
        "---\n"
        "Claude Code spells it mcp__github__pull_request_read.\n"
    )

    out = copilot_body_translation.translate_skill_file(content, tmp_path)

    assert "description: routes through mcp__github__get_me\n" in out
    assert "Claude Code spells it mcp__github__pull_request_read." in out


def test_committed_skill_frontmatter_grants_no_claude_mcp_names() -> None:
    """Gate the shipped artifact, not only the generator.

    A hand-edit or a merge can put the Claude spelling back into a committed
    mirror without the generator ever running (`.claude/rules/generated-artifacts.md`
    MUST 3). Frontmatter only: the bodies carry the per-harness tables.
    """
    offenders = []
    for path in sorted(_COPILOT_SKILLS.glob("*/SKILL.md")):
        content = path.read_text(encoding="utf-8")
        match = copilot_body_translation._FRONTMATTER_RE.match(content)
        if match is None:
            continue
        if "mcp__" in match.group(1):
            offenders.append(path.parent.name)
    assert not offenders, f"Claude MCP tool names in Copilot frontmatter: {offenders}"


def test_translate_skill_file_matches_call_with_extra_args(tmp_path: Path) -> None:
    """Task()/Skill() calls with trailing args (e.g. prompt=) are still mapped."""
    body = 'Task(subagent_type="architect", prompt="Create ADR")\n'
    out = copilot_body_translation.translate_body(body, tmp_path)
    assert '`agent_type: "project-toolkit:architect"`' in out
    assert 'with prompt "Create ADR"' in out
    assert "Task(subagent_type=" not in out


def test_prompt_value_with_escaped_quotes_not_truncated(tmp_path: Path) -> None:
    """A prompt value containing same-type escaped quotes must survive whole.

    Regression for the lazy `.*?` extraction that stopped at the first escaped
    quote, silently truncating the rendered prompt. The value carries two
    escaped double-quotes inside a double-quoted argument.
    """
    body = 'Task(subagent_type="critic", prompt="Write \\"ADR-099\\" now")\n'
    out = copilot_body_translation.translate_body(body, tmp_path)
    assert 'with prompt "Write \\"ADR-099\\" now"' in out
    assert "Task(subagent_type=" not in out
    # Negative control: the buggy lazy `.*?` extraction truncated the value at
    # the first escaped quote, dropping everything after it. Prove the tail of
    # the prompt (which only exists past that escaped quote) survived.
    assert "ADR-099" in out
    assert "now" in out


def test_inline_calls_allow_spaces_and_single_quotes(tmp_path: Path) -> None:
    """Formatted Skill()/Task() calls (spaces, single quotes) still translate."""
    body = "Skill( skill = 'memory')\nTask( subagent_type = 'critic')\n"
    out = copilot_body_translation.translate_body(body, tmp_path)
    assert '`skill: "memory"`' in out
    assert '`agent_type: "project-toolkit:critic"`' in out
    assert "Skill(" not in out
    assert "Task(" not in out


# Committed-artifact gate ----------------------------------------------------


# The committed-artifact gate covers every translated Copilot SKILL.md this
# branch ships clean:
#   1. The nine lifecycle command-mirrors at .claude/commands/<name>.md mirrored
#      into src/copilot-cli/skills/<name>/SKILL.md.
#   2. The five skill-tree mirrors whose SOURCE skills pass SkillForge after
#      translation: cva-analysis, orphan-ref-validator, review,
#      security-detection, slashcommandcreator.
# cva-analysis and slashcommandcreator were deferred under #2755 while their
# source skills carried SkillForge defects. #2762 fixed the sources and #2777
# removed the staleness deferral, so their translated mirrors are now committed
# and gated like every other skill-tree mirror.
# Refs #2743. Refs #2755. Refs #2762. Refs #2777.
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
        "cva-analysis",
        "orphan-ref-validator",
        "review",
        "security-detection",
        "slashcommandcreator",
    }
)
_GATED_MIRRORS = _GATED_COMMAND_MIRRORS | _GATED_SKILL_MIRRORS


def _committed_bodies() -> list[tuple[str, str]]:
    return [
        (p.parent.name, p.read_text(encoding="utf-8"))
        for p in sorted(_COPILOT_SKILLS.glob("*/SKILL.md"))
        if p.parent.name in _GATED_MIRRORS
    ]


def _contains_untranslated_arguments_token(body: str) -> bool:
    body_without_fences = _FENCED_CODE_BLOCK_RE.sub("", body)
    body_without_code_spans = _INLINE_CODE_SPAN_RE.sub("", body_without_fences)
    return "$ARGUMENTS" in body_without_code_spans


def test_orphan_ref_validator_uses_platform_neutral_invocation_wording() -> None:
    """The orphan-ref-validator prose must not claim one syntax works everywhere."""
    source = REPO_ROOT / ".claude" / "skills" / "orphan-ref-validator" / "SKILL.md"
    mirror = _COPILOT_SKILLS / "orphan-ref-validator" / "SKILL.md"
    expected = (
        "The `/build` gate invokes this skill through whichever invocation form "
        "its platform provides; each platform mirror runs its own copy of `scan.py`."
    )

    for path in (source, mirror):
        body = path.read_text(encoding="utf-8")
        assert expected in body, f"missing platform-neutral wording in {path}"
        assert "invocation form is platform-agnostic" not in body


def test_committed_skills_have_no_untranslated_arguments_token() -> None:
    """No shipped Copilot skill body may carry unresolved `$ARGUMENTS` prose."""
    offenders = [
        name
        for name, body in _committed_bodies()
        if _contains_untranslated_arguments_token(body)
    ]
    assert not offenders, f"$ARGUMENTS present in: {offenders}"


def test_committed_skills_have_no_bare_claude_include() -> None:
    """No shipped Copilot skill body may carry a bare `@CLAUDE.md` include line."""
    offenders = [
        name
        for name, body in _committed_bodies()
        if any(line.strip() == "@CLAUDE.md" for line in body.splitlines())
    ]
    assert not offenders, f"bare @CLAUDE.md include present in: {offenders}"


def test_committed_skills_have_no_untranslated_calls() -> None:
    """A shipped Copilot skill body must be a fixed point of translation.

    Re-translating an already-translated body is a no-op. A substring check for
    the exact `Skill(skill="` / `Task(subagent_type=` forms misses calls in any
    other formatting the translator supports (extra spaces, single quotes).
    Re-running the translator catches every residual translatable call: if one
    survived, translation would rewrite the body and it would differ. Prose
    mentions such as `Skill(...)` carry no valid argument, render to nothing, and
    are left unchanged, so they do not trip this gate.
    """
    offenders = [
        name
        for name, body in _committed_bodies()
        if copilot_body_translation.translate_skill_file(body, _COPILOT_SKILLS)
        != body
    ]
    assert not offenders, f"untranslated Claude call present in: {offenders}"


def test_gated_skill_mirrors_are_committed() -> None:
    """The five clean skill-tree mirrors this branch ships exist on disk."""
    committed = {name for name, _ in _committed_bodies()}
    missing = _GATED_SKILL_MIRRORS - committed
    assert not missing, f"expected committed skill-mirrors absent: {missing}"


def test_formerly_deferred_skill_mirrors_are_now_gated() -> None:
    """The #2755-deferred mirrors are gated again after #2762/#2777.

    #2762 fixed the cva-analysis and slashcommandcreator source skills, and
    #2777 removed the STALENESS_DEFERRALS exemption. Their translated mirrors
    are now committed, so the committed gate must assert over them.
    """
    formerly_deferred = {"cva-analysis", "slashcommandcreator"}
    assert formerly_deferred <= _GATED_MIRRORS, (
        "cva-analysis/slashcommandcreator are fixed (#2762) and no longer "
        "deferred (#2777); their committed translated mirrors must be gated"
    )
