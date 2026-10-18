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
DENYLISTS_RELATIVE_PATH = Path("templates") / "agent-denylists.yaml"
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
_DENY_PREFIX = "$deny:"
_DENY_ITEM_RE = re.compile(r"^(?P<indent>[ \t]*)- (?P<ref>\$deny:\S*)[ \t]*$", re.MULTILINE)
_FRONTMATTER_BLOCK_RE = re.compile(r"\A---\r?\n.*?\r?\n---\r?\n", re.DOTALL)
_PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")
_TOOL_NAME_RE = re.compile(r"^[A-Za-z0-9_]+$")
# Capabilities a read-only agent must not hold (see ``_BUILTIN``).
MUTATOR_CAPABILITIES = frozenset({"write", "execute"})


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


def load_denylists(repo_root: Path) -> dict[str, object]:
    """Return the Claude deny-list definitions. A missing file is an empty mapping.

    The file is ``templates/agent-denylists.yaml``: ``prefix_variants``,
    ``servers`` and ``denylists``. An empty mapping makes every ``$deny:``
    reference an unknown name, which fails the build.
    """
    path = repo_root / DENYLISTS_RELATIVE_PATH
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        raise CapabilityError(f"cannot read {path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise CapabilityError(f"{path} is not valid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise CapabilityError(f"{path} must be a mapping")
    return data


def _string_list(value: object, where: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise CapabilityError(f"{where} must be a non-empty list")
    if not all(isinstance(item, str) and _TOOL_NAME_RE.match(item) for item in value):
        raise CapabilityError(f"{where} holds an entry that is not a plain tool name")
    return list(value)


def _prefix_templates(value: object) -> list[str]:
    if not isinstance(value, list) or not value:
        raise CapabilityError("prefix_variants must be a non-empty list")
    if not all(isinstance(item, str) and item.startswith("mcp__") for item in value):
        raise CapabilityError("every prefix variant must be a string starting with 'mcp__'")
    return list(value)


def _server_prefixes(server: str, config: dict[str, object]) -> list[str]:
    """Return every ``mcp__...`` prefix variant for one logical server."""
    variants = _prefix_templates(config.get("prefix_variants"))
    servers = config.get("servers")
    entry = servers.get(server) if isinstance(servers, dict) else None
    if not isinstance(entry, dict):
        raise CapabilityError(f"deny list names server {server!r}, which has no `servers` entry")
    prefixes: list[str] = []
    for variant in variants:
        wanted = set(_PLACEHOLDER_RE.findall(variant))
        if not wanted <= {"server", "claude_ai"}:
            raise CapabilityError(f"prefix variant {variant!r} uses an unknown placeholder")
        if "claude_ai" in wanted:
            names = _string_list(entry.get("claude_ai"), f"servers.{server}.claude_ai")
        else:
            names = [""]
        prefixes.extend(variant.format(server=server, claude_ai=name) for name in names)
    return list(dict.fromkeys(prefixes))


def expand_deny(name: str, config: dict[str, object]) -> list[str]:
    """Return the tool entries for logical deny list ``name``.

    A list with a ``server`` expands to ``<prefix>__<tool>`` for every prefix
    variant. A list without one is literal (built-in tool names). An unknown
    name raises, matching ``_expand_one``: a typo must never silently deny
    nothing.
    """
    lists = config.get("denylists")
    entry = lists.get(name) if isinstance(lists, dict) else None
    if not isinstance(entry, dict):
        raise CapabilityError(f"unknown deny list {name!r}")
    tools = _string_list(entry.get("tools"), f"denylists.{name}.tools")
    server = entry.get("server")
    if server is None:
        return tools
    if not isinstance(server, str):
        raise CapabilityError(f"denylists.{name}.server must be a string")
    return [f"{prefix}__{tool}" for prefix in _server_prefixes(server, config) for tool in tools]


def expand_deny_frontmatter(text: str, config: dict[str, object]) -> str:
    """Expand each ``- $deny:<name>`` list item in the frontmatter block of ``text``.

    Only the frontmatter is touched; a body that mentions ``$deny:`` is left
    alone. A ``$deny:`` that is not a whole list item (for example inside a
    flow list) raises, because leaving it would ship the literal text as a
    tool name.
    """
    match = _FRONTMATTER_BLOCK_RE.match(text)
    if match is None:
        return text

    def replace(item: re.Match[str]) -> str:
        entries = expand_deny(item["ref"][len(_DENY_PREFIX) :], config)
        return "\n".join(f"{item['indent']}- {entry}" for entry in entries)

    head = _DENY_ITEM_RE.sub(replace, match.group(0))
    if _DENY_PREFIX in head:
        raise CapabilityError("a $deny: reference must be a whole list item in the frontmatter")
    return head + text[match.end() :]


def _claude_mutators() -> frozenset[str]:
    """Claude spellings of the built-in tools whose capability is a mutator."""
    return frozenset(
        name
        for name, item in _BUILTIN.items()
        if item in MUTATOR_CAPABILITIES and name[0].isupper()
    )


def is_deny_list_member(frontmatter: dict[str, object]) -> bool:
    """True when a Claude member inherits tools and denies at least one built-in mutator.

    A member that omits ``tools`` and denies only ``Agent`` (the worker
    convention, ``check_agent_delegation.py``) is not read-only by deny list; it
    stays on the ordinary ``tools`` comparison. Denying even one mutator opts
    the member in, so a half-finished list is caught by :func:`uncovered_mutators`
    and not skipped.
    """
    if frontmatter.get("tools") is not None or frontmatter.get("disallowedTools") is None:
        return False
    denied = set(_names(frontmatter["disallowedTools"], "disallowedTools"))
    return bool(denied & _claude_mutators())


def uncovered_mutators(frontmatter: dict[str, object]) -> list[str]:
    """Return Claude built-in mutator tools a deny-list member fails to deny.

    Empty when the member is not deny-list shaped, because then the ordinary
    ``tools`` comparison owns the question. A member that omits ``tools``
    inherits every tool, so each built-in mutator must be denied by name.
    """
    if not is_deny_list_member(frontmatter):
        return []
    denied = set(_names(frontmatter["disallowedTools"], "disallowedTools"))
    return sorted(_claude_mutators() - denied)
