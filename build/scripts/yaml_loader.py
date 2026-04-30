#!/usr/bin/env python3
"""Shared YAML loader for build-pipeline configs.

Centralizes YAML reading + safety checks shared by:
- validate_templates_schema.py (REQ-003-002)
- validate_marketplace_counts.py (REQ-003-004)
- future config-driven build scripts (M3+)

Enforces ADR-006 Amendment 2026-04-28 conditions:
- safe_load only (no Python tags)
- anchors and aliases forbidden (Condition 3/6)
- schemaVersion SemVer compatibility (^1.x by default)
- relative-path enforcement (REQ-003-009)

Public API:
    load_platform_config(path, supported_major=1) -> dict
    validate_relative_path(field, value) -> list[str]
    ConfigError (raised on missing/parse/version errors)
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

SCHEMA_VERSION_RE = re.compile(r"^(\d+)\.(\d+)$")
DEFAULT_SUPPORTED_MAJOR = 1


class ConfigError(Exception):
    """Raised when a build-pipeline YAML config cannot be loaded safely.

    Covers: missing file, parse error, anchor/alias use, missing
    schemaVersion, malformed schemaVersion, unsupported major version.
    """


# --- Anchor/alias detection ----------------------------------------------


def _detect_anchors_aliases(text: str) -> None:
    """Raise ConfigError on YAML anchor (`&name`) or alias (`*name`).

    Strips quoted spans first so blocklist patterns like ``"@[a-f0-9]{40}\\b"``
    don't trigger false positives. The schemas are small, so a per-line scan
    is cheaper than a custom Loader.
    """
    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = re.sub(r"'[^']*'", "''", line)
        stripped = re.sub(r'"[^"]*"', '""', stripped)
        if re.search(r"(?<![\w])&[A-Za-z_][\w\-]*", stripped):
            raise ConfigError(
                f"line {lineno}: YAML anchor detected. Anchors and aliases "
                "are forbidden in build-pipeline YAML "
                "(ADR-006 Amendment 2026-04-28)."
            )
        if re.search(r"(?<![\w])\*[A-Za-z_][\w\-]*", stripped):
            raise ConfigError(
                f"line {lineno}: YAML alias detected. Anchors and aliases "
                "are forbidden in build-pipeline YAML "
                "(ADR-006 Amendment 2026-04-28)."
            )


def _strict_safe_load(text: str) -> object:
    """safe_load with anchor/alias rejection."""
    _detect_anchors_aliases(text)
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"YAML parse error: {exc}") from exc


# --- SchemaVersion --------------------------------------------------------


def _check_schema_version(
    value: object, supported_major: int, *, source: str = ""
) -> None:
    """Raise ConfigError if schemaVersion is missing or incompatible.

    ``source`` (file path string) is prefixed to every message so contributors
    diagnosing a typo see which file triggered the failure.
    """
    prefix = f"{source}: " if source else ""
    if value is None:
        raise ConfigError(f"{prefix}missing required `schemaVersion`")
    if not isinstance(value, str):
        raise ConfigError(
            f"{prefix}`schemaVersion`: must be a string (got {type(value).__name__})"
        )
    match = SCHEMA_VERSION_RE.match(value)
    if not match:
        raise ConfigError(
            f"{prefix}`schemaVersion`: '{value}' is not a valid SemVer 'MAJOR.MINOR'"
        )
    major = int(match.group(1))
    if major != supported_major:
        raise ConfigError(
            f"{prefix}`schemaVersion`: major version {major} unsupported "
            f"(this loader handles ^{supported_major}.x)"
        )


# --- Relative path safety ------------------------------------------------


def validate_relative_path(field: str, value: object) -> list[str]:
    """Reject absolute paths and ``..`` traversal (REQ-003-009).

    Returns a list of error strings (empty when valid). Path fields in
    build-pipeline configs are always repo-relative.
    """
    if not isinstance(value, str):
        return [f"`{field}`: must be a string path (got {type(value).__name__})"]
    if not value:
        return [f"`{field}`: must not be empty"]
    if value.startswith("/"):
        return [
            f"`{field}`: absolute path '{value}' rejected (must be repo-relative)"
        ]
    parts = Path(value).parts
    if ".." in parts:
        return [f"`{field}`: path '{value}' must not contain '..' traversal"]
    return []


# --- Public entry point --------------------------------------------------


def load_platform_config(
    path: Path | str, supported_major: int = DEFAULT_SUPPORTED_MAJOR
) -> dict:
    """Load and minimally validate a build-pipeline YAML config.

    Accepts ``str`` or ``Path``; coerces to ``Path`` so callers don't get
    opaque ``AttributeError`` from passing a string.

    Performs the safety checks shared by every consumer:
    - file exists and is readable as UTF-8
    - no anchors or aliases
    - parses as a top-level mapping
    - has a SemVer-shaped ``schemaVersion`` whose major matches ``supported_major``

    Domain-specific validation (allowed keys, artifact stanzas, counter
    strategies) belongs in the calling validator, not here.

    Raises:
        ConfigError on any failure (with file path in the message).
    Returns:
        The parsed YAML document as a dict.
    """
    path = Path(path)
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ConfigError(f"missing file: {path}") from exc
    except OSError as exc:
        raise ConfigError(f"read error for '{path}': {exc}") from exc
    except UnicodeDecodeError as exc:
        raise ConfigError(f"decode error for '{path}': {exc}") from exc

    try:
        data = _strict_safe_load(raw)
    except ConfigError as exc:
        # Re-raise with file path prefixed for diagnosability.
        raise ConfigError(f"{path}: {exc}") from exc.__cause__
    if not isinstance(data, dict):
        raise ConfigError(f"top-level value in '{path}' must be a mapping")

    _check_schema_version(
        data.get("schemaVersion"), supported_major, source=str(path)
    )
    return data
