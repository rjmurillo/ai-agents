#!/usr/bin/env python3
"""Validate that marketplace.json plugin descriptions have accurate counts.

Counts agents, commands, hooks, and skills from source directories and
compares them against the counts embedded in marketplace.json descriptions.

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
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MARKETPLACE_JSON = REPO_ROOT / ".claude-plugin" / "marketplace.json"

# Maps plugin name to a dict of (label -> counting function).
# Each counting function returns an int.
PLUGIN_COUNTERS: dict[str, dict[str, callable]] = {}


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


def _count_agent_md(directory: Path) -> int:
    """Count .agent.md files in a directory."""
    return sum(1 for f in directory.glob("*.agent.md") if f.is_file())


def _count_commands(directory: Path) -> int:
    """Count command .md files recursively, excluding CLAUDE.md."""
    return sum(
        1
        for f in directory.rglob("*.md")
        if f.is_file() and f.name != "CLAUDE.md"
    )


def _count_hooks(directory: Path) -> int:
    """Count hook .py scripts (all levels)."""
    return sum(1 for f in directory.rglob("*.py") if f.is_file())


def _count_skill_dirs(directory: Path) -> int:
    """Count immediate subdirectories (each is a skill)."""
    return sum(1 for d in directory.iterdir() if d.is_dir())


PLUGIN_COUNTERS["claude-agents"] = {
    "agent": lambda: _count_md_agents(
        REPO_ROOT / "src" / "claude",
        exclude={"AGENTS.md"},
    ),
}

PLUGIN_COUNTERS["copilot-cli-agents"] = {
    "agent": lambda: _count_agent_md(REPO_ROOT / "src" / "copilot-cli"),
}

PLUGIN_COUNTERS["project-toolkit"] = {
    "agent": lambda: _count_md_agents(
        REPO_ROOT / ".claude" / "agents",
        exclude={"AGENTS.md", "CLAUDE.md"},
    ),
    "slash command": lambda: _count_commands(REPO_ROOT / ".claude" / "commands"),
    "lifecycle hook": lambda: _count_hooks(REPO_ROOT / ".claude" / "hooks"),
    "reusable skill": lambda: _count_skill_dirs(REPO_ROOT / ".claude" / "skills"),
}

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


def validate(fix: bool = False) -> int:
    """Validate marketplace.json counts. Returns 0 on success, 1 on mismatch."""
    if not MARKETPLACE_JSON.exists():
        print(f"Error: {MARKETPLACE_JSON} not found", file=sys.stderr)
        return 2

    with open(MARKETPLACE_JSON) as f:
        data = json.load(f)

    plugins = data.get("plugins", [])
    mismatches: list[str] = []
    fixes: dict[str, str] = {}

    for plugin in plugins:
        name = plugin.get("name", "")
        description = plugin.get("description", "")
        counters = PLUGIN_COUNTERS.get(name)
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
                # Build fixed description by replacing the old count.
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
        print("marketplace.json counts are up to date.")
        return 0

    print("Stale counts detected in marketplace.json:")
    for msg in mismatches:
        print(msg)

    if fix:
        for plugin in plugins:
            if plugin["name"] in fixes:
                plugin["description"] = fixes[plugin["name"]]
        with open(MARKETPLACE_JSON, "w") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        print("\nFixed: marketplace.json updated with correct counts.")
        return 0

    print("\nRun with --fix to update marketplace.json automatically.")
    return 1


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate marketplace.json plugin description counts."
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Automatically fix stale counts in marketplace.json.",
    )
    args = parser.parse_args()
    sys.exit(validate(fix=args.fix))


if __name__ == "__main__":
    main()
