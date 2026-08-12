#!/usr/bin/env python3
"""Validate templates/platforms/*.yaml against REQ-003-002 schema.

Enforces ADR-006 Amendment 2026-04-28 conditions on build-pipeline YAML:
- safe_load only (no Python tags, no anchors, no aliases)
- schemaVersion SemVer compatibility (current supported: ^1.x)
- allowed top-level keys + per-artifact-type dispatch
- path traversal rejection (REQ-003-009)
- structural complexity limits (list-of-objects key cap, file size cap)

Exit codes:
    0 - All YAML files valid
    1 - One or more invalid
    2 - Config error (missing file, parse error, schemaVersion mismatch,
        path traversal, anchor/alias detected, file too large)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path, PurePosixPath

from yaml_loader import (
    ConfigError,
    load_platform_config,
    validate_relative_path,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# Top-level schema --------------------------------------------------------

ALLOWED_TOP_LEVEL = {"schemaVersion", "provider", "artifacts", "auditPolicy", "legacy"}
REQUIRED_TOP_LEVEL = {"schemaVersion", "provider"}

# Compatibility window: major version 1 with any minor.
SUPPORTED_MAJOR = 1

# Structural complexity limits (ADR-006 Amendment 2026-04-28).
# Nesting depth limit dropped per amendment-of-amendment: aesthetic only,
# caught nothing line-count + list-key-cap don't, and the canonical
# REQ-003-002 schema needs depth 4 for legitimate two-level mappings.
MAX_LIST_OBJECT_KEYS = 2
MAX_FILE_LINES = 200

# Per-artifact stanza shapes. Keys are required-or-allowed sets only;
# value-shape checks are inline so error messages stay informative.
AGENTS_KEYS = {
    "sourceDir",
    "outputDir",
    "sourceSuffix",
    "outputSuffix",
    "excludeFilenames",
}
SKILLS_KEYS = {"sourceDir", "outputDir", "mode", "excludeFilenames"}
# `lib` only supports directory-copy today; no `mode` selector. If a
# second mode (symlink, etc.) lands later, add `mode` to LIB_KEYS and
# enforce it in `_build_lib`. Until then, an unused field is documentation
# rot.
LIB_KEYS = {"sourceDir", "outputDir"}
COMMANDS_KEYS = {
    "sourceDir",
    "outputDir",
    "resourceOutputDir",
    "resourceSuffixes",
    "transform",
    "appendFrontmatter",
    "excludeFilenames",
}
RULES_KEYS = {
    "sourceDir",
    "outputDir",
    "outputDirs",
    "sourceSuffix",
    "outputSuffix",
    "frontmatterRemap",
    "frontmatterDrop",
    "keepInternalGlobsFor",
}
HOOKS_KEYS = {
    "settingsSource",
    "scriptSource",
    "outputConfig",
    "outputScripts",
    "eventRemap",
    "eventDrop",
    "matcherPolicy",
    "versionField",
    "dispatcher",
}
ARTIFACT_DISPATCH = {
    "agents": AGENTS_KEYS,
    "skills": SKILLS_KEYS,
    "commands": COMMANDS_KEYS,
    "rules": RULES_KEYS,
    "lib": LIB_KEYS,
    "hooks": HOOKS_KEYS,
}

PATH_FIELDS_BY_ARTIFACT = {
    "agents": ("sourceDir", "outputDir"),
    "skills": ("sourceDir", "outputDir"),
    "commands": ("sourceDir", "outputDir", "resourceOutputDir"),
    "rules": ("sourceDir", "outputDir"),
    "lib": ("sourceDir", "outputDir"),
    "hooks": ("settingsSource", "scriptSource", "outputConfig", "outputScripts"),
}

AUDIT_POLICY_KEYS = {"pathBlocklist", "output"}


# --- Path safety (delegates to yaml_loader.validate_relative_path) -------


def _validate_path_value(field: str, value: object) -> list[str]:
    """Backwards-compat wrapper around yaml_loader.validate_relative_path."""
    errors: list[str] = validate_relative_path(field, value)
    return errors


# --- Structural complexity ------------------------------------------------


def _check_list_object_keys(value: object, *, path: str = "$") -> list[str]:
    """Walk the structure; reject list-of-objects with too many keys per object."""
    errors: list[str] = []
    if isinstance(value, dict):
        for k, v in value.items():
            errors.extend(_check_list_object_keys(v, path=f"{path}.{k}"))
    elif isinstance(value, list):
        for idx, item in enumerate(value):
            if isinstance(item, dict) and len(item) > MAX_LIST_OBJECT_KEYS:
                errors.append(
                    f"`{path}[{idx}]`: object has {len(item)} keys; "
                    f"list-of-objects limited to {MAX_LIST_OBJECT_KEYS} keys "
                    f"(ADR-006 Amendment 2026-04-28)"
                )
            errors.extend(_check_list_object_keys(item, path=f"{path}[{idx}]"))
    return errors


# --- Schema validation ----------------------------------------------------


def _validate_artifact_keys(name: str, stanza: dict[str, object]) -> list[str]:
    unknown = set(stanza.keys()) - ARTIFACT_DISPATCH[name]
    errors: list[str] = []
    if unknown:
        errors.append(
            f"`artifacts.{name}`: unknown keys {sorted(unknown)}. "
            f"Allowed: {sorted(ARTIFACT_DISPATCH[name])}"
        )
    return errors


def _validate_artifact_paths(name: str, stanza: dict[str, object]) -> list[str]:
    errors: list[str] = []
    for path_field in PATH_FIELDS_BY_ARTIFACT.get(name, ()):
        if path_field in stanza:
            errors.extend(
                _validate_path_value(f"artifacts.{name}.{path_field}", stanza[path_field])
            )
    return errors


def _validate_rules_output_dirs(name: str, stanza: dict[str, object]) -> list[str]:
    if "outputDirs" not in stanza:
        return []
    errors: list[str] = []
    dirs = stanza.get("outputDirs")
    if not isinstance(dirs, list) or not dirs:
        errors.append(
            f"`artifacts.{name}.outputDirs`: must be a non-empty list of paths"
        )
    else:
        for idx, item in enumerate(dirs):
            errors.extend(
                _validate_path_value(f"artifacts.{name}.outputDirs[{idx}]", item)
            )
    if "outputDir" in stanza:
        errors.append(
            f"`artifacts.{name}`: `outputDir` and `outputDirs` are "
            f"mutually exclusive"
        )
    return errors


def _declared_rule_output_dirs(stanza: dict[str, object]) -> set[str]:
    declared = set()
    raw_dirs = stanza.get("outputDirs")
    if isinstance(raw_dirs, list):
        declared = {d for d in raw_dirs if isinstance(d, str)}
    single = stanza.get("outputDir")
    if isinstance(single, str):
        declared.add(single)
    return {PurePosixPath(d).as_posix() for d in declared}


def _validate_rules_keep_internal_globs(
    name: str, stanza: dict[str, object]
) -> list[str]:
    keep = stanza.get("keepInternalGlobsFor")
    if keep is None:
        return []
    if not isinstance(keep, list):
        return [f"`artifacts.{name}.keepInternalGlobsFor`: must be a list of paths"]
    errors: list[str] = []
    declared_norm = _declared_rule_output_dirs(stanza)
    for idx, item in enumerate(keep):
        errors.extend(
            _validate_path_value(f"artifacts.{name}.keepInternalGlobsFor[{idx}]", item)
        )
        if isinstance(item, str) and PurePosixPath(item).as_posix() not in declared_norm:
            errors.append(
                f"`artifacts.{name}.keepInternalGlobsFor[{idx}]`: "
                f"{item!r} is not one of the declared output dirs"
            )
    return errors


def _validate_command_resources(name: str, stanza: dict[str, object]) -> list[str]:
    errors: list[str] = []
    has_resource_output = "resourceOutputDir" in stanza
    has_resource_suffixes = "resourceSuffixes" in stanza
    if has_resource_output != has_resource_suffixes:
        errors.append(
            f"`artifacts.{name}`: `resourceOutputDir` and "
            "`resourceSuffixes` must be set together"
        )
    if has_resource_suffixes:
        suffixes = stanza.get("resourceSuffixes")
        if (
            not isinstance(suffixes, list)
            or not suffixes
            or not all(
                isinstance(item, str)
                and item.startswith(".")
                and len(item) > 1
                for item in suffixes
            )
        ):
            errors.append(
                f"`artifacts.{name}.resourceSuffixes`: must be a "
                "non-empty list of dotted suffix strings"
            )
    return errors


def _validate_exclude_filenames(name: str, stanza: dict[str, object]) -> list[str]:
    if "excludeFilenames" not in stanza:
        return []
    value = stanza["excludeFilenames"]
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return [
            f"`artifacts.{name}.excludeFilenames`: must be a list of strings"
        ]
    return []


def _validate_artifact_stanza(name: str, stanza: object) -> list[str]:
    if not isinstance(stanza, dict):
        return [f"`artifacts.{name}`: must be a mapping (got {type(stanza).__name__})"]
    if name not in ARTIFACT_DISPATCH:
        return [
            f"`artifacts.{name}`: unknown artifact type. "
            f"Valid: {sorted(ARTIFACT_DISPATCH)}"
        ]
    errors = _validate_artifact_keys(name, stanza)
    errors.extend(_validate_artifact_paths(name, stanza))
    if "excludeFilenames" in ARTIFACT_DISPATCH[name]:
        errors.extend(_validate_exclude_filenames(name, stanza))
    if name == "rules":
        errors.extend(_validate_rules_output_dirs(name, stanza))
        errors.extend(_validate_rules_keep_internal_globs(name, stanza))
    if name == "commands":
        errors.extend(_validate_command_resources(name, stanza))
    return errors


def _validate_audit_policy(value: object) -> list[str]:
    if not isinstance(value, dict):
        return [f"`auditPolicy`: must be a mapping (got {type(value).__name__})"]
    unknown = set(value.keys()) - AUDIT_POLICY_KEYS
    errors: list[str] = []
    if unknown:
        errors.append(
            f"`auditPolicy`: unknown keys {sorted(unknown)}. "
            f"Allowed: {sorted(AUDIT_POLICY_KEYS)}"
        )
    blocklist = value.get("pathBlocklist")
    if blocklist is not None and not isinstance(blocklist, list):
        errors.append("`auditPolicy.pathBlocklist`: must be a list of strings")
    return errors


def validate_yaml_doc(data: object) -> tuple[list[str], bool]:
    """Validate a parsed YAML document. Returns (errors, is_config_error).

    Assumes the document already passed yaml_loader.load_platform_config
    (mapping shape + valid schemaVersion). Performs schema-specific checks
    only.
    """
    if not isinstance(data, dict):
        return (["Top-level value must be a mapping"], True)

    missing = REQUIRED_TOP_LEVEL - data.keys()
    if missing:
        return ([f"Missing required top-level keys: {sorted(missing)}"], True)

    unknown = set(data.keys()) - ALLOWED_TOP_LEVEL
    errors: list[str] = []
    if unknown:
        errors.append(
            f"Unknown top-level keys: {sorted(unknown)}. "
            f"Allowed: {sorted(ALLOWED_TOP_LEVEL)}"
        )

    if not isinstance(data.get("provider"), str) or not data["provider"].strip():
        errors.append("`provider`: must be a non-empty string")

    artifacts = data.get("artifacts")
    if artifacts is not None:
        if not isinstance(artifacts, dict):
            errors.append("`artifacts`: must be a mapping")
        else:
            for name, stanza in artifacts.items():
                errors.extend(_validate_artifact_stanza(name, stanza))

    if "auditPolicy" in data:
        errors.extend(_validate_audit_policy(data["auditPolicy"]))

    errors.extend(_check_list_object_keys(data))

    return (errors, False)


# --- File-level entry point -----------------------------------------------


def validate_file(path: Path) -> tuple[list[str], bool]:
    """Validate a single platform YAML file. Returns (errors, is_config_error).

    Delegates I/O, anchor/alias, and schemaVersion checks to yaml_loader.
    Enforces the per-file line cap inline (file-format concern, not loader
    concern).
    """
    # Line-count cap runs before the loader so we can return a clean message
    # without paying for parse cost on oversize files.
    try:
        raw = path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError, UnicodeDecodeError):
        # Defer to load_platform_config so the message format stays consistent.
        raw = ""

    if raw:
        line_count = raw.count("\n") + (0 if raw.endswith("\n") else 1)
        if line_count > MAX_FILE_LINES:
            return (
                [
                    f"File has {line_count} lines; limit is {MAX_FILE_LINES} "
                    "(ADR-006 Amendment 2026-04-28)"
                ],
                True,
            )

    try:
        data = load_platform_config(path, supported_major=SUPPORTED_MAJOR)
    except ConfigError as exc:
        return ([str(exc)], True)

    return validate_yaml_doc(data)


def find_platform_configs(root: Path) -> list[Path]:
    platforms_dir = root / "templates" / "platforms"
    if not platforms_dir.is_dir():
        return []
    return sorted(p for p in platforms_dir.glob("*.yaml") if p.is_file())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=REPO_ROOT,
        help="Repository root to scan (default: %(default)s)",
    )
    parser.add_argument(
        "--platform",
        type=Path,
        action="append",
        help="Specific platform YAML to validate (skips discovery)",
    )
    args = parser.parse_args(argv)

    if args.platform:
        targets = list(args.platform)
    else:
        targets = find_platform_configs(args.root)

    if not targets:
        print("No platform YAML files found", file=sys.stderr)
        return 2

    failures = 0
    config_errors = 0
    for target in targets:
        errors, is_config_error = validate_file(target)
        try:
            rel = target.relative_to(args.root)
        except ValueError:
            rel = target
        if errors:
            failures += 1
            if is_config_error:
                config_errors += 1
            print(f"FAIL {rel}")
            for err in errors:
                print(f"  - {err}")
        else:
            print(f"OK   {rel}")

    if failures:
        print(
            f"\n{failures} of {len(targets)} platform config(s) invalid",
            file=sys.stderr,
        )
        return 2 if config_errors else 1
    print(f"\nAll {len(targets)} platform config(s) valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
