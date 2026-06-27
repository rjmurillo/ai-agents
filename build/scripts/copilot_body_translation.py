"""Translate Claude Code conventions in a skill body for GitHub Copilot CLI.

Issue #2743. Both the command-to-skill bridge (`generate_commands.py`) and
the skill-tree mirror (`generate_skills.py`) emit `SKILL.md` bodies into the
Copilot CLI plugin tree (`src/copilot-cli/skills/`). Those bodies are copied
from `.claude/commands/*.md` and `.claude/skills/*/SKILL.md`, which use
Claude Code conventions that Copilot CLI does NOT resolve.

Runtime contract verified empirically against GitHub Copilot CLI 1.0.66-1
(2026-06-27, recorded in Serena memory
`decisions/decision-copilot-cli-skill-task-arguments-claude-import-contract`):

  - `$ARGUMENTS`               -> returns UNRECOGNIZED-TOKEN (no argument vector)
  - `@CLAUDE.md` first line    -> treated as LITERAL-TEXT (not auto-inlined)
  - `Skill(skill="X")`         -> NOT callable; real tool is `skill` (param `skill`)
  - `Task(subagent_type="Y")`  -> NOT callable; real tool is `task`
                                  (param `agent_type`, persona `<plugin>:Y`)

The translation applies three transforms:

  1. `@file` includes  -> a Copilot note (instructions load via the plugin tree).
  2. `$ARGUMENTS`       -> a conversation instruction (no argument vector).
  3. an appended invocation reference mapping inline `Skill()`/`Task()` calls
     to the Copilot `skill`/`task` tools.

Transforms 1 and 2 run inline. Transform 3 is appended rather than rewritten
in place: the inline calls live inside blocks that
`tests/commands/test_spec_step0.py::test_step{0,9}_block_identical` assert
byte-identical between `.claude/commands/spec.md` and the Copilot SKILL.md.
Appending keeps those parity blocks intact.
"""

from __future__ import annotations

import re
from pathlib import Path

_PLUGIN_MANIFEST_RELATIVE = Path(".claude-plugin") / "plugin.json"
_DEFAULT_PLUGIN_NAME = "project-toolkit"

# Match the call's first keyword argument value, tolerating additional
# arguments before the closing paren (for example
# `Task(subagent_type="architect", prompt="...")`). The capture is only the
# skill/persona name; trailing args are ignored for the mapping.
_SKILL_CALL_RE = re.compile(r'Skill\(skill="([^"]+)"')
_TASK_CALL_RE = re.compile(r'Task\(subagent_type="([^"]+)"')
_INCLUDE_LINE_RE = re.compile(r"^@([A-Za-z0-9_.\-/]+)\s*$", re.MULTILINE)
_ARGUMENTS_TOKEN = "$ARGUMENTS"

_FRONTMATTER_RE = re.compile(r"\A(---\n.*?\n---\n)(.*)\Z", re.DOTALL)


def resolve_plugin_name(skills_output_dir: Path) -> str:
    """Read the Copilot plugin name from the output tree's plugin.json.

    The plugin name namespaces `task` agent_types as `<plugin>:<persona>`
    under Copilot CLI. Single-source it from the manifest that ships in the
    same plugin tree the skills land in. Falls back to the known default when
    the manifest is absent (for example, a synthetic test output tree).

    ``skills_output_dir`` is the ``.../skills`` directory; the manifest sits at
    ``.../.claude-plugin/plugin.json`` (one level up).
    """
    manifest = skills_output_dir.parent / _PLUGIN_MANIFEST_RELATIVE
    if not manifest.is_file():
        return _DEFAULT_PLUGIN_NAME
    match = re.search(r'"name"\s*:\s*"([^"]+)"', manifest.read_text(encoding="utf-8"))
    return match.group(1) if match else _DEFAULT_PLUGIN_NAME


def _translate_includes(body: str) -> str:
    """Replace Claude ``@file`` standalone include lines with a Copilot note."""

    def _replace(match: re.Match[str]) -> str:
        target = match.group(1)
        return (
            f"<!-- Copilot CLI: project instructions ({target}) load via the "
            "plugin instructions tree; no include directive needed. -->"
        )

    return _INCLUDE_LINE_RE.sub(_replace, body)


def _translate_arguments(body: str) -> str:
    """Replace the ``$ARGUMENTS`` token with a Copilot-safe instruction."""
    if _ARGUMENTS_TOKEN not in body:
        return body
    replacement = (
        "the problem statement from the conversation (under Copilot CLI the "
        "skill tool takes no argument vector, so state it in your message)"
    )
    return body.replace(_ARGUMENTS_TOKEN, replacement)


def _build_invocation_appendix(body: str, plugin_name: str) -> str:
    """Build the Copilot CLI invocation-reference appendix for a body.

    Returns an empty string when the body has no inline `Skill()`/`Task()`.
    """
    skills = sorted({m.group(1) for m in _SKILL_CALL_RE.finditer(body)})
    agents = sorted({m.group(1) for m in _TASK_CALL_RE.finditer(body)})
    if not skills and not agents:
        return ""

    lines = [
        "",
        "## Copilot CLI invocation reference",
        "",
        "This skill body uses Claude Code call syntax. Under GitHub Copilot "
        "CLI, translate as follows (verified against Copilot CLI 1.0.66-1).",
        "",
    ]
    if skills:
        lines += ["### Sub-skill calls", ""]
        lines += ["| Claude Code syntax | Copilot CLI equivalent |", "| --- | --- |"]
        lines += [
            f'| `Skill(skill="{name}")` | `skill` tool, `skill: "{name}"` |'
            for name in skills
        ]
        lines.append("")
    if agents:
        lines += ["### Sub-agent calls", ""]
        lines += ["| Claude Code syntax | Copilot CLI equivalent |", "| --- | --- |"]
        lines += [
            f'| `Task(subagent_type="{name}")` | `task` tool, '
            f'`agent_type: "{plugin_name}:{name}"` |'
            for name in agents
        ]
        lines.append("")
    lines.append(
        "If a referenced skill or agent is unavailable in the Copilot CLI "
        "environment, perform that step inline and note the reduced coverage."
    )
    return "\n".join(lines)


def translate_body(body: str, skills_output_dir: Path) -> str:
    """Translate Claude Code conventions in a SKILL.md body for Copilot CLI.

    ``skills_output_dir`` is the ``.../skills`` directory the body lands in;
    it locates the plugin manifest for the agent_type namespace.
    """
    translated = _translate_includes(body)
    translated = _translate_arguments(translated)
    plugin_name = resolve_plugin_name(skills_output_dir)
    appendix = _build_invocation_appendix(translated, plugin_name)
    if not appendix:
        return translated
    separator = "" if translated.endswith("\n") else "\n"
    return f"{translated}{separator}{appendix}\n"


def translate_skill_file(content: str, skills_output_dir: Path) -> str:
    """Translate a full SKILL.md (frontmatter + body), preserving frontmatter.

    Frontmatter is left untouched; only the body after the closing `---`
    fence is translated. When no frontmatter is present, the whole content is
    treated as body.
    """
    match = _FRONTMATTER_RE.match(content)
    if match is None:
        return translate_body(content, skills_output_dir)
    frontmatter, body = match.group(1), match.group(2)
    return frontmatter + translate_body(body, skills_output_dir)
