#!/usr/bin/env python3
"""Shared functions for agent generation and testing.

This module contains common functions used by both generate_agents.py
and its test suite. Extracting these functions ensures tests validate
the actual implementations, not stale copies.

This is a Python port of Generate-Agents.Common.psm1 following ADR-042 migration.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

# Field ordering for frontmatter output
_FIELD_ORDER = ("name", "description", "argument-hint", "tools", "model")

# Regex for parsing inline array items
_ARRAY_ITEM_PATTERN = re.compile(r"'([^']+)'|\"([^\"]+)\"|([^,\s]+)")

# Regex for block-style array items
_BLOCK_ARRAY_ITEM = re.compile(r"^\s+-\s*(.*)$")

# Regex for frontmatter key-value lines (allows hyphens in keys)
_FM_KEY_VALUE = re.compile(r"^([\w-]+):\s*(.*)$")

# Regex for YAML frontmatter extraction
_FRONTMATTER_RE = re.compile(r"^---\r?\n([\s\S]*?)\r?\n---\r?\n([\s\S]*)$")


def is_path_within_root(path: str | Path, root: str | Path) -> bool:
    """Security check: validate that a path is within the repository root.

    Ensures path is a true descendant of root by appending directory separator
    to prevent prefix-matching attacks (e.g., /repo_evil matching /repo).
    """
    resolved_path = os.path.abspath(str(path))
    resolved_root = os.path.abspath(str(root)).rstrip("/\\")

    path_without_trailing = resolved_path.rstrip("/\\")
    if path_without_trailing == resolved_root:
        return True

    resolved_root_with_sep = resolved_root + os.sep
    return os.path.normcase(resolved_path).startswith(
        os.path.normcase(resolved_root_with_sep)
    )


def read_yaml_frontmatter(content: str) -> dict[str, str] | None:
    """Extract YAML frontmatter from a markdown file.

    Returns dict with 'frontmatter_raw' and 'body' keys, or None if no frontmatter found.
    """
    match = _FRONTMATTER_RE.match(content)
    if match:
        return {
            "frontmatter_raw": match.group(1),
            "body": match.group(2),
        }
    return None


def parse_simple_frontmatter(frontmatter_raw: str) -> dict[str, str | None]:
    """Parse simple YAML frontmatter into a dict.

    Handles basic key: value pairs, inline arrays ['item1', 'item2'],
    and block-style arrays with indented list items.
    """
    if not frontmatter_raw or not frontmatter_raw.strip():
        return {}

    result: dict[str, str | None] = {}
    lines = re.split(r"\r?\n", frontmatter_raw)
    current_key: str | None = None
    current_array: list[str] | None = None

    for i, line in enumerate(lines):
        if not line.strip():
            continue

        # Check for block-style array item (indented with "  - ")
        array_match = _BLOCK_ARRAY_ITEM.match(line)
        if array_match:
            if current_key is not None and current_array is not None:
                item = array_match.group(1).strip()
                item = _strip_quotes(item)
                current_array.append(item)
            continue

        # Save pending block array
        if current_key is not None and current_array is not None:
            result[current_key] = _format_inline_array(current_array)
            current_key = None
            current_array = None

        kv_match = _FM_KEY_VALUE.match(line)
        if kv_match:
            key = kv_match.group(1)
            value = kv_match.group(2).strip()

            if re.match(r"^\[.*\]$", value):
                result[key] = value
            elif value == "" or value == "null":
                # Check if next line is an array item
                if i + 1 < len(lines) and _BLOCK_ARRAY_ITEM.match(lines[i + 1]):
                    current_key = key
                    current_array = []
                else:
                    result[key] = None
            else:
                value = _strip_quotes(value)
                result[key] = value

    # Handle array at end of frontmatter
    if current_key is not None and current_array is not None:
        result[current_key] = _format_inline_array(current_array)

    return result


def _strip_quotes(value: str) -> str:
    """Remove surrounding single or double quotes from a value."""
    if len(value) >= 2:
        if (value[0] == '"' and value[-1] == '"') or (value[0] == "'" and value[-1] == "'"):
            return value[1:-1]
    return value


def _format_inline_array(items: list[str]) -> str:
    """Format a list of items as an inline array string."""
    quoted = [f"'{item}'" for item in items]
    return "[" + ", ".join(quoted) + "]"


def convert_frontmatter_for_platform(
    frontmatter: dict[str, str | None],
    platform_config: dict[str, object],
    agent_name: str,
) -> dict[str, str | None]:
    """Transform frontmatter for a specific platform."""
    result: dict[str, str | None] = {}
    platform_name = str(platform_config.get("platform", ""))

    for key, value in frontmatter.items():
        if isinstance(value, str) and value.startswith("{{PLATFORM_"):
            continue
        if key.startswith("tools_"):
            continue
        if key == "tools" and (
            "tools_vscode" in frontmatter or "tools_copilot" in frontmatter
        ):
            continue
        result[key] = value

    fm = platform_config.get("frontmatter")
    if isinstance(fm, dict):
        if fm.get("includeNameField") is True:
            result["name"] = agent_name
        else:
            result.pop("name", None)

        model = fm.get("model")
        if model:
            result["model"] = str(model)
        else:
            result.pop("model", None)
    else:
        result.pop("name", None)
        result.pop("model", None)

    # Handle platform-specific tools array
    clean_name = platform_name.replace("-", "")
    tools_key = f"tools_{clean_name}"
    alt_name = re.sub(r"-cli$", "", platform_name)
    tools_key_alt = f"tools_{alt_name}"

    if tools_key in frontmatter:
        result["tools"] = frontmatter[tools_key]
    elif tools_key_alt in frontmatter:
        result["tools"] = frontmatter[tools_key_alt]
    elif "tools" in frontmatter:
        tools_value = frontmatter["tools"]
        if isinstance(tools_value, str) and not tools_value.startswith("{{PLATFORM_"):
            result["tools"] = tools_value

    return result


def format_frontmatter_yaml(frontmatter: dict[str, str | None]) -> str:
    """Convert frontmatter dict back to YAML string.

    Maintains specific field order for consistency.
    Outputs arrays in block-style format for cross-platform compatibility.
    """
    lines: list[str] = []

    def _format_field(key: str, value: str | None) -> list[str]:
        if value is None:
            return []
        value_str = str(value)

        # Check if value is an inline array
        array_match = re.match(r"^\[(.*)\]$", value_str)
        if array_match:
            array_content = array_match.group(1)
            items = _parse_array_items(array_content)

            if not items and array_content.strip():
                return [f"{key}: {value_str}"]

            result = [f"{key}:"]
            for item in items:
                result.append(f"  - {item}")
            return result

        return [f"{key}: {value_str}"]

    # Output fields in defined order first
    for field_name in _FIELD_ORDER:
        if field_name in frontmatter and frontmatter[field_name] is not None:
            lines.extend(_format_field(field_name, frontmatter[field_name]))

    # Output remaining fields
    for key in frontmatter:
        if key not in _FIELD_ORDER and frontmatter[key] is not None:
            lines.extend(_format_field(key, frontmatter[key]))

    return "\n".join(lines)


def _parse_array_items(array_content: str) -> list[str]:
    """Parse items from an inline array content string."""
    items: list[str] = []
    for match in _ARRAY_ITEM_PATTERN.finditer(array_content):
        if match.group(1):
            items.append(match.group(1))
        elif match.group(2):
            items.append(match.group(2))
        elif match.group(3):
            items.append(match.group(3))
    return items


def convert_handoff_syntax(body: str, target_syntax: str) -> str:
    """Transform handoff syntax in markdown body.

    Handles multiple patterns:
    - `/agent name` with backticks: `/agent implementer`
    - `/agent` alone with backticks: `/agent`
    - `/agent name` without backticks (start of line): /agent context-retrieval
    - `/agent [agent_name]` placeholder text
    """
    result = body

    if target_syntax == "#runSubagent":
        # Transform backticked `/agent name` to `#runSubagent with subagentType=name`
        result = re.sub(r"`/agent\s+(\w+)`", r"`#runSubagent with subagentType=\1`", result)
        # Transform backticked `/agent` alone to `#runSubagent`
        result = re.sub(r"`/agent`", r"`#runSubagent`", result)
        # Transform line-start /agent name (no backticks) to #runSubagent with subagentType=name
        result = re.sub(r"^/agent\s+([\w-]+)", r"#runSubagent with subagentType=\1", result, flags=re.MULTILINE)
        # Transform placeholder text
        result = result.replace(
            "/agent [agent_name]", "#runSubagent with subagentType={agent_name}"
        )
    elif target_syntax == "/agent":
        # Reverse transformations
        result = re.sub(
            r"`#runSubagent with subagentType=(\w+)`", r"`/agent \1`", result
        )
        result = re.sub(r"`#runSubagent`", r"`/agent`", result)
        result = re.sub(
            r"^#runSubagent with subagentType=([\w-]+)", r"/agent \1", result, flags=re.MULTILINE
        )
        result = result.replace(
            "#runSubagent with subagentType={agent_name}", "/agent [agent_name]"
        )

    return result


def convert_memory_prefix(body: str, prefix: str) -> str:
    """Replace {{MEMORY_PREFIX}} placeholder with platform-specific prefix."""
    return body.replace("{{MEMORY_PREFIX}}", prefix)


def read_toolset_definitions(toolsets_path: str | Path) -> dict[str, dict[str, object]]:
    """Read toolset definitions from a YAML file.

    Parses the toolsets.yaml file which defines named groups of tools
    with optional platform-specific variants.
    """
    path = Path(toolsets_path)
    if not path.exists():
        return {}

    content = path.read_text(encoding="utf-8")
    lines = re.split(r"\r?\n", content)
    toolsets: dict[str, dict[str, object]] = {}
    current_toolset: str | None = None
    current_key: str | None = None
    current_array: list[str] | None = None

    for line in lines:
        if re.match(r"^\s*#", line) or not line.strip():
            continue

        # Top-level toolset name
        top_match = re.match(r"^([a-zA-Z][\w-]*):\s*$", line)
        if top_match:
            _save_toolset_array(toolsets, current_toolset, current_key, current_array)
            current_toolset = top_match.group(1)
            toolsets[current_toolset] = {}
            current_key = None
            current_array = None
            continue

        # Nested key starting a block array (indented, ends with colon, no value)
        nested_key_match = re.match(r"^\s{2}(\w[\w_]*):\s*$", line)
        if nested_key_match:
            _save_toolset_array(toolsets, current_toolset, current_key, current_array)
            current_key = nested_key_match.group(1)
            current_array = []
            continue

        # Nested key-value pair
        nested_kv_match = re.match(r"^\s{2}(\w[\w_]*):\s+(.+)$", line)
        if nested_kv_match:
            _save_toolset_array(toolsets, current_toolset, current_key, current_array)
            current_key = None
            current_array = None
            if current_toolset is not None:
                key = nested_kv_match.group(1)
                value = nested_kv_match.group(2).strip()
                toolsets[current_toolset][key] = value
            continue

        # Array item
        array_item_match = re.match(r"^\s{4}-\s+(.+)$", line)
        if array_item_match and current_array is not None:
            current_array.append(array_item_match.group(1).strip())

    # Save final array
    _save_toolset_array(toolsets, current_toolset, current_key, current_array)

    return toolsets


def _save_toolset_array(
    toolsets: dict[str, dict[str, object]],
    toolset_name: str | None,
    key: str | None,
    array: list[str] | None,
) -> None:
    """Save a collected array into the toolsets dict."""
    if toolset_name is not None and key is not None and array is not None:
        toolsets[toolset_name][key] = array


def expand_toolset_references(
    tools_array_string: str,
    toolsets: dict[str, dict[str, object]],
    platform_name: str,
) -> str:
    """Expand $toolset:name references in a tools array string.

    Takes a tools array in inline format and expands each $toolset:name
    reference into its individual tools based on the toolset definitions
    and the target platform.
    """
    if "$toolset:" not in tools_array_string:
        return tools_array_string

    array_match = re.match(r"^\[(.*)\]$", tools_array_string)
    if not array_match:
        return tools_array_string

    array_content = array_match.group(1)
    items = _parse_array_items(array_content)

    expanded: list[str] = []
    clean_name = platform_name.replace("-", "")
    alt_name = re.sub(r"-cli$", "", platform_name)

    for item in items:
        toolset_match = re.match(r"^\$toolset:(.+)$", item)
        if toolset_match:
            toolset_name = toolset_match.group(1)
            if toolset_name not in toolsets:
                continue

            toolset = toolsets[toolset_name]
            platform_key = f"tools_{clean_name}"
            platform_key_alt = f"tools_{alt_name}"

            tools = None
            if platform_key in toolset:
                tools = toolset[platform_key]
            elif platform_key_alt in toolset:
                tools = toolset[platform_key_alt]
            elif "tools" in toolset:
                tools = toolset["tools"]

            if isinstance(tools, list):
                for tool in tools:
                    if tool not in expanded:
                        expanded.append(tool)
        else:
            if item not in expanded:
                expanded.append(item)

    quoted = [f"'{t}'" for t in expanded]
    return "[" + ", ".join(quoted) + "]"
