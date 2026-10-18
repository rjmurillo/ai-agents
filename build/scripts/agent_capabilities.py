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
MCP_TABLE_RELATIVE_PATH = Path("templates") / "agent-mcp-servers.yaml"
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
    "ToolSearch": "tool-discovery",
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
_PLUGIN_SERVER_RE = re.compile(r"^plugin_(?P<name>.+)_(?P=name)$")
_CONNECTOR_PREFIX = "claude_ai_"
_TOOLSET_PREFIX = "$toolset:"
_REF_ITEM_RE = re.compile(r"^(?P<indent>[ \t]*)- \$mcp:(?P<name>\S*)[ \t]*$", re.MULTILINE)
# A bare `mcp__*` (or `mcp__`) grants no MCP tool on Claude Code 2.1.302 (probe,
# 2026-10-17), so a template that writes one silently grants nothing.
_GLOBAL_MCP_RE = re.compile(r"(?<![\w])mcp__\*?(?![\w*])")
_FRONTMATTER_BLOCK_RE = re.compile(r"\A---\r?\n.*?\r?\n---\r?\n", re.DOTALL)
_PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")
_TOOL_NAME_RE = re.compile(r"^[A-Za-z0-9_]+$")


class CapabilityError(Exception):
    """A tool list or toolset definition is unusable."""


def _claude_server(server: str) -> str:
    """Return the logical server for a Claude MCP prefix variant.

    ``plugin_<s>_<s>`` and ``claude_ai_<Name>`` are other spellings of the server
    a ``.mcp.json`` entry calls ``<s>``, so the parity gate must compare them as
    one capability family.
    """
    plugin = _PLUGIN_SERVER_RE.match(server)
    if plugin:
        return plugin["name"]
    if server.startswith(_CONNECTOR_PREFIX):
        return server[len(_CONNECTOR_PREFIX) :].lower().replace("_", "-")
    return server


def classify(name: str) -> tuple[str, str]:
    """Return ``(family, item)`` for one tool name.

    ``family`` is ``builtin``, ``mcp:<server>``, or ``unmapped``.
    """
    if name in _BUILTIN:
        return FAMILY_BUILTIN, _BUILTIN[name]
    claude = _CLAUDE_MCP_RE.match(name)
    if claude:
        return f"mcp:{_claude_server(claude['server'])}", claude["tool"].replace("-", "_")
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


def load_mcp_table(repo_root: Path) -> dict[str, object]:
    """Return the MCP server table. A missing file is an empty mapping.

    The file is ``templates/agent-mcp-servers.yaml``: ``prefix_variants``
    and ``servers``. An empty mapping makes every ``$mcp:`` reference an unknown
    name, which fails the build.
    """
    path = repo_root / MCP_TABLE_RELATIVE_PATH
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


def _prefix_templates(value: object, where: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise CapabilityError(f"{where} must be a non-empty list")
    if not all(isinstance(item, str) and item.startswith("mcp__") for item in value):
        raise CapabilityError(f"every entry of {where} must be a string starting with 'mcp__'")
    return list(value)


def _server_prefixes(server: str, table: dict[str, object]) -> list[str]:
    """Return every ``mcp__...`` prefix for one logical server.

    A server entry may carry its own ``variants`` list; otherwise the table's
    ``prefix_variants`` apply.
    """
    servers = table.get("servers")
    entry = servers.get(server) if isinstance(servers, dict) else None
    if not isinstance(entry, dict):
        raise CapabilityError(f"unknown MCP server {server!r}: no `servers` entry")
    if "variants" in entry:
        variants = _prefix_templates(entry["variants"], f"servers.{server}.variants")
    else:
        variants = _prefix_templates(table.get("prefix_variants"), "prefix_variants")
    prefixes: list[str] = []
    for variant in variants:
        wanted = set(_PLACEHOLDER_RE.findall(variant))
        if not wanted <= {"server", "claude_ai"}:
            raise CapabilityError(f"prefix variant {variant!r} uses an unknown placeholder")
        names = (
            _string_list(entry.get("claude_ai"), f"servers.{server}.claude_ai")
            if "claude_ai" in wanted
            else [""]
        )
        prefixes.extend(variant.format(server=server, claude_ai=name) for name in names)
    return list(dict.fromkeys(prefixes))


_NO_WILDCARD_KEYS = ("explicit_only", "remote_only")


def wildcard_servers(table: dict[str, object]) -> list[str]:
    """Return the servers the table lets a template grant by wildcard.

    A server marked ``explicit_only`` has write or shell tools, and one marked
    ``remote_only`` is listed only to satisfy the ``.mcp.json`` coverage check.
    Neither may be granted whole.
    """
    servers = table.get("servers")
    if not isinstance(servers, dict):
        return []
    return [
        name
        for name, entry in servers.items()
        if isinstance(entry, dict) and not any(key in entry for key in _NO_WILDCARD_KEYS)
    ]


def wildcard_grants(table: dict[str, object]) -> frozenset[str]:
    """Return every ``<prefix>__*`` entry that ``$mcp:`` can emit."""
    return frozenset(
        grant for server in wildcard_servers(table) for grant in expand_server_grant(server, table)
    )


def expand_server_grant(server: str, table: dict[str, object]) -> list[str]:
    """Return ``<prefix>__*`` for every prefix variant of ``server``.

    A server-level entry is the only MCP wildcard Claude Code honors in
    ``tools`` (probe, Claude Code 2.1.302, 2026-10-17): ``mcp__<server>__*``
    grants that server's tools, and a bare ``mcp__*`` grants none. A server
    marked ``explicit_only`` or ``remote_only`` fails, because a wildcard would
    grant every tool it has, write and shell tools included.
    """
    servers = table.get("servers")
    entry = servers.get(server) if isinstance(servers, dict) else None
    blocked = [key for key in _NO_WILDCARD_KEYS if isinstance(entry, dict) and key in entry]
    if blocked:
        raise CapabilityError(
            f"MCP server {server!r} is {blocked[0]}, so it cannot be granted by wildcard; "
            "list its read tools one by one"
        )
    return [f"{prefix}__*" for prefix in _server_prefixes(server, table)]


def expand_frontmatter(text: str, table: dict[str, object]) -> str:
    """Expand ``- $mcp:<server>`` list items in the frontmatter.

    Only the frontmatter is touched; a body that mentions ``$mcp:`` is left
    alone. A reference that is not a whole list item raises, because leaving it
    would ship the literal text as a tool name. A bare ``mcp__*`` entry raises
    too: it grants nothing on Claude Code 2.1.302.
    """
    match = _FRONTMATTER_BLOCK_RE.match(text)
    if match is None:
        return text

    def replace(item: re.Match[str]) -> str:
        entries = expand_server_grant(item["name"], table)
        return "\n".join(f"{item['indent']}- {entry}" for entry in entries)

    head = _REF_ITEM_RE.sub(replace, match.group(0))
    if "$mcp:" in head:
        raise CapabilityError("a $mcp: reference must be a whole list item")
    if _GLOBAL_MCP_RE.search(head):
        raise CapabilityError("bare `mcp__*` grants no tool; use a `$mcp:<server>` reference")
    return head + text[match.end() :]
