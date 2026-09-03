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
  - `mcp__github__<op>`        -> not a Copilot tool name; Copilot spells the
                                  same server `github/<op>` (`templates/toolsets.yaml`)

The translation applies four transforms, all in place:

  1. `@file` includes -> a Copilot note (instructions load via the plugin tree).
  2. `$ARGUMENTS`      -> a conversation instruction (no argument vector).
  3. `Skill()`/`Task()` calls -> the Copilot tool-input span they map to:
     `Skill(skill="X")`        -> `` `skill: "X"` ``
     `Task(subagent_type="Y")` -> `` `agent_type: "<plugin>:Y"` ``
     A `prompt="Z"` argument is preserved as ` with prompt "Z"`.
  4. `allowed-tools` frontmatter -> MCP names respelled for Copilot:
     `mcp__github__*` -> `github/*`, `mcp__serena__find_symbol` ->
     `serena/find_symbol`. Transforms 1 to 3 skip frontmatter, so before this
     a Claude-only namespace was copied verbatim into the Copilot mirror and
     the grant named nothing the harness exposes (Copilot review on PR #5509).

Transform 3 rewrites each call where it sits (structural rework, #2743). The
earlier design appended a reference table to sidestep the Step 0 / Step 9
byte-parity tests in `tests/commands/test_spec_step0.py`; that indirection is
gone. Those parity tests now apply this same translation to the source block
before comparing, so the mirror is a pure in-place translation of the source
with no appended section. Transform 3 runs over the whole body, fenced code
included, because three skills (security-detection, slashcommandcreator,
cva-analysis) carry their only calls inside fenced example blocks.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path

_PLUGIN_MANIFEST_RELATIVE = Path(".claude-plugin") / "plugin.json"
_DEFAULT_PLUGIN_NAME = "project-toolkit"

_INCLUDE_LINE_RE = re.compile(r"^@([A-Za-z0-9_.\-/]+\.md)\s*$", re.MULTILINE)
_ARGUMENTS_TOKEN = "$ARGUMENTS"
_FENCED_CODE_BLOCK_RE = re.compile(r"(```.*?```)", re.DOTALL)
_INLINE_CODE_SPAN_RE = re.compile(r"(`+[^`\n]*`+)")

_FRONTMATTER_RE = re.compile(r"\A(---\r?\n.*?\r?\n---\r?\n)(.*)\Z", re.DOTALL)

# The `allowed-tools` value, which may wrap onto continuation lines in a YAML
# block or list. Anchored at the key so no other frontmatter value is touched.
#
# The continuation class is indentation only. Allowing a leading `-` also
# matched the closing `---` fence, and from there every following list line, so
# a call on a whole document respelled the body too and broke the promise to
# touch one key. A YAML list under a key is indented, so nothing legitimate is
# lost (Copilot review on PR #5509).
_ALLOWED_TOOLS_LINE_RE = re.compile(
    r"^allowed-tools:.*(?:\n[ \t].*)*$", re.MULTILINE
)
# `mcp__<server>__<op>`; `<op>` is `*` for a whole-namespace grant.
_MCP_TOOL_NAME_RE = re.compile(r"mcp__([A-Za-z0-9_]+?)__([A-Za-z0-9_]+|\*)")

# Locate the start of a `Skill(` / `Task(` call. The matching close paren is
# found by a quote-aware balanced scan (a `prompt="..."` argument can contain
# parens), so this only anchors the opener.
_CALL_START_RE = re.compile(r"(Skill|Task)\(")
# Extract quoted argument values, escape-aware: a value may contain an escaped
# quote of the same type (`prompt="say \"hi\""`). Matches non-quote/non-backslash
# runs and `\.` escapes, mirroring the backslash handling in _find_matching_paren
# so value extraction never truncates at an escaped quote.
_QUOTED_VALUE = r"(?P<q>['\"])(?P<value>(?:(?!(?P=q))[^\\]|\\.)*)(?P=q)"
_SKILL_NAME_RE = re.compile(r"skill\s*=\s*" + _QUOTED_VALUE, re.DOTALL)
_TASK_NAME_RE = re.compile(r"subagent_type\s*=\s*" + _QUOTED_VALUE, re.DOTALL)
_PROMPT_ARG_RE = re.compile(r"prompt\s*=\s*" + _QUOTED_VALUE, re.DOTALL)


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
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _DEFAULT_PLUGIN_NAME
    name = data.get("name")
    return name if isinstance(name, str) and name else _DEFAULT_PLUGIN_NAME


def _translate_outside_fenced_code(
    body: str,
    translate_segment: Callable[[str], str],
) -> str:
    parts = _FENCED_CODE_BLOCK_RE.split(body)
    for index in range(0, len(parts), 2):
        parts[index] = translate_segment(parts[index])
    return "".join(parts)


def _translate_includes(body: str) -> str:
    """Replace Claude ``@file`` standalone include lines with a Copilot note."""

    def _replace(match: re.Match[str]) -> str:
        target = match.group(1)
        return (
            f"<!-- Copilot CLI: project instructions ({target}) load via the "
            "plugin instructions tree; no include directive needed. -->"
        )

    return _translate_outside_fenced_code(
        body,
        lambda segment: _INCLUDE_LINE_RE.sub(_replace, segment),
    )


def _replace_arguments_outside_inline_code(line: str, replacement: str) -> str:
    parts = _INLINE_CODE_SPAN_RE.split(line)
    for index, part in enumerate(parts):
        if not _INLINE_CODE_SPAN_RE.fullmatch(part):
            parts[index] = part.replace(_ARGUMENTS_TOKEN, replacement)
    return "".join(parts)


def _replace_arguments_in_segment(segment: str, replacement: str) -> str:
    lines = segment.splitlines(keepends=True)
    return "".join(
        _replace_arguments_outside_inline_code(line, replacement) for line in lines
    )


def _translate_arguments(body: str) -> str:
    """Replace the ``$ARGUMENTS`` token with a Copilot-safe instruction."""
    if _ARGUMENTS_TOKEN not in body:
        return body
    replacement = (
        "the problem statement from the conversation (under Copilot CLI the "
        "skill tool takes no argument vector, so state it in your message)"
    )
    return _translate_outside_fenced_code(
        body,
        lambda segment: _replace_arguments_in_segment(segment, replacement),
    )


def _find_matching_paren(text: str, open_index: int) -> int:
    """Return the index of the ``)`` that closes the ``(`` at ``open_index``.

    Quote-aware: parens inside single- or double-quoted argument strings do
    not change the depth. Returns -1 when the call is unbalanced.
    """
    depth = 0
    quote: str | None = None
    index = open_index
    length = len(text)
    while index < length:
        char = text[index]
        if quote is not None:
            if char == "\\":
                index += 2
                continue
            if char == quote:
                quote = None
        elif char in ("'", '"'):
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return -1


def _render_invocation(kind: str, args: str, plugin_name: str) -> str | None:
    """Render the Copilot tool-input span for one call, or None if unparseable."""
    if kind == "Skill":
        name = _SKILL_NAME_RE.search(args)
        if name is None:
            return None
        return f'`skill: "{name.group("value")}"`'
    name = _TASK_NAME_RE.search(args)
    if name is None:
        return None
    rendered = f'`agent_type: "{plugin_name}:{name.group("value")}"`'
    prompt = _PROMPT_ARG_RE.search(args)
    if prompt is not None:
        rendered += f' with prompt "{prompt.group("value")}"'
    return rendered


def _translate_invocations(body: str, plugin_name: str) -> str:
    """Rewrite each ``Skill()``/``Task()`` call as its Copilot tool-input span.

    A call already wrapped in backticks (`` `Skill(skill="X")` ``) has those
    wrapping backticks absorbed, so the result is a single clean code span.
    """
    out: list[str] = []
    cursor = 0
    length = len(body)
    for match in _CALL_START_RE.finditer(body):
        call_start = match.start()
        if call_start < cursor:
            continue
        open_index = match.end() - 1
        close_index = _find_matching_paren(body, open_index)
        if close_index == -1:
            continue
        rendered = _render_invocation(
            match.group(1), body[open_index + 1 : close_index], plugin_name
        )
        if rendered is None:
            continue
        call_end = close_index + 1
        if (
            call_start - 1 >= cursor
            and body[call_start - 1] == "`"
            and call_end < length
            and body[call_end] == "`"
        ):
            call_start -= 1
            call_end += 1
        out.append(body[cursor:call_start])
        out.append(rendered)
        cursor = call_end
    out.append(body[cursor:])
    return "".join(out)


def translate_body(body: str, skills_output_dir: Path) -> str:
    """Translate Claude Code conventions in a SKILL.md body for Copilot CLI.

    ``skills_output_dir`` is the ``.../skills`` directory the body lands in;
    it locates the plugin manifest for the agent_type namespace.
    """
    translated = _translate_includes(body)
    translated = _translate_arguments(translated)
    plugin_name = resolve_plugin_name(skills_output_dir)
    return _translate_invocations(translated, plugin_name)


def respell_mcp_tool_names(value: str) -> str:
    """Rewrite `mcp__<server>__<op>` to the Copilot CLI spelling `<server>/<op>`.

    Claude Code names an MCP tool `mcp__github__pull_request_read`; Copilot CLI
    names the same tool `github/pull_request_read`, which
    `templates/toolsets.yaml` uses throughout (`github/*`, `serena/*`). A grant
    copied across unchanged names nothing the harness exposes, so the tool is
    not granted and any workflow depending on it is inert in the mirror.

    Takes a tool-list value, not a document. The same token appears in body
    prose that deliberately contrasts the two spellings, and rewriting it there
    would turn a per-harness table into two identical rows.
    """
    return _MCP_TOOL_NAME_RE.sub(r"\1/\2", value)


def translate_allowed_tools(frontmatter: str) -> str:
    """Apply :func:`respell_mcp_tool_names` to the `allowed-tools` value only.

    `generate_skills.py` mirrors a whole `SKILL.md` as text, so its frontmatter
    arrives as a string. `generate_commands.py` builds frontmatter as a dict and
    calls the helper above on the value directly; both paths have to respell or
    only half the Copilot tree is fixed.
    """
    return _ALLOWED_TOOLS_LINE_RE.sub(
        lambda line: respell_mcp_tool_names(line.group(0)),
        frontmatter,
    )


def translate_skill_file(content: str, skills_output_dir: Path) -> str:
    """Translate a full SKILL.md (frontmatter + body), preserving frontmatter.

    Only the `allowed-tools` line of the frontmatter is rewritten (transform 4);
    every other key is passed through. When no frontmatter is present, the
    whole content is treated as body.
    """
    match = _FRONTMATTER_RE.match(content)
    if match is None:
        return translate_body(content, skills_output_dir)
    frontmatter, body = match.group(1), match.group(2)
    return translate_allowed_tools(frontmatter) + translate_body(body, skills_output_dir)
