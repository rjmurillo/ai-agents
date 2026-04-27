#!/usr/bin/env python3
"""Validate Claude Code plugin manifests against Anthropic schema.

Catches the regression class introduced by PR #1773 where plugin.json
declared invalid `agents`/`skills`/`commands`/`hooks` shapes, breaking
plugin install for all consumers ("Validation errors: hooks: Invalid
input, agents: Invalid input").

Exit codes:
    0 - All manifests valid
    1 - One or more manifests invalid
    2 - Configuration or parse error
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

REQUIRED_KEYS = {"name"}
ALLOWED_KEYS = {
    "name",
    "version",
    "description",
    "author",
    "homepage",
    "repository",
    "license",
    "keywords",
    "commands",
    "agents",
    "skills",
    "hooks",
    "mcpServers",
}

VALID_HOOK_EVENTS = {
    "PreToolUse",
    "PostToolUse",
    "PostToolUseFailure",
    "Stop",
    "StopFailure",
    "SessionStart",
    "SessionEnd",
    "UserPromptSubmit",
    "UserPromptExpansion",
    "SubagentStart",
    "SubagentStop",
    "PermissionRequest",
    "PermissionDenied",
    "Notification",
    "PreCompact",
    "PostCompact",
    "TaskCreated",
    "TaskCompleted",
    "TeammateIdle",
    "WorktreeCreate",
    "WorktreeRemove",
    "ConfigChange",
    "CwdChanged",
    "FileChanged",
    "InstructionsLoaded",
    "Elicitation",
    "ElicitationResult",
    "Setup",
    "PostToolBatch",
}


def _validate_relative_path(field: str, item: str) -> list[str]:
    """Plugin manifest paths must be relative, prefixed with ./, no `..` traversal."""
    errors: list[str] = []
    if not item.startswith("./"):
        errors.append(
            f"`{field}`: path '{item}' must start with './' (relative to plugin root)"
        )
    if ".." in Path(item).parts:
        errors.append(f"`{field}`: path '{item}' must not contain '..' traversal")
    return errors


def _validate_path_field(name: str, value: object) -> list[str]:
    """A path field must be a string or list of strings, each rooted with './'."""
    if isinstance(value, str):
        return _validate_relative_path(name, value)
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        errors: list[str] = []
        for item in value:
            errors.extend(_validate_relative_path(name, item))
        return errors
    return [
        f"`{name}`: must be a string or array of strings (got {type(value).__name__}). "
        f"Omit this key to auto-discover from default `./{name}/` directory."
    ]


def _validate_hook_event_entries(event: str, entries: object) -> list[str]:
    """Each event maps to a list of matcher groups."""
    if not isinstance(entries, list):
        return [
            f"`hooks.{event}`: must be an array of matcher groups "
            f"(got {type(entries).__name__}). Use `hooks/hooks.json` for a "
            f"separate config file, or inline matcher objects here. "
            f"Pointing to a directory is invalid."
        ]
    errors: list[str] = []
    for idx, group in enumerate(entries):
        if not isinstance(group, dict):
            errors.append(
                f"`hooks.{event}[{idx}]`: must be an object with `hooks` array"
            )
            continue
        if "hooks" not in group or not isinstance(group["hooks"], list):
            errors.append(
                f"`hooks.{event}[{idx}].hooks`: required array of hook commands"
            )
            continue
        for hidx, hook in enumerate(group["hooks"]):
            if not isinstance(hook, dict):
                errors.append(
                    f"`hooks.{event}[{idx}].hooks[{hidx}]`: must be an object"
                )
                continue
            if hook.get("type") != "command":
                errors.append(
                    f"`hooks.{event}[{idx}].hooks[{hidx}].type`: must be 'command'"
                )
            if not isinstance(hook.get("command"), str):
                errors.append(
                    f"`hooks.{event}[{idx}].hooks[{hidx}].command`: required string"
                )
    return errors


def _validate_hooks(value: object) -> list[str]:
    """Hooks must be either a string path to a JSON file or an inline object.

    Rejects the dict-of-strings shape (`{event: "./hooks/Event"}`) that broke
    plugin install in PR #1773.
    """
    if isinstance(value, str):
        if not value.endswith(".json"):
            return [
                "`hooks`: string value must reference a `.json` file "
                f"(got '{value}'). Pointing to a directory is invalid."
            ]
        return _validate_relative_path("hooks", value)
    if not isinstance(value, dict):
        return [
            f"`hooks`: must be an object or string path (got {type(value).__name__})"
        ]
    errors: list[str] = []
    for event, entries in value.items():
        if event not in VALID_HOOK_EVENTS:
            errors.append(
                f"`hooks.{event}`: unknown hook event. "
                f"Valid: {sorted(VALID_HOOK_EVENTS)}"
            )
            continue
        if isinstance(entries, str):
            errors.append(
                f"`hooks.{event}`: string value '{entries}' is invalid. "
                f"Hook events must map to an array of matcher groups, "
                f"not a directory path. This was the PR #1773 regression."
            )
            continue
        errors.extend(_validate_hook_event_entries(event, entries))
    return errors


def validate_manifest(path: Path) -> list[str]:
    """Validate a single plugin.json file. Returns list of error messages."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"Manifest read error for '{path}': {exc}"]
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return [f"JSON parse error: {exc}"]

    if not isinstance(data, dict):
        return ["Top-level value must be an object"]

    errors: list[str] = []

    missing = REQUIRED_KEYS - data.keys()
    if missing:
        errors.append(f"Missing required keys: {sorted(missing)}")

    unknown = set(data.keys()) - ALLOWED_KEYS
    if unknown:
        errors.append(f"Unknown keys: {sorted(unknown)}")

    for path_field in ("agents", "skills", "commands"):
        if path_field in data:
            errors.extend(_validate_path_field(path_field, data[path_field]))

    if "hooks" in data:
        errors.extend(_validate_hooks(data["hooks"]))

    return errors


def find_manifests(root: Path) -> list[Path]:
    """Find all plugin.json files under .claude-plugin/ directories."""
    excluded_parts = {"worktrees", "node_modules", ".git", "cache"}
    results: list[Path] = []
    for candidate in root.rglob(".claude-plugin/plugin.json"):
        if any(part in excluded_parts for part in candidate.relative_to(root).parts):
            continue
        results.append(candidate)
    return sorted(results)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=REPO_ROOT,
        help="Repository root to scan (default: %(default)s)",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        action="append",
        help="Specific manifest path(s) to validate (skips discovery)",
    )
    args = parser.parse_args(argv)

    if args.manifest:
        manifests = list(args.manifest)
    else:
        manifests = find_manifests(args.root)

    if not manifests:
        print("No plugin.json files found", file=sys.stderr)
        return 2

    failures = 0
    for manifest in manifests:
        errors = validate_manifest(manifest)
        rel = manifest.relative_to(args.root) if manifest.is_relative_to(args.root) else manifest
        if errors:
            failures += 1
            print(f"FAIL {rel}")
            for err in errors:
                print(f"  - {err}")
        else:
            print(f"OK   {rel}")

    if failures:
        print(
            f"\n{failures} of {len(manifests)} manifest(s) invalid",
            file=sys.stderr,
        )
        return 1
    print(f"\nAll {len(manifests)} manifest(s) valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
