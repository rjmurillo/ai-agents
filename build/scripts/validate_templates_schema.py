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
import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# Top-level schema --------------------------------------------------------

ALLOWED_TOP_LEVEL = {"schemaVersion", "provider", "artifacts", "auditPolicy", "legacy"}
REQUIRED_TOP_LEVEL = {"schemaVersion", "provider"}

# Compatibility window: major version 1 with any minor.
SUPPORTED_MAJOR = 1
SCHEMA_VERSION_RE = re.compile(r"^(\d+)\.(\d+)$")

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
SKILLS_KEYS = {"sourceDir", "outputDir", "mode"}
COMMANDS_KEYS = {
    "sourceDir",
    "outputDir",
    "transform",
    "appendFrontmatter",
}
RULES_KEYS = {
    "sourceDir",
    "outputDir",
    "sourceSuffix",
    "outputSuffix",
    "frontmatterRemap",
    "frontmatterDrop",
    "skipIfNoPathScope",
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
}
ARTIFACT_DISPATCH = {
    "agents": AGENTS_KEYS,
    "skills": SKILLS_KEYS,
    "commands": COMMANDS_KEYS,
    "rules": RULES_KEYS,
    "hooks": HOOKS_KEYS,
}

PATH_FIELDS_BY_ARTIFACT = {
    "agents": ("sourceDir", "outputDir"),
    "skills": ("sourceDir", "outputDir"),
    "commands": ("sourceDir", "outputDir"),
    "rules": ("sourceDir", "outputDir"),
    "hooks": ("settingsSource", "scriptSource", "outputConfig", "outputScripts"),
}

AUDIT_POLICY_KEYS = {"pathBlocklist", "output"}


# --- Safe loader: forbid anchors/aliases ----------------------------------


def _strict_safe_load(text: str) -> object:
    """safe_load with anchor/alias detection.

    The standard SafeLoader resolves aliases silently. To meet ADR-006
    Amendment 2026-04-28 Condition 3, scan the raw text for `&name` and
    `*name` markers before parsing. Inline regex is sufficient because
    the schema is small and the markers are unambiguous outside of
    quoted strings (we reject the file outright either way).
    """
    # Detect anchor/alias outside of quoted strings. Cheap, conservative:
    # any line containing `&word` or `*word` after stripping quoted spans.
    for lineno, line in enumerate(text.splitlines(), start=1):
        # Strip both single- and double-quoted spans so blocklist regex
        # entries like "@[a-f0-9]{40}\\b" don't trip the alias scan.
        stripped = re.sub(r"'[^']*'", "''", line)
        stripped = re.sub(r'"[^"]*"', '""', stripped)
        if re.search(r"(?<![\w])&[A-Za-z_][\w\-]*", stripped):
            raise yaml.YAMLError(
                f"line {lineno}: YAML anchor detected. Anchors and aliases "
                "are forbidden in templates/platforms/*.yaml "
                "(ADR-006 Amendment 2026-04-28)."
            )
        if re.search(r"(?<![\w])\*[A-Za-z_][\w\-]*", stripped):
            raise yaml.YAMLError(
                f"line {lineno}: YAML alias detected. Anchors and aliases "
                "are forbidden in templates/platforms/*.yaml "
                "(ADR-006 Amendment 2026-04-28)."
            )
    return yaml.safe_load(text)


# --- Path safety ----------------------------------------------------------


def _validate_path_value(field: str, value: object) -> list[str]:
    """Reject absolute paths and `..` traversal (REQ-003-009).

    Path fields in platform configs are always relative to the repo root.
    """
    if not isinstance(value, str):
        return [f"`{field}`: must be a string path (got {type(value).__name__})"]
    if not value:
        return [f"`{field}`: must not be empty"]
    if value.startswith("/"):
        return [f"`{field}`: absolute path '{value}' rejected (must be repo-relative)"]
    parts = Path(value).parts
    if ".." in parts:
        return [f"`{field}`: path '{value}' must not contain '..' traversal"]
    return []


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


def _validate_schema_version(value: object) -> tuple[list[str], bool]:
    """Returns (errors, is_config_error). Config errors map to exit 2."""
    if not isinstance(value, str):
        return (
            [f"`schemaVersion`: must be a string (got {type(value).__name__})"],
            True,
        )
    match = SCHEMA_VERSION_RE.match(value)
    if not match:
        return (
            [f"`schemaVersion`: '{value}' is not a valid SemVer 'MAJOR.MINOR'"],
            True,
        )
    major = int(match.group(1))
    if major != SUPPORTED_MAJOR:
        return (
            [
                f"`schemaVersion`: major version {major} unsupported "
                f"(this validator handles ^{SUPPORTED_MAJOR}.x)"
            ],
            True,
        )
    return ([], False)


def _validate_artifact_stanza(name: str, stanza: object) -> list[str]:
    if not isinstance(stanza, dict):
        return [f"`artifacts.{name}`: must be a mapping (got {type(stanza).__name__})"]
    if name not in ARTIFACT_DISPATCH:
        return [
            f"`artifacts.{name}`: unknown artifact type. "
            f"Valid: {sorted(ARTIFACT_DISPATCH)}"
        ]
    allowed = ARTIFACT_DISPATCH[name]
    unknown = set(stanza.keys()) - allowed
    errors: list[str] = []
    if unknown:
        errors.append(
            f"`artifacts.{name}`: unknown keys {sorted(unknown)}. "
            f"Allowed: {sorted(allowed)}"
        )
    for path_field in PATH_FIELDS_BY_ARTIFACT.get(name, ()):
        if path_field in stanza:
            errors.extend(
                _validate_path_value(f"artifacts.{name}.{path_field}", stanza[path_field])
            )
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
    """Validate a parsed YAML document. Returns (errors, is_config_error)."""
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

    version_errors, version_is_config = _validate_schema_version(data["schemaVersion"])
    if version_errors:
        return (version_errors, version_is_config)

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
    """Validate a single platform YAML file. Returns (errors, is_config_error)."""
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        return ([f"Missing file: {exc}"], True)
    except OSError as exc:
        return ([f"Read error for '{path}': {exc}"], True)
    except UnicodeDecodeError as exc:
        return ([f"Decode error for '{path}': {exc}"], True)

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
        data = _strict_safe_load(raw)
    except yaml.YAMLError as exc:
        return ([f"YAML parse error: {exc}"], True)

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
