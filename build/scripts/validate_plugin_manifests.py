#!/usr/bin/env python3
"""Validate Claude Code plugin manifests against Anthropic schema.

Catches the regression class introduced by PR #1776 where plugin.json
declared invalid `agents`/`skills`/`commands`/`hooks` shapes, breaking
plugin install for all consumers ("Validation errors: hooks: Invalid
input, agents: Invalid input").

Exit codes:
    0 - All manifests valid
    1 - One or more manifests invalid (includes JSON parse and read errors)
    2 - No plugin.json files found (discovery returned empty)
"""

from __future__ import annotations

import argparse
import json
import re
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
    "dependencies",
}

# Documented in Anthropic plugin hooks reference and observed in production
# plugins (caveman, context-mode, security-guidance). Speculative/undocumented
# events are deliberately excluded so an obvious typo (e.g. SessionStarted)
# fails CI rather than silently never firing. Re-extend only with citation.
VALID_HOOK_EVENTS = {
    "PreToolUse",
    "PostToolUse",
    "Stop",
    "SessionStart",
    "SessionEnd",
    "UserPromptSubmit",
    "SubagentStop",
    "PermissionRequest",
    "Notification",
    "PreCompact",
}


def _validate_relative_path(field: str, item: str) -> list[str]:
    """Plugin manifest paths must be relative, prefixed with ./, no `..` traversal."""
    errors: list[str] = []
    if not item.startswith("./"):
        errors.append(f"`{field}`: path '{item}' must start with './' (relative to plugin root)")
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


# ADR-072 Decision 3, measured 2026-09-09 against Claude Code 2.1.266:
# `dependencies` is a first-class, type-checked manifest field, and
# `dependencies: "nope"` produces `dependencies: Invalid input` and fails
# validation on the real host. This gate must not be looser than that, so a
# non-list value or a list containing a non-string is rejected below.
#
# ADR-092 (accepted, implemented) deleted `version` from all three packaged
# plugin manifests and `build/scripts/validate_plugin_version_bump.py` fails
# when the field reappears, so a dependency here can only ever be a bare
# plugin name or `name@marketplace`, never version-constrained. This matches
# `@` followed by a digit (`cap-b@1.2.3`), the comparison and equality
# operators, `~`, and `^` followed by a digit. It does not match
# `name@marketplace` (an alias, not a version), which ADR-072's reversibility
# section measures as the valid multi-entry-marketplace form.
#
# `<`, `<=` and `!=` are here because an earlier revision listed only
# `@\d`, `==`, `>=`, `~` and `^\d`, which let `cap-b<2.0.0` through as a bare
# name and so contradicted the stated intent that any version specifier is
# rejected. Found by the ADR-072 round 4 security seat. Bare `<` and `>` are
# safe to reject outright because no plugin name may contain them.
_DEPENDENCY_VERSION_SPECIFIER_RE = re.compile(r"@\d|==|!=|>=|<=|>|<|~|\^\d")


def _validate_dependencies(value: object) -> list[str]:
    """`dependencies` must be a list of bare plugin names or `name@marketplace` strings.

    An empty list is valid (declaring no cross-plugin dependencies is not an
    error). Each non-empty entry must not carry leading/trailing whitespace,
    must not be empty or whitespace-only, and must not be version-constrained
    (see `_DEPENDENCY_VERSION_SPECIFIER_RE` above for why).
    """
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return [f"`dependencies`: must be an array of strings (got {type(value).__name__})"]
    errors: list[str] = []
    for item in value:
        if not item.strip():
            errors.append(
                f"`dependencies`: entry must not be empty or whitespace-only (got {item!r})"
            )
            continue
        if item != item.strip():
            errors.append(
                f"`dependencies`: entry {item!r} must not have leading or trailing whitespace"
            )
            continue
        if _DEPENDENCY_VERSION_SPECIFIER_RE.search(item):
            errors.append(
                f"`dependencies`: entry '{item}' must not be version-constrained. "
                f"ADR-092 deleted `version` from every packaged manifest; use a "
                f"bare plugin name or `name@marketplace` instead."
            )
    return errors


# Measured against Claude Code 2.1.122 (commit a4ed5850c, 2026-05-01). Re-probed
# on 2.1.266 (2026-09-09): `claude plugin validate` accepts explicit `skills` and
# `commands` path keys, and an unrecognized key only warns ("Claude Code ignores
# it at load time") while a wrong-typed known key hard-fails, so the two are
# distinguishable. The narrow rejection this constant guards was NOT re-probed
# against a real marketplace install, so the guard stays until someone does that.
#
# Read the version as the date of a measurement, not as a standing platform law.
# Five of six reviewers in the 2026-09-09 ADR-072 round read this comment as the
# latter and blocked a decision on it. The check is also narrower than it reads:
# _is_repo_marketplace_manifest matches three hardcoded paths, so a plugin root
# anywhere else is unaffected.
#
# Claude Code 2.1.122 rejects explicit discovery keys in the manifests shipped
# by this repo's marketplace, even though the published schema still documents
# these fields. Auto-discovery works when the keys are omitted.
_MARKETPLACE_RUNTIME_FORBIDDEN_KEYS = ("agents", "skills", "commands", "hooks")


def _is_repo_marketplace_manifest(path: Path) -> bool:
    """Return True when a manifest belongs to this repo's shipped marketplace."""
    normalized = path.resolve().parts
    patterns = (
        (".claude", ".claude-plugin", "plugin.json"),
        ("src", "claude", ".claude-plugin", "plugin.json"),
        ("src", "copilot-cli", ".claude-plugin", "plugin.json"),
    )
    return any(normalized[-len(pattern) :] == pattern for pattern in patterns)


def _check_marketplace_runtime_forbidden_keys(path: Path, manifest: dict[str, object]) -> list[str]:
    """Reject discovery keys for this repo's marketplace manifests.

    Issue #1833 reproduces on the plugin manifests shipped by this repository.
    Those installs succeed when Claude Code auto-discovers the default
    locations and fail when these keys are declared explicitly.
    """
    if not _is_repo_marketplace_manifest(path):
        return []
    present = [k for k in _MARKETPLACE_RUNTIME_FORBIDDEN_KEYS if k in manifest]
    if not present:
        return []
    keys = ", ".join(f"`{k}`" for k in present)
    return [
        f"{keys}: rejected for this repo's Claude marketplace manifests. "
        f"Claude Code 2.1.122 rejects explicit discovery keys for the marketplace "
        f"entries backed by `.claude/`, `src/claude/`, and `src/copilot-cli/`; "
        f"omit them and rely on auto-discovery instead. See issue #1833."
    ]


def _validate_hook_group(event: str, idx: int, group: object) -> list[str]:
    """Validate one matcher group (an object with a `hooks` array)."""
    if not isinstance(group, dict):
        return [f"`hooks.{event}[{idx}]`: must be an object with `hooks` array"]
    if "hooks" not in group or not isinstance(group["hooks"], list):
        return [f"`hooks.{event}[{idx}].hooks`: required array of hook commands"]
    errors: list[str] = []
    for hidx, hook in enumerate(group["hooks"]):
        if not isinstance(hook, dict):
            errors.append(f"`hooks.{event}[{idx}].hooks[{hidx}]`: must be an object")
            continue
        if hook.get("type") != "command":
            errors.append(f"`hooks.{event}[{idx}].hooks[{hidx}].type`: must be 'command'")
        if not isinstance(hook.get("command"), str):
            errors.append(f"`hooks.{event}[{idx}].hooks[{hidx}].command`: required string")
    return errors


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
        errors.extend(_validate_hook_group(event, idx, group))
    return errors


def _validate_referenced_hooks_doc(value: str, inner: object) -> list[str]:
    """Validate the parsed contents of a referenced hooks JSON file."""
    if not isinstance(inner, dict):
        return [f"`hooks`: referenced file '{value}' must be a JSON object"]
    # The canonical hooks.json shape (per production plugins context-mode and
    # security-guidance) wraps event names under a top-level "hooks" key.
    # Without the wrapper, Claude Code does not load the events. Enforce strictly.
    if "hooks" not in inner:
        return [
            f"`hooks`: referenced file '{value}' must contain a top-level "
            f"`hooks` key wrapping the event names "
            f'(e.g. {{"hooks": {{"PreToolUse": [...]}}}}). '
            f"Without the wrapper, Claude Code does not load the events."
        ]
    events_obj = inner["hooks"]
    if not isinstance(events_obj, dict):
        return [
            f"`hooks`: referenced file '{value}' top-level `hooks` value "
            f"must be an object of event names"
        ]
    nested_errors: list[str] = []
    for event, entries in events_obj.items():
        if event not in VALID_HOOK_EVENTS:
            nested_errors.append(f"`hooks` ref '{value}': unknown hook event '{event}'")
            continue
        nested_errors.extend(_validate_hook_event_entries(event, entries))
    return nested_errors


def _validate_hooks_string_ref(value: str, manifest_dir: Path | None) -> list[str]:
    """Validate a `hooks` string ref to a JSON file and its referenced contents."""
    if not value.endswith(".json"):
        return [
            "`hooks`: string value must reference a `.json` file "
            f"(got '{value}'). Pointing to a directory is invalid."
        ]
    errors = _validate_relative_path("hooks", value)
    if errors or manifest_dir is None:
        return errors
    # The plugin root is the directory containing .claude-plugin/, i.e.
    # the parent of manifest_dir. Hook string refs are relative to root.
    plugin_root = manifest_dir.parent.resolve()
    referenced = (plugin_root / value).resolve()
    if not referenced.is_relative_to(plugin_root):
        return [f"`hooks`: path '{value}' escapes the plugin root directory"]
    if not referenced.exists():
        return errors  # Don't fail if path is just unresolvable here.
    try:
        inner = json.loads(referenced.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return [f"`hooks`: referenced file '{value}' is unreadable: {exc}"]
    return _validate_referenced_hooks_doc(value, inner)


def _validate_hooks_inline(value: dict[str, object]) -> list[str]:
    """Validate an inline `hooks` object mapping event names to matcher groups."""
    inline_errors: list[str] = []
    for event, entries in value.items():
        if event not in VALID_HOOK_EVENTS:
            inline_errors.append(
                f"`hooks.{event}`: unknown hook event. Valid: {sorted(VALID_HOOK_EVENTS)}"
            )
            continue
        if isinstance(entries, str):
            inline_errors.append(
                f"`hooks.{event}`: string value '{entries}' is invalid. "
                f"Hook events must map to an array of matcher groups, "
                f"not a directory path. This was the PR #1776 regression."
            )
            continue
        inline_errors.extend(_validate_hook_event_entries(event, entries))
    return inline_errors


def _validate_hooks(value: object, manifest_dir: Path | None = None) -> list[str]:
    """Hooks must be either a string path to a JSON file or an inline object.

    Rejects the dict-of-strings shape (`{event: "./hooks/Event"}`) that broke
    plugin install in PR #1776. When `value` is a string ref and `manifest_dir`
    is provided, the referenced file is also loaded and its contents validated.
    """
    if isinstance(value, str):
        return _validate_hooks_string_ref(value, manifest_dir)
    if not isinstance(value, dict):
        return [f"`hooks`: must be an object or string path (got {type(value).__name__})"]
    return _validate_hooks_inline(value)


def _validate_manifest_data(data: dict[str, object], path: Path) -> list[str]:
    """Validate the parsed manifest object. Returns list of error messages.

    Split out of validate_manifest so each stays within the cyclomatic-complexity
    budget; validate_manifest handles read/parse, this handles field semantics.
    """
    errors: list[str] = []

    missing = REQUIRED_KEYS - data.keys()
    name = data.get("name")
    if missing:
        errors.append(f"Missing required keys: {sorted(missing)}")
    elif not isinstance(name, str) or not name.strip():
        errors.append(f"`name`: must be a non-empty string (got {type(name).__name__})")

    unknown = set(data.keys()) - ALLOWED_KEYS
    if unknown:
        errors.append(f"Unknown keys: {sorted(unknown)}")

    errors.extend(_check_marketplace_runtime_forbidden_keys(path, data))

    for path_field in ("agents", "skills", "commands"):
        if path_field in data:
            errors.extend(_validate_path_field(path_field, data[path_field]))

    if "hooks" in data:
        errors.extend(_validate_hooks(data["hooks"], manifest_dir=path.parent))

    if "dependencies" in data:
        errors.extend(_validate_dependencies(data["dependencies"]))

    return errors


def validate_manifest(path: Path) -> list[str]:
    """Validate a single plugin.json file. Returns list of error messages."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"Manifest read error for '{path}': {exc}"]
    except UnicodeDecodeError as exc:
        return [f"Manifest decode error for '{path}': {exc}"]
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return [f"JSON parse error: {exc}"]

    if not isinstance(data, dict):
        return ["Top-level value must be an object"]

    return _validate_manifest_data(data, path)


def find_manifests(root: Path) -> list[Path]:
    """Find all plugin.json files under `.claude-plugin/` directories.

    Uses an os.walk-based traversal that prunes excluded directories
    BEFORE descending. This avoids the rglob trap of walking through
    `node_modules/`, `.git/`, etc. just to discard the candidates after.
    """
    import os

    excluded_dirs = {
        ".agent-tmp",
        ".worktrees",
        "worktrees",
        "node_modules",
        ".git",
        "cache",
        ".pytest_cache",
        ".pytest_tmp",
    }
    results: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune excluded directories in-place so os.walk does not descend.
        dirnames[:] = [d for d in dirnames if d not in excluded_dirs]
        if Path(dirpath).name == ".claude-plugin" and "plugin.json" in filenames:
            results.append(Path(dirpath) / "plugin.json")
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
