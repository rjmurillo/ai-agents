#!/usr/bin/env python3
"""Validate plugin manifest version parity between .claude and src/copilot-cli.

Catches the drift class where `.claude/.claude-plugin/plugin.json` and
`src/copilot-cli/.claude-plugin/plugin.json` declare different `version`
fields. Both manifests must carry identical semver versions.

Exit codes:
    0 - Versions match (parity holds)
    2 - Version mismatch, missing manifest, or malformed JSON
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

MANIFEST_PATHS = [
    ".claude/.claude-plugin/plugin.json",
    "src/copilot-cli/.claude-plugin/plugin.json",
]


def _read_manifest(path: Path) -> tuple[str | None, list[str]]:
    """Read a manifest and extract its version field.

    Returns (version, errors). If errors is non-empty, version may be None.
    """
    if not path.exists():
        return None, [f"Manifest not found: {path}"]
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return None, [f"Manifest read error: {path}: {exc}"]
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return None, [f"JSON parse error in {path}: {exc}"]
    if not isinstance(data, dict):
        return None, [f"Manifest {path} top-level value must be an object"]
    version = data.get("version")
    if version is None:
        return None, [f"Manifest {path} missing `version` field"]
    if not isinstance(version, str) or not version.strip():
        return None, [f"Manifest {path} `version` must be a non-empty string (got {type(version).__name__})"]
    return version, []


def validate_version_parity(root: Path) -> tuple[bool, list[str]]:
    """Validate that all plugin manifests declare identical `version` fields.

    Returns (parity_holds, errors).
    """
    versions: dict[str, str] = {}
    errors: list[str] = []

    for rel_path in MANIFEST_PATHS:
        manifest = root / rel_path
        version, read_errors = _read_manifest(manifest)
        if read_errors:
            errors.extend(read_errors)
            continue
        if version is not None:
            versions[rel_path] = version

    if errors:
        return False, errors

    if not versions:
        return False, ["No valid manifests found"]

    unique_versions = set(versions.values())
    if len(unique_versions) == 1:
        return True, []

    # Mismatch: report which manifest has which version
    mismatch_lines = [
        "Plugin manifest version mismatch detected:",
        "",
    ]
    for rel_path, version in sorted(versions.items()):
        mismatch_lines.append(f"  {rel_path}: {version}")
    mismatch_lines.append("")
    mismatch_lines.append(
        "Both manifests must declare the same `version` field. "
        "Update the stale manifest(s) to match, then commit."
    )
    return False, mismatch_lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=REPO_ROOT,
        help="Repository root to scan (default: %(default)s)",
    )
    args = parser.parse_args(argv)

    parity_holds, messages = validate_version_parity(args.root)

    for msg in messages:
        print(msg, file=sys.stderr if not parity_holds else sys.stdout)

    if parity_holds:
        print("\n✓ Plugin manifest version parity check passed", file=sys.stdout)
        return 0
    print("\n✗ Plugin manifest version parity check failed", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
