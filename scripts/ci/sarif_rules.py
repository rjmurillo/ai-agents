"""Resolve the SARIF reporting rule and effective level for a result.

``check_codeql_sarif.py`` grades findings with these helpers. A result may
name its rule by id, by index into a tool component, or through a
``toolComponent`` reference, and may inherit its level from the rule.
"""

from __future__ import annotations


def dig(container: object, *keys: str) -> object:
    """Walk nested mappings, returning None as soon as a level is not a mapping."""
    for key in keys:
        if not isinstance(container, dict):
            return None
        container = container.get(key)
    return container


def _indexed(items: object, index: object) -> dict[str, object] | None:
    if isinstance(items, list) and type(index) is int and 0 <= index < len(items):
        item = items[index]
        if isinstance(item, dict):
            return item
    return None


def _rule_components(tool: object, reference: object) -> list[object]:
    """Select the referenced SARIF tool component or search driver first."""
    driver = dig(tool, "driver")
    extensions = dig(tool, "extensions")
    components = extensions if isinstance(extensions, list) else []
    if not isinstance(reference, dict):
        return [driver, *components]
    indexed = _indexed(components, reference.get("index"))
    if indexed is not None:
        return [indexed]
    for key in ("guid", "name"):
        identity = reference.get(key)
        if isinstance(identity, str):
            return [c for c in [driver, *components] if dig(c, key) == identity]
    return [driver]


def resolve_rule(tool: object, result: dict[str, object]) -> tuple[object, object]:
    """Resolve the reporting descriptor and id for a SARIF result."""
    reference = result.get("rule")
    rule_id = result.get("ruleId", dig(reference, "id"))
    rule_index = result.get("ruleIndex", dig(reference, "index"))
    components = _rule_components(tool, dig(reference, "toolComponent"))
    if components:
        # Without a component reference, an index addresses the driver only.
        rule = _indexed(dig(components[0], "rules"), rule_index)
        if rule is not None:
            return rule, rule_id if rule_id is not None else rule.get("id")
    for component in components:
        rules = dig(component, "rules")
        if isinstance(rules, list) and isinstance(rule_id, str):
            for rule in rules:
                if dig(rule, "id") == rule_id:
                    return rule, rule_id
    return None, rule_id


def effective_level(result: dict[str, object], rule: object) -> object:
    if "level" in result:
        return result["level"]
    if result.get("kind", "fail") != "fail":
        return "none"
    default_level = dig(rule, "defaultConfiguration", "level")
    return default_level if default_level is not None else "warning"
