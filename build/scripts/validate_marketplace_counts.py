#!/usr/bin/env python3
"""Validate that marketplace.json plugin descriptions have accurate counts.

Counts agents, commands, hooks, and skills from source directories and
compares them against the counts embedded in marketplace.json descriptions.

The plugin -> (label, strategy, sourceDir, exclude) mapping lives in
templates/marketplace-counters.yaml so adding a new plugin requires no
Python edits (REQ-003-004). Strategies remain Python because they are
reusable building blocks across plugins.

Exit codes:
    0 - All counts match
    1 - One or more counts are stale
    2 - Configuration or parse error
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Callable
from pathlib import Path

from yaml_loader import ConfigError, load_platform_config

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MARKETPLACE_JSON = REPO_ROOT / ".claude-plugin" / "marketplace.json"
COPILOT_MARKETPLACE_JSON = REPO_ROOT / ".github" / "plugin" / "marketplace.json"
COUNTERS_YAML = REPO_ROOT / "templates" / "marketplace-counters.yaml"


# --- Counter strategies (reusable building blocks) -----------------------


# Directories pruned during recursive walks. Same set as
# validate_plugin_manifests.py (PR #1795); prevents CI hang on
# large vendored trees or symlink loops.
_EXCLUDED_DIRS = frozenset({"node_modules", ".git", "worktrees", "cache", "__pycache__"})


def _walk_files(directory: Path, suffix: str, exclude_names: set[str]) -> int:
    """Count files matching suffix, pruning EXCLUDED_DIRS during descent.

    Replaces ``directory.rglob('*.suffix')`` which walks excluded subtrees
    before discarding matches. ``os.walk`` with in-place ``dirnames`` mutation
    prunes BEFORE descending — safe against vendored bloat and symlink loops.
    """
    import os

    count = 0
    for dirpath, dirnames, filenames in os.walk(directory):
        dirnames[:] = [d for d in dirnames if d not in _EXCLUDED_DIRS]
        for name in filenames:
            if name.endswith(suffix) and name not in exclude_names:
                count += 1
    return count


def _count_md_agents(directory: Path, exclude: set[str] | None = None) -> int:
    """Count .md files in a directory, excluding specific filenames."""
    exclude = exclude or set()
    return sum(
        1
        for f in directory.iterdir()
        if f.is_file()
        and f.suffix == ".md"
        and f.name not in exclude
        and "template" not in f.name
    )


def _count_agent_md(directory: Path, exclude: set[str] | None = None) -> int:
    """Count .agent.md files in a directory, excluding specific filenames."""
    exclude = exclude or set()
    return sum(
        1
        for f in directory.glob("*.agent.md")
        if f.is_file() and f.name not in exclude
    )


def _count_commands(directory: Path, exclude: set[str] | None = None) -> int:
    """Count command .md files recursively, excluding specific filenames.

    Walks pruning EXCLUDED_DIRS; safe against vendored subtrees.
    Defaults to excluding CLAUDE.md if no exclude set is provided.
    """
    exclude = exclude if exclude is not None else {"CLAUDE.md"}
    return _walk_files(directory, ".md", exclude)


def _count_hooks(directory: Path, exclude: set[str] | None = None) -> int:
    """Count hook .py scripts (all levels), pruning EXCLUDED_DIRS."""
    exclude = exclude or set()
    return _walk_files(directory, ".py", exclude)


def _count_skill_dirs(directory: Path, exclude: set[str] | None = None) -> int:
    """Count immediate subdirectories (each is a skill), excluding specific names."""
    exclude = exclude or set()
    return sum(1 for d in directory.iterdir() if d.is_dir() and d.name not in exclude)


# Strategy registry. Add new keys ONLY when introducing a fundamentally
# new counting algorithm; per-plugin mapping belongs in marketplace-counters.yaml.
STRATEGIES: dict[str, Callable[[Path, set[str] | None], int]] = {
    "md_agents": _count_md_agents,
    "agent_md": _count_agent_md,
    "commands": _count_commands,
    "hooks": _count_hooks,
    "skill_dirs": _count_skill_dirs,
}


# --- Config loading -------------------------------------------------------


def _build_counter(rule: dict, repo_root: Path) -> Callable[[], int]:
    """Bind one (strategy, sourceDir, exclude?) rule into a zero-arg counter."""
    strategy_name = rule.get("strategy")
    source_dir = rule.get("sourceDir")
    if strategy_name not in STRATEGIES:
        raise ConfigError(
            f"unknown strategy '{strategy_name}'. "
            f"Registered: {sorted(STRATEGIES)}"
        )
    if not isinstance(source_dir, str) or not source_dir:
        raise ConfigError(
            f"strategy '{strategy_name}': sourceDir must be a non-empty string"
        )
    exclude_raw = rule.get("exclude")
    exclude: set[str] | None = None
    if exclude_raw is not None:
        if not isinstance(exclude_raw, list) or not all(
            isinstance(x, str) for x in exclude_raw
        ):
            raise ConfigError(
                f"strategy '{strategy_name}': exclude must be a list of strings"
            )
        exclude = set(exclude_raw)
    fn = STRATEGIES[strategy_name]
    target = repo_root / source_dir
    if not target.exists():
        raise ConfigError(
            f"strategy '{strategy_name}': sourceDir '{source_dir}' "
            f"does not exist (resolved to '{target}')"
        )
    return lambda: fn(target, exclude)


def load_plugin_counters(
    config_path: Path = COUNTERS_YAML,
    repo_root: Path = REPO_ROOT,
    marketplace_path: Path | None = None,
) -> dict[str, dict[str, Callable[[], int]]]:
    """Load plugin -> {label -> counter-fn} mapping from YAML.

    Supports either a direct label -> rule mapping, or a nested
    marketplaces.<relative-marketplace-path>.<label> -> rule mapping for cases
    where the same plugin name exists in multiple native marketplace manifests
    with platform-specific payloads.
    """
    data = load_platform_config(config_path)
    plugins = data.get("plugins")
    if not isinstance(plugins, dict):
        raise ConfigError(
            f"{config_path}: top-level `plugins` must be a mapping"
        )

    marketplace_key: str | None = None
    if marketplace_path is not None:
        try:
            marketplace_key = str(marketplace_path.resolve().relative_to(repo_root))
        except ValueError:
            marketplace_key = str(marketplace_path)

    counters: dict[str, dict[str, Callable[[], int]]] = {}
    for plugin_name, labels in plugins.items():
        if not isinstance(labels, dict):
            raise ConfigError(
                f"plugins.{plugin_name}: must be a mapping of label -> rule"
            )

        rules = labels
        marketplaces = labels.get("marketplaces")
        if marketplaces is not None:
            if not isinstance(marketplaces, dict):
                raise ConfigError(
                    f"plugins.{plugin_name}.marketplaces: must be a mapping"
                )
            if marketplace_key is None:
                raise ConfigError(
                    f"plugins.{plugin_name}.marketplaces requires marketplace_path"
                )
            rules = marketplaces.get(marketplace_key)
            if rules is None:
                continue
            if not isinstance(rules, dict):
                raise ConfigError(
                    f"plugins.{plugin_name}.marketplaces.{marketplace_key}: must be a mapping"
                )

        per_label: dict[str, Callable[[], int]] = {}
        for label, rule in rules.items():
            if not isinstance(rule, dict):
                raise ConfigError(
                    f"plugins.{plugin_name}.{label}: must be a mapping"
                )
            per_label[label] = _build_counter(rule, repo_root)
        counters[plugin_name] = per_label
    return counters


# --- Description parsing --------------------------------------------------


# Pattern: captures a number followed by a label.
# Example: "23 specialized agent definitions" -> (23, "agent")
# Example: "12 slash commands" -> (12, "slash command")
COUNT_PATTERN = re.compile(
    r"(\d+)\s+"
    r"(specialized\s+agent\s+definition"
    r"|agent\s+definition"
    r"|agent"
    r"|slash\s+command"
    r"|lifecycle\s+hook"
    r"|reusable\s+skill)"
    r"s?"
)

# Map matched label text to the counter key.
LABEL_MAP = {
    "specialized agent definition": "agent",
    "agent definition": "agent",
    "agent": "agent",
    "slash command": "slash command",
    "lifecycle hook": "lifecycle hook",
    "reusable skill": "reusable skill",
}


def parse_counts_from_description(description: str) -> dict[str, int]:
    """Extract (label -> count) pairs from a plugin description string."""
    results = {}
    for match in COUNT_PATTERN.finditer(description):
        count_str, label_text = match.group(1), match.group(2)
        key = LABEL_MAP.get(label_text)
        if key:
            results[key] = int(count_str)
    return results


# --- Validation -----------------------------------------------------------


def validate(
    fix: bool = False,
    counters_path: Path = COUNTERS_YAML,
    marketplace_path: Path | None = None,
    repo_root: Path = REPO_ROOT,
) -> int:
    """Validate marketplace.json counts. Returns 0 success, 1 mismatch, 2 config."""
    marketplace = marketplace_path or MARKETPLACE_JSON
    if not marketplace.exists():
        print(f"Error: {marketplace} not found", file=sys.stderr)
        return 2

    with open(marketplace) as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            print(f"Error: Failed to parse {marketplace}: {e}", file=sys.stderr)
            return 2

    try:
        plugin_counters = load_plugin_counters(counters_path, repo_root, marketplace)
    except ConfigError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    plugins = data.get("plugins", [])
    mismatches: list[str] = []
    fixes: dict[str, str] = {}

    for plugin in plugins:
        name = plugin.get("name", "")
        description = plugin.get("description", "")
        counters = plugin_counters.get(name)
        if not counters:
            continue

        declared = parse_counts_from_description(description)
        new_description = description

        for label, counter_fn in counters.items():
            actual = counter_fn()
            expected = declared.get(label)

            if expected is None:
                print(f"  Warning: no count found for '{label}' in {name}")
                continue

            if actual != expected:
                mismatches.append(
                    f"  {name}: '{label}' declared={expected}, actual={actual}"
                )
                for match in COUNT_PATTERN.finditer(new_description):
                    matched_label = LABEL_MAP.get(match.group(2))
                    if matched_label == label:
                        old_text = match.group(0)
                        new_text = old_text.replace(
                            match.group(1), str(actual), 1
                        )
                        new_description = new_description.replace(
                            old_text, new_text, 1
                        )

        if new_description != description:
            fixes[name] = new_description

    if not mismatches:
        try:
            display_path = marketplace.relative_to(repo_root)
        except ValueError:
            display_path = marketplace
        print(f"{display_path} counts are up to date.")
        return 0

    try:
        display_path = marketplace.relative_to(repo_root)
    except ValueError:
        display_path = marketplace

    print(f"Stale counts detected in {display_path}:")
    for msg in mismatches:
        print(msg)

    if fix:
        for plugin in plugins:
            if plugin["name"] in fixes:
                plugin["description"] = fixes[plugin["name"]]
        with open(marketplace, "w") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        print(f"\nFixed: {display_path} updated with correct counts.")
        return 0

    print("\nRun with --fix to update marketplace.json automatically.")
    return 1


def validate_known_marketplaces(
    fix: bool = False,
    counters_path: Path = COUNTERS_YAML,
    repo_root: Path = REPO_ROOT,
) -> int:
    """Validate all native marketplace manifests shipped by the repo."""
    results = []
    for marketplace in (MARKETPLACE_JSON, COPILOT_MARKETPLACE_JSON):
        result = validate(
            fix=fix,
            counters_path=counters_path,
            marketplace_path=marketplace,
            repo_root=repo_root,
        )
        results.append(result)
    if any(result == 2 for result in results):
        return 2
    if any(result == 1 for result in results):
        return 1
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate marketplace.json plugin description counts."
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Automatically fix stale counts in marketplace.json.",
    )
    parser.add_argument(
        "--marketplace",
        type=Path,
        help="Validate one specific marketplace.json instead of all native marketplaces.",
    )
    args = parser.parse_args()

    if args.marketplace is not None:
        sys.exit(validate(fix=args.fix, marketplace_path=args.marketplace.resolve()))

    sys.exit(validate_known_marketplaces(fix=args.fix))


if __name__ == "__main__":
    main()
