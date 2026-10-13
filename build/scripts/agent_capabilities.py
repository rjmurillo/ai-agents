"""Abstract capability sets for agent tool lists (ADR-107 section 5, invariant 6).

Each harness spells a tool differently: Claude writes ``Read`` and
``mcp__github__issue_read``, VS Code and Copilot CLI write ``read`` and
``github/issue_read``. The spelling is a projection detail. The capability the
agent holds is not, so ``check_agent_source_parity.py`` compares the abstract
set and never the spelling.

The mapping fails closed. A name this module does not know stays a literal
``unmapped`` item, so an unrecognized tool can only produce a difference, never
hide one. A wildcard such as ``serena/*`` is a different capability from any
explicit ``serena/<tool>`` list, because the wildcard grants tools the explicit
list does not name.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

TOOLSETS_RELATIVE_PATH = Path("templates") / "toolsets.yaml"
DECLARATION = "declaration"
RESTRICTED = "restricted"
UNRESTRICTED = "unrestricted"

FAMILY_BUILTIN = "builtin"
FAMILY_UNMAPPED = "unmapped"

_BUILTIN: dict[str, str] = {
    # Claude Code spellings.
    "Read": "read",
    "Glob": "search",
    "Grep": "search",
    "Write": "write",
    "Edit": "write",
    "MultiEdit": "write",
    "NotebookEdit": "write",
    "Bash": "execute",
    "WebFetch": "network",
    "WebSearch": "network",
    "Task": "delegate",
    "TodoWrite": "track",
    # VS Code and Copilot CLI spellings.
    "read": "read",
    "search": "search",
    "edit": "write",
    "execute": "execute",
    "shell": "execute",
    "web": "network",
    "agent": "delegate",
    "todo": "track",
    "memory": "memory",
    "vscode": "host:vscode",
}
_SERVER_ALIASES = {"cognitionai/deepwiki": "deepwiki"}
_CLAUDE_MCP_RE = re.compile(r"^mcp__(?P<server>.+?)__(?P<tool>.+)$")
_TOOLSET_PREFIX = "$toolset:"


class CapabilityError(Exception):
    """A tool list or toolset definition is unusable."""


def classify(name: str) -> tuple[str, str]:
    """Return ``(family, item)`` for one tool name.

    ``family`` is ``builtin``, ``mcp:<server>``, or ``unmapped``.
    """
    if name in _BUILTIN:
        return FAMILY_BUILTIN, _BUILTIN[name]
    claude = _CLAUDE_MCP_RE.match(name)
    if claude:
        return f"mcp:{claude['server']}", claude["tool"].replace("-", "_")
    if "/" in name:
        server, tool = name.rsplit("/", 1)
        return f"mcp:{_SERVER_ALIASES.get(server, server)}", tool.replace("-", "_")
    return FAMILY_UNMAPPED, name


def load_toolsets(repo_root: Path) -> dict[str, dict[str, object]]:
    """Return the named toolset definitions. A missing file is an empty mapping."""
    path = repo_root / TOOLSETS_RELATIVE_PATH
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        raise CapabilityError(f"cannot read {path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise CapabilityError(f"{path} is not valid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise CapabilityError(f"{path} must be a mapping of toolset names")
    return data


def _expand_one(name: str, key: str, toolsets: dict[str, dict[str, object]]) -> list[str]:
    toolset = toolsets.get(name)
    if not isinstance(toolset, dict):
        raise CapabilityError(f"unknown toolset {name!r} referenced from {key}")
    tools = toolset.get(key, toolset.get("tools"))
    if not isinstance(tools, list):
        raise CapabilityError(f"toolset {name!r} has no tools for {key!r}")
    return [str(tool) for tool in tools]


def expand_names(names: list[str], key: str, toolsets: dict[str, dict[str, object]]) -> list[str]:
    """Replace each ``$toolset:name`` with that toolset's tools for frontmatter ``key``.

    The platform variant (``tools_vscode`` or ``tools_copilot``) wins over the
    shared ``tools`` list, as in ``build/generate_agents_common.py``.
    """
    expanded: list[str] = []
    for name in names:
        if name.startswith(_TOOLSET_PREFIX):
            expanded.extend(_expand_one(name[len(_TOOLSET_PREFIX) :], key, toolsets))
        else:
            expanded.append(name)
    return expanded


def _names(value: object, key: str) -> list[str]:
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    if not isinstance(value, list):
        raise CapabilityError(f"{key} must be a list or a comma-separated string")
    if not all(isinstance(item, str) for item in value):
        raise CapabilityError(f"{key} holds a non-string tool entry")
    return [item.strip() for item in value if item.strip()]


def capability_units(
    frontmatter: dict[str, object],
    key: str,
    prefix: str,
    toolsets: dict[str, dict[str, object]],
) -> dict[str, str]:
    """Return ``{unit: text}`` for the abstract capability set in ``frontmatter[key]``.

    One ``<prefix>:declaration`` unit says whether the member restricts its
    tools at all, because an agent with no tool list inherits every tool. One
    ``<prefix>:<family>`` unit per family holds the sorted, de-duplicated items.
    """
    if key not in frontmatter or frontmatter[key] is None:
        return {f"{prefix}:{DECLARATION}": UNRESTRICTED}
    names = expand_names(_names(frontmatter[key], key), key, toolsets)
    families: dict[str, set[str]] = {}
    for name in names:
        family, item = classify(name)
        families.setdefault(family, set()).add(item)
    units = {f"{prefix}:{DECLARATION}": RESTRICTED}
    for family, items in families.items():
        units[f"{prefix}:{family}"] = "\n".join(sorted(items))
    return units


def drop_families_on_declaration_mismatch(left: dict[str, str], right: dict[str, str]) -> None:
    """Remove family units for a prefix whose two declarations disagree.

    A restricted list against an unrestricted member is one divergence, the
    declaration. Comparing the families too would pin the same fact once per
    family.
    """
    declarations = {u for u in (*left, *right) if u.endswith(f":{DECLARATION}")}
    for declaration in declarations:
        if left.get(declaration) == right.get(declaration):
            continue
        prefix = declaration[: -len(DECLARATION)]
        for units in (left, right):
            for unit in [u for u in units if u.startswith(prefix) and u != declaration]:
                del units[unit]
