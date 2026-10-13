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
                      ``tools`` list names only read-only tools
``excludeFilenames``  source file names to skip

``readonly`` is derived, never guessed: an agent without a ``tools`` list gets
no ``readonly`` key, and one tool outside the read-only set removes it. Cursor
documents no tool allow-list for subagents, so ``readonly: true`` is the only
tool restriction it can carry.

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
# word is `read` (`issue_read`), and no word names a mutation (`find_and_replace`).
# An unfamiliar name matches neither test and never earns `readonly: true`.
_READ_WORDS = frozenset(
    {"get", "list", "read", "find", "search", "ask", "resolve", "initial", "query"}
)
_MUTATING_WORDS = frozenset(
    {
        "write", "edit", "create", "update", "delete", "add", "merge", "push", "replace",
        "insert", "rename", "remove", "apply", "move", "fork",
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
    if any(word in _MUTATING_WORDS for word in words):
        return False
    return words[0] in _READ_WORDS or words[-1] == "read"


def derive_readonly(frontmatter: dict[str, object]) -> bool:
    """True when the agent declares tools and every one is read-only."""
    tools = frontmatter.get("tools")
    if not isinstance(tools, list) or not tools:
        return False
    return all(is_readonly_tool(tool) for tool in tools)


def render_agent(text: str, keep: list[str], *, derive_readonly_flag: bool, source: str) -> str:
    """Return ``text`` with its frontmatter reduced to the ``keep`` keys."""
    parsed = read_yaml_frontmatter(text)
    if parsed is None:
        raise AgentCopyError(f"{source}: no frontmatter block")
    try:
        loaded = yaml.safe_load(parsed["frontmatter_raw"])
    except yaml.YAMLError as exc:
        raise AgentCopyError(f"{source}: unparseable frontmatter: {exc}") from exc
    if not isinstance(loaded, dict):
        raise AgentCopyError(f"{source}: frontmatter is not a mapping")
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
        expected.add(src.name)
        rendered = render_agent(
            src.read_text(encoding="utf-8"),
            keep,
            derive_readonly_flag=stanza.get("deriveReadonly") is True,
            source=src.as_posix(),
        )
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
