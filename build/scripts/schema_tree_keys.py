"""Schema checks for the tree-copy keys ADR-115 Decision 2 added.

Split from validate_templates_schema.py for the taste-lint file-size ceiling.

``artifacts.rules.outputFormat``, ``artifacts.skills.frontmatterKeep``,
``artifacts.agents.frontmatterKeep``, and ``artifacts.agents.deriveReadonly``.
Each function returns error strings; an empty list is valid.
"""

from __future__ import annotations

# `instructions` is the default and today's Copilot output; `cursor-mdc` writes
# Cursor `.mdc` rules. generate_rules.py imports this tuple, so there is one list.
RULES_OUTPUT_FORMATS = ("instructions", "cursor-mdc")


def validate_string_list(name: str, stanza: dict[str, object], key: str) -> list[str]:
    if key not in stanza:
        return []
    value = stanza[key]
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return [f"`artifacts.{name}.{key}`: must be a list of strings"]
    return []


def validate_rules_output_format(name: str, stanza: dict[str, object]) -> list[str]:
    if "outputFormat" not in stanza:
        return []
    value = stanza["outputFormat"]
    if not isinstance(value, str) or value not in RULES_OUTPUT_FORMATS:
        return [
            f"`artifacts.{name}.outputFormat`: must be one of {list(RULES_OUTPUT_FORMATS)} "
            f"(got {value!r})"
        ]
    return []


def validate_frontmatter_keep(name: str, stanza: dict[str, object]) -> list[str]:
    """Check the allow-list key on a skills or agents stanza (ADR-115 Decision 2).

    An allow-list is non-empty: an empty one would strip the required `name`
    and `description` and ship a tree the host cannot load. On skills it is
    mutually exclusive with `frontmatterDrop`, because two cuts of one block
    leave the result order-dependent.
    """
    if "frontmatterKeep" not in stanza:
        return []
    errors = validate_string_list(name, stanza, "frontmatterKeep")
    keep = stanza["frontmatterKeep"]
    if not errors and not keep:
        errors.append(f"`artifacts.{name}.frontmatterKeep`: must not be empty")
    if "frontmatterDrop" in stanza:
        errors.append(
            f"`artifacts.{name}`: `frontmatterKeep` and `frontmatterDrop` are mutually exclusive"
        )
    return errors


def validate_agents_tree_copy(name: str, stanza: dict[str, object]) -> list[str]:
    """Check the agent tree-copy keys (ADR-115 Decision 2).

    `frontmatterKeep` turns on the `src/claude/agents` copy
    (`agent_tree_copy.py`), which reads `sourceDir` and writes `outputDir`, so
    both are required with it. `deriveReadonly` has no meaning without it.
    """
    errors: list[str] = []
    if "deriveReadonly" in stanza and not isinstance(stanza["deriveReadonly"], bool):
        errors.append(f"`artifacts.{name}.deriveReadonly`: must be a boolean")
    if "frontmatterKeep" not in stanza:
        if "deriveReadonly" in stanza:
            errors.append(f"`artifacts.{name}.deriveReadonly`: requires `frontmatterKeep`")
        return errors
    errors.extend(validate_frontmatter_keep(name, stanza))
    for required in ("sourceDir", "outputDir"):
        if required not in stanza:
            errors.append(f"`artifacts.{name}.frontmatterKeep`: requires `{required}`")
    return errors
