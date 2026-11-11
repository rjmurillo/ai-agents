#!/usr/bin/env python3
"""Copy ``src/claude/agents/`` into a host plugin tree with a frontmatter allow-list.

ADR-115 Decision 2. The Cursor plugin tree reads agents from ``agents/*.md``
with frontmatter ``name``, ``description``, ``model``, ``readonly`` and
``is_background`` (https://cursor.com/docs/context/subagents). The Claude agent
files carry more keys (``tools``, ``metadata``, ``argument-hint``, ``model``,
and others) that Cursor does not document, so this copy keeps only the keys the
platform stanza lists.

A platform opts in by setting ``artifacts.agents.frontmatterKeep``. The
Copilot-family generator (``build/generate_agents.py``) skips such a platform,
because it renders from ``templates/agents/`` and this module renders from the
already-compiled Claude plugin tree.

Stanza keys (all under ``artifacts.agents``):

``sourceDir``         plugin-tree agent directory to read (``src/claude/agents``)
``outputDir``         directory to write (``src/cursor/agents``)
``frontmatterKeep``   top-level frontmatter keys to keep, in output order
``deriveReadonly``    when true, emit ``readonly: true`` for an agent whose
                      ``tools`` (list or comma-separated string) names only
                      read-only tools, and do not ship an agent whose ``tools``
                      is restricted (including empty) but not all read-only
``excludeFilenames``  source file names to skip
``skipToolRestricted`` when true, do not ship an agent whose frontmatter declares
                      ``tools`` (list or comma string), and append a paragraph to
                      every shipped body naming the agents left out (Codex agent
                      files cannot restrict tools, ADR-115 Decision 7). Requires
                      ``frontmatterKeep``; excludes ``deriveReadonly: true``.
``outputFormat``      ``markdown`` (default) or ``codex-toml``. ``codex-toml`` writes
                      ``<stem>.toml`` with the keys ``name``, ``description`` and
                      ``developer_instructions`` (the body). ``frontmatterKeep`` must
                      be exactly ``[name, description]`` for it.
``bodyReplace``       map of agent file name to ``{from: to}`` literal edits to its body
                      (issue #7226). Cursor ships no ``security`` agent, so a
                      line that hands work to one is reworded for Cursor. Each
                      ``from`` must occur exactly once in its file, and each
                      ``file`` must exist, so a stale entry fails the build.

``readonly`` is derived, never guessed: an agent without a ``tools`` list gets
no ``readonly`` key (it is unrestricted in Claude too). Cursor documents no
tool allow-list for subagents, so ``readonly: true`` is the only tool
restriction it can carry. ADR-115 Decision 3: an agent whose ``tools`` list is
non-empty but not all read-only has a restriction ``readonly`` cannot express,
and copying it would hand it every tool, shell included. With
``deriveReadonly`` on, such an agent is not emitted, a skip line names it, and
the prune step removes a copy generated earlier (``--check`` reports it as
drift).

Different from ``generate_agents.py``: no handoff or memory-prefix rewrite and
no model pin. ``model`` is not in the keep list, so Cursor's default
(``inherit``) applies, and ADR-080's pin rules do not reach this tree.
"""

from __future__ import annotations

import functools
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

_SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPT_DIR))
sys.path.insert(0, str(_SCRIPT_DIR.parent))

from agent_capabilities import load_mcp_table, wildcard_grants  # noqa: E402
from atomic_write import publish_bytes_preserving_mode  # noqa: E402
from generate_agents_common import read_yaml_frontmatter  # noqa: E402
from regen_guard import detect_reason as regen_detect_reason  # noqa: E402
from yaml_loader import ConfigError, load_platform_config, validate_relative_path  # noqa: E402

KEEP_KEY = "frontmatterKeep"
REPLACE_KEY = "bodyReplace"
SKIP_RESTRICTED_KEY = "skipToolRestricted"
FORMAT_KEY = "outputFormat"
FORMAT_MARKDOWN = "markdown"
FORMAT_CODEX_TOML = "codex-toml"
_FORMATS = (FORMAT_MARKDOWN, FORMAT_CODEX_TOML)
_CODEX_KEEP = ["name", "description"]
_TOML_SUFFIX = ".toml"
_TOML_ESCAPES = {
    "\\": "\\\\",
    '"': '\\"',
    "\b": "\\b",
    "\t": "\\t",
    "\n": "\\n",
    "\f": "\\f",
    "\r": "\\r",
}
_READONLY_KEY = "readonly"
_SOURCE_SUFFIX = ".md"
_DEFAULT_EXCLUDES = ("AGENTS.md", "CLAUDE.md")
_READONLY_TOOLS = frozenset({"Read", "Glob", "Grep", "WebSearch", "WebFetch", "ToolSearch"})
# An MCP tool name is `mcp__<server>__<words>`, the words joined by `_`. It is
# read-only when a read verb leads the words (`get_file_contents`) or the last
# word is `read` (`issue_read`), and no word names a mutation (`find_and_replace`,
# `get_and_run`). `run` is a noun in `get_workflow_run`, so it is not a mutating
# word; a compound name (`and`, `then`) is rejected instead. `query` is not a
# read word: `mcp__db__query` can run a write. `resolve` and `ask` can lead a
# state change (`resolve_review_thread`), so only the exact names in
# _READ_NAMES earn readonly through them.
# A server-level wildcard (`mcp__context7__*`, ADR-107) is read-only only when
# `templates/agent-mcp-servers.yaml` lets that server be granted whole. A
# wildcard for any other server (`mcp__github__*`, `mcp__serena__*`) can carry
# write or shell tools, so it never earns `readonly: true`.
# An unfamiliar name matches none of these and never earns `readonly: true`.
_READ_WORDS = frozenset({"get", "list", "read", "find", "search", "initial"})
_READ_NAMES = frozenset({"resolve_library_id"})
_COMPOUND_WORDS = frozenset({"and", "or", "then"})
_MUTATING_WORDS = frozenset(
    {
        "write", "edit", "create", "update", "delete", "add", "merge", "push", "replace",
        "insert", "rename", "remove", "apply", "move", "fork",
        "exec", "execute", "send", "post", "set", "close", "dispatch",
    }
)  # fmt: skip


class AgentCopyError(Exception):
    """A platform stanza or a source agent file is unusable."""


@dataclass
class AgentCopyResult:
    """Outcome of one copy run."""

    inputs: int = 0
    written: int = 0
    drift: list[str] = field(default_factory=list)
    pruned: int = 0
    skipped: list[str] = field(default_factory=list)


def uses_agent_tree_copy(stanza: object) -> bool:
    """True when an ``artifacts.agents`` stanza opts in to this copy."""
    return isinstance(stanza, dict) and KEEP_KEY in stanza


@functools.cache
def _readonly_wildcards() -> frozenset[str]:
    """Return the ``<prefix>__*`` grants of the servers the MCP table marks safe whole."""
    grants: frozenset[str] = wildcard_grants(load_mcp_table(_SCRIPT_DIR.parents[1]))
    return grants


def is_readonly_tool(tool: object) -> bool:
    """True when ``tool`` names a tool that changes no state."""
    if not isinstance(tool, str):
        return False
    if tool in _READONLY_TOOLS:
        return True
    parts = tool.split("__")
    if len(parts) < 3 or parts[0] != "mcp":
        return False
    if parts[-1] == "*":
        return tool in _readonly_wildcards()
    words = parts[-1].split("_")
    if any(word in _MUTATING_WORDS or word in _COMPOUND_WORDS for word in words):
        return False
    return parts[-1] in _READ_NAMES or words[0] in _READ_WORDS or words[-1] == "read"


def declared_tools(frontmatter: dict[str, object]) -> list[object] | None:
    """The agent's ``tools`` as a list, or ``None`` when it declares none.

    Claude Code accepts a YAML list or a comma-separated string
    (``tools: Read, Write``, see ``generate_agents_common.py``); both are
    restrictions. Any other non-null type is an error, so the build fails
    instead of shipping an unrestricted agent.
    """
    tools = frontmatter.get("tools")
    if tools is None:
        return None
    if isinstance(tools, list):
        return list(tools)
    if isinstance(tools, str):
        return [name for name in (part.strip() for part in tools.split(",")) if name]
    raise AgentCopyError(
        f"`tools` must be a list or a comma-separated string, got {type(tools).__name__}"
    )


def derive_readonly(frontmatter: dict[str, object]) -> bool:
    """True when the agent declares tools and every one is read-only."""
    tools = declared_tools(frontmatter)
    return bool(tools) and all(is_readonly_tool(tool) for tool in tools or [])


def has_inexpressible_restriction(frontmatter: dict[str, object]) -> bool:
    """True when ``tools`` restricts the agent in a way ``readonly`` cannot express.

    An empty list or empty string restricts the agent to nothing. Cursor has no
    way to say that, so it fails closed like any other non-read-only list.
    """
    return declared_tools(frontmatter) is not None and not derive_readonly(frontmatter)


def parse_agent(text: str, source: str) -> tuple[dict[str, object], str]:
    """Return ``(frontmatter mapping, body)`` for one agent file."""
    parsed = read_yaml_frontmatter(text)
    if parsed is None:
        raise AgentCopyError(f"{source}: no frontmatter block")
    try:
        loaded = yaml.safe_load(parsed["frontmatter_raw"])
    except yaml.YAMLError as exc:
        raise AgentCopyError(f"{source}: unparseable frontmatter: {exc}") from exc
    if not isinstance(loaded, dict):
        raise AgentCopyError(f"{source}: frontmatter is not a mapping")
    return loaded, parsed["body"]


def toml_basic_string(value: str) -> str:
    """Return ``value`` as a single-line TOML 1.0 basic string, quotes included.

    Escapes ``\\``, ``"`` and the control characters U+0000-U+001F and U+007F
    (``\\b \\t \\n \\f \\r`` or ``\\uXXXX``). Every other character, including
    non-BMP ones such as emoji, stays raw UTF-8. ``json.dumps`` is not a
    substitute: it emits surrogate pairs (invalid TOML) and leaves U+007F raw.
    """
    out: list[str] = []
    for char in value:
        if char in _TOML_ESCAPES:
            out.append(_TOML_ESCAPES[char])
        elif ord(char) < 0x20 or ord(char) == 0x7F:
            out.append(f"\\u{ord(char):04X}")
        else:
            out.append(char)
    return '"' + "".join(out) + '"'


def _render_codex_toml(kept: dict[str, object], body: str, source: str) -> str:
    for key in _CODEX_KEEP:
        if not isinstance(kept.get(key), str):
            raise AgentCopyError(f"{source}: frontmatter `{key}` must be a string for codex-toml")
    return (
        f"name = {toml_basic_string(str(kept['name']))}\n"
        f"description = {toml_basic_string(str(kept['description']))}\n"
        f"developer_instructions = {toml_basic_string(body)}\n"
    )


def not_installed_paragraph(skipped_stems: list[str]) -> str:
    """Return the paragraph appended to each body when agents were left out.

    The list is the sorted skip list passed in, never a fixed set of names.
    """
    names = ", ".join(f"`{stem}`" for stem in sorted(skipped_stems))
    return (
        "\n\n## Agents not installed on this host\n\n"
        f"These agents are not installed on this host: {names}. "
        "When a step above hands work to one of them, do that step yourself "
        "in this session and say that you did.\n"
    )


def render_agent(
    text: str,
    keep: list[str],
    *,
    derive_readonly_flag: bool,
    source: str,
    body_edits: list[tuple[str, str]] | None = None,
    skip_tool_restricted: bool = False,
    appendix: str = "",
    output_format: str = FORMAT_MARKDOWN,
) -> str | None:
    """Return ``text`` with its frontmatter reduced to the ``keep`` keys.

    Returns ``None`` when the agent must not ship: ``derive_readonly_flag`` is
    set and the agent carries a tool restriction ``readonly`` cannot express
    (ADR-115 Decision 3), or ``skip_tool_restricted`` is set and the agent
    declares ``tools`` at all (ADR-115 Decision 7).

    ``body_edits`` are literal ``(from, to)`` edits applied to the body only, so
    text that also appears in the frontmatter can never be rewritten by mistake.
    ``appendix`` is added after the edits, to the end of the body.
    ``output_format`` ``codex-toml`` returns a TOML document, not markdown.
    """
    loaded, body = parse_agent(text, source)
    try:
        if skip_tool_restricted and declared_tools(loaded) is not None:
            return None
        if derive_readonly_flag and has_inexpressible_restriction(loaded):
            return None
    except AgentCopyError as exc:
        raise AgentCopyError(f"{source}: {exc}") from exc
    kept = {key: loaded[key] for key in keep if key in loaded}
    if derive_readonly_flag and derive_readonly(loaded):
        kept[_READONLY_KEY] = True
    if body_edits:
        body = apply_body_replacements(body, body_edits, source)
    if appendix:
        body = body.rstrip("\n") + appendix
    if output_format == FORMAT_CODEX_TOML:
        return _render_codex_toml(kept, body, source)
    dumped = yaml.safe_dump(
        kept, sort_keys=False, allow_unicode=True, default_flow_style=False, width=10**9
    )
    return f"---\n{dumped}---\n{body}"


def _body_replacements(stanza: dict[str, object]) -> dict[str, list[tuple[str, str]]]:
    """Return ``{file name: [(from, to), ...]}`` from the ``bodyReplace`` mapping."""
    raw = stanza.get(REPLACE_KEY, {})
    problem = f"`artifacts.agents.{REPLACE_KEY}` must map agent file names to {{from: to}} maps"
    if not isinstance(raw, dict):
        raise AgentCopyError(problem)
    edits: dict[str, list[tuple[str, str]]] = {}
    for file, pairs in raw.items():
        if not isinstance(file, str) or not isinstance(pairs, dict) or not pairs:
            raise AgentCopyError(problem)
        if not all(isinstance(k, str) and k and isinstance(v, str) for k, v in pairs.items()):
            raise AgentCopyError(problem)
        edits[file] = list(pairs.items())
    return edits


def apply_body_replacements(text: str, edits: list[tuple[str, str]], source: str) -> str:
    """Apply literal edits; each ``from`` must occur exactly once in ``text``."""
    for old, new in edits:
        found = text.count(old)
        if found != 1:
            raise AgentCopyError(
                f"{source}: bodyReplace text occurs {found} times, expected 1: {old!r}"
            )
        text = text.replace(old, new)
    return text


def _read_stanza(config_path: Path) -> dict[str, object] | None:
    try:
        cfg = load_platform_config(config_path)
    except ConfigError as exc:
        raise AgentCopyError(str(exc)) from exc
    artifacts = cfg.get("artifacts")
    stanza = artifacts.get("agents") if isinstance(artifacts, dict) else None
    return stanza if uses_agent_tree_copy(stanza) else None


def _keep_list(stanza: dict[str, object]) -> list[str]:
    keep = stanza[KEEP_KEY]
    if not isinstance(keep, list) or not keep or not all(isinstance(k, str) for k in keep):
        raise AgentCopyError(
            "`artifacts.agents.frontmatterKeep` must be a non-empty list of strings"
        )
    return list(keep)


def _resolve_dirs(repo_root: Path, stanza: dict[str, object]) -> tuple[Path, Path]:
    for key in ("sourceDir", "outputDir"):
        errors = validate_relative_path(f"artifacts.agents.{key}", stanza.get(key))
        if errors:
            raise AgentCopyError("; ".join(errors))
    return repo_root / str(stanza["sourceDir"]), repo_root / str(stanza["outputDir"])


def _excludes(stanza: dict[str, object]) -> frozenset[str]:
    raw = stanza.get("excludeFilenames", list(_DEFAULT_EXCLUDES))
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        raise AgentCopyError("`artifacts.agents.excludeFilenames` must be a list of strings")
    return frozenset(raw)


def _output_format(stanza: dict[str, object], keep: list[str]) -> str:
    """Return the validated ``outputFormat``; reject keys the format cannot honor."""
    fmt = stanza.get(FORMAT_KEY, FORMAT_MARKDOWN)
    if fmt not in _FORMATS:
        raise AgentCopyError(f"`artifacts.agents.{FORMAT_KEY}` must be one of {list(_FORMATS)}")
    if fmt == FORMAT_CODEX_TOML and keep != _CODEX_KEEP:
        raise AgentCopyError(
            f"`artifacts.agents.{KEEP_KEY}` must be exactly {_CODEX_KEEP} for {FORMAT_CODEX_TOML}"
        )
    return str(fmt)


def _skip_restricted(stanza: dict[str, object]) -> bool:
    """Return ``skipToolRestricted``; reject a non-boolean or a conflict with ``deriveReadonly``."""
    value = stanza.get(SKIP_RESTRICTED_KEY, False)
    if not isinstance(value, bool):
        raise AgentCopyError(f"`artifacts.agents.{SKIP_RESTRICTED_KEY}` must be a boolean")
    if value and stanza.get("deriveReadonly") is True:
        raise AgentCopyError(
            f"`artifacts.agents.{SKIP_RESTRICTED_KEY}` and `deriveReadonly: true` are exclusive"
        )
    return value


def _tool_restricted_stems(sources: list[Path]) -> list[str]:
    """Return the sorted stems of source agents whose frontmatter declares ``tools``."""
    stems: list[str] = []
    for src in sources:
        loaded, _ = parse_agent(src.read_text(encoding="utf-8"), src.as_posix())
        try:
            restricted = declared_tools(loaded) is not None
        except AgentCopyError as exc:
            raise AgentCopyError(f"{src.as_posix()}: {exc}") from exc
        if restricted:
            stems.append(src.stem)
    return sorted(stems)


def _check_name_matches_stem(src: Path, text: str) -> str:
    """Return the agent's frontmatter ``name``; fail when it differs from the file stem."""
    loaded, _ = parse_agent(text, src.as_posix())
    name = loaded.get("name")
    if name != src.stem:
        raise AgentCopyError(f"{src.as_posix()}: frontmatter name {name!r} differs from file stem")
    return str(name)


def generate_agent_copies(
    repo_root: Path, config_path: Path, *, check: bool = False, what_if: bool = False
) -> AgentCopyResult | None:
    """Render one platform's agent copy; ``None`` when the platform does not opt in.

    ``check`` writes nothing and records every differing file in ``drift``.
    ``what_if`` writes nothing and prints what would change. Raises
    :class:`AgentCopyError` for a bad stanza or source file.
    """
    stanza = _read_stanza(config_path)
    if stanza is None:
        return None
    keep = _keep_list(stanza)
    output_format = _output_format(stanza, keep)
    skip_restricted = _skip_restricted(stanza)
    suffix = _TOML_SUFFIX if output_format == FORMAT_CODEX_TOML else _SOURCE_SUFFIX
    source_dir, output_dir = _resolve_dirs(repo_root, stanza)
    if not source_dir.is_dir():
        raise AgentCopyError(f"sourceDir not found: {source_dir}")
    excludes = _excludes(stanza)
    replacements = _body_replacements(stanza)
    missing = sorted(set(replacements) - {p.name for p in source_dir.glob(f"*{_SOURCE_SUFFIX}")})
    if missing:
        raise AgentCopyError(f"bodyReplace names agents not in {source_dir}: {missing}")
    excluded = sorted(set(replacements) & excludes)
    if excluded:
        raise AgentCopyError(
            f"bodyReplace names agents that are excluded from the copy: {excluded}"
        )
    sources = [p for p in sorted(source_dir.glob(f"*{_SOURCE_SUFFIX}")) if p.name not in excludes]
    appendix = ""
    if skip_restricted:
        restricted = _tool_restricted_stems(sources)
        if restricted:
            appendix = not_installed_paragraph(restricted)
    result = AgentCopyResult()
    expected: set[str] = set()
    names: dict[str, str] = {}
    for src in sources:
        result.inputs += 1
        text = src.read_text(encoding="utf-8")
        rendered = render_agent(
            text,
            keep,
            derive_readonly_flag=stanza.get("deriveReadonly") is True,
            source=src.as_posix(),
            body_edits=replacements.get(src.name),
            skip_tool_restricted=skip_restricted,
            appendix=appendix,
            output_format=output_format,
        )
        if rendered is None:
            if src.name in replacements:
                raise AgentCopyError(
                    f"bodyReplace names {src.name}, which is skipped because its tools list "
                    "restricts it"
                )
            result.skipped.append(src.name)
            reason = (
                "declares a tools list"
                if skip_restricted
                else "tools list restricts it beyond what readonly can express"
            )
            print(f"  SKIPPED: {src.name} ({reason})")
            continue
        name = _check_name_matches_stem(src, text)
        if name in names:
            raise AgentCopyError(f"agents {names[name]} and {src.name} share the name {name!r}")
        names[name] = src.name
        out_name = f"{src.stem}{suffix}"
        expected.add(out_name)
        _emit(output_dir / out_name, rendered, result, check=check, what_if=what_if)
    if not result.inputs:
        raise AgentCopyError(f"no agent files found under {source_dir}")
    _prune(output_dir, expected, suffix, result, check=check, what_if=what_if)
    return result


def _emit(
    target: Path, rendered: str, result: AgentCopyResult, *, check: bool, what_if: bool
) -> None:
    reason = regen_detect_reason(target)
    if reason is not None:
        print(f"  NOTICE: skipped {target} (NO-REGEN: {reason})")
        return
    current = target.read_text(encoding="utf-8") if target.is_file() else None
    if current == rendered:
        return
    if check:
        result.drift.append(target.as_posix())
        return
    if what_if:
        print(f"  Would write: {target}")
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    publish_bytes_preserving_mode(target, rendered.encode("utf-8"))
    result.written += 1


def _prune(
    output_dir: Path,
    expected: set[str],
    suffix: str,
    result: AgentCopyResult,
    *,
    check: bool,
    what_if: bool,
) -> None:
    if not output_dir.is_dir():
        return
    for existing in sorted(output_dir.glob(f"*{suffix}")):
        if existing.name in expected or regen_detect_reason(existing) is not None:
            continue
        if check:
            result.drift.append(existing.as_posix())
        elif not what_if:
            existing.unlink()
            result.pruned += 1
