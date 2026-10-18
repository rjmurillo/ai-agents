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

``readonly`` is derived, never guessed: an agent without a ``tools`` list gets
no ``readonly`` key (it is unrestricted in Claude too), unless it carries a
``disallowedTools`` list that denies every built-in shell and file mutator. A deny-list
agent that leaves one of them open (``security`` keeps ``Write``) is not shipped.
Cursor documents no tool allow-list for subagents, so ``readonly: true`` is the only tool
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

import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

_SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPT_DIR))
sys.path.insert(0, str(_SCRIPT_DIR.parent))

import agent_capabilities  # noqa: E402
from atomic_write import publish_bytes_preserving_mode  # noqa: E402
from generate_agents_common import read_yaml_frontmatter  # noqa: E402
from regen_guard import detect_reason as regen_detect_reason  # noqa: E402
from yaml_loader import ConfigError, load_platform_config, validate_relative_path  # noqa: E402

KEEP_KEY = "frontmatterKeep"
_READONLY_KEY = "readonly"
_SOURCE_SUFFIX = ".md"
_DEFAULT_EXCLUDES = ("AGENTS.md", "CLAUDE.md")
_READONLY_TOOLS = frozenset({"Read", "Glob", "Grep", "WebSearch", "WebFetch"})
# An MCP tool name is `mcp__<server>__<words>`, the words joined by `_`. It is
# read-only when a read verb leads the words (`get_file_contents`) or the last
# word is `read` (`issue_read`), and no word names a mutation (`find_and_replace`,
# `get_and_run`). `run` is a noun in `get_workflow_run`, so it is not a mutating
# word; a compound name (`and`, `then`) is rejected instead. `query` is not a
# read word: `mcp__db__query` can run a write. `resolve` and `ask` can lead a
# state change (`resolve_review_thread`), so only the exact names in
# _READ_NAMES earn readonly through them.
# An unfamiliar name matches neither test and never earns `readonly: true`.
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


def is_readonly_tool(tool: object) -> bool:
    """True when ``tool`` names a tool that changes no state."""
    if not isinstance(tool, str):
        return False
    if tool in _READONLY_TOOLS:
        return True
    parts = tool.split("__")
    if len(parts) < 3 or parts[0] != "mcp":
        return False
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
    """True when the agent declares only read-only tools, or denies every mutator.

    A deny-list member (no ``tools``, ``disallowedTools`` present, ADR-107
    "Read-only agents inherit tools") earns ``readonly`` when its list names
    every built-in shell and file mutator. Without this the Cursor copy of a
    read-only Claude agent would silently lose its one restriction.
    """
    tools = declared_tools(frontmatter)
    if tools is None and agent_capabilities.is_deny_list_member(frontmatter):
        return not agent_capabilities.uncovered_mutators(frontmatter, include_write=True)
    return bool(tools) and all(is_readonly_tool(tool) for tool in tools or [])


def has_inexpressible_restriction(frontmatter: dict[str, object]) -> bool:
    """True when ``tools`` restricts the agent in a way ``readonly`` cannot express.

    An empty list or empty string restricts the agent to nothing. Cursor has no
    way to say that, so it fails closed like any other non-read-only list.
    """
    restricted = declared_tools(frontmatter) is not None
    if agent_capabilities.is_deny_list_member(frontmatter):
        restricted = True
    return restricted and not derive_readonly(frontmatter)


def render_agent(
    text: str, keep: list[str], *, derive_readonly_flag: bool, source: str
) -> str | None:
    """Return ``text`` with its frontmatter reduced to the ``keep`` keys.

    Returns ``None`` when ``derive_readonly_flag`` is set and the agent carries a
    tool restriction ``readonly`` cannot express (ADR-115 Decision 3). The caller
    must not ship such an agent.
    """
    parsed = read_yaml_frontmatter(text)
    if parsed is None:
        raise AgentCopyError(f"{source}: no frontmatter block")
    try:
        loaded = yaml.safe_load(parsed["frontmatter_raw"])
    except yaml.YAMLError as exc:
        raise AgentCopyError(f"{source}: unparseable frontmatter: {exc}") from exc
    if not isinstance(loaded, dict):
        raise AgentCopyError(f"{source}: frontmatter is not a mapping")
    try:
        if derive_readonly_flag and has_inexpressible_restriction(loaded):
            return None
    except AgentCopyError as exc:
        raise AgentCopyError(f"{source}: {exc}") from exc
    kept = {key: loaded[key] for key in keep if key in loaded}
    if derive_readonly_flag and derive_readonly(loaded):
        kept[_READONLY_KEY] = True
    dumped = yaml.safe_dump(
        kept, sort_keys=False, allow_unicode=True, default_flow_style=False, width=10**9
    )
    return f"---\n{dumped}---\n{parsed['body']}"


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
    source_dir, output_dir = _resolve_dirs(repo_root, stanza)
    if not source_dir.is_dir():
        raise AgentCopyError(f"sourceDir not found: {source_dir}")
    excludes = _excludes(stanza)
    result = AgentCopyResult()
    expected: set[str] = set()
    for src in sorted(source_dir.glob(f"*{_SOURCE_SUFFIX}")):
        if src.name in excludes:
            continue
        result.inputs += 1
        rendered = render_agent(
            src.read_text(encoding="utf-8"),
            keep,
            derive_readonly_flag=stanza.get("deriveReadonly") is True,
            source=src.as_posix(),
        )
        if rendered is None:
            result.skipped.append(src.name)
            print(
                f"  SKIPPED: {src.name} (tools list restricts it beyond what readonly can express)"
            )
            continue
        expected.add(src.name)
        _emit(output_dir / src.name, rendered, result, check=check, what_if=what_if)
    if not result.inputs:
        raise AgentCopyError(f"no agent files found under {source_dir}")
    _prune(output_dir, expected, result, check=check, what_if=what_if)
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
    output_dir: Path, expected: set[str], result: AgentCopyResult, *, check: bool, what_if: bool
) -> None:
    if not output_dir.is_dir():
        return
    for existing in sorted(output_dir.glob(f"*{_SOURCE_SUFFIX}")):
        if existing.name in expected or regen_detect_reason(existing) is not None:
            continue
        if check:
            result.drift.append(existing.as_posix())
        elif not what_if:
            existing.unlink()
            result.pruned += 1
