#!/usr/bin/env python3
"""Validate that both plugin manifests carry identical version strings.

The two manifests are:
  .claude/.claude-plugin/plugin.json        (Claude plugin)
  src/copilot-cli/.claude-plugin/plugin.json (Copilot CLI plugin)

When a PR bumps the version on one but not the other, the installed
plugins report different versions to the host. This check gates that
drift in CI (fix for #2222).

Exit codes (ADR-035):
    0 - Versions match
    2 - Configuration error (missing file, JSON parse error)
    1 - Staleness: versions differ
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

_MANIFESTS: tuple[Path, ...] = (
    _REPO_ROOT / ".claude" / ".claude-plugin" / "plugin.json",
    _REPO_ROOT / "src" / "copilot-cli" / ".claude-plugin" / "plugin.json",
)


def _read_version(path: Path) -> str | None:
    """Return the version field or None on parse error."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: cannot read {path}: {exc}", file=sys.stderr)
        return None
    version = data.get("version")
    if not isinstance(version, str) or not version.strip():
        print(f"ERROR: {path} has no valid 'version' field", file=sys.stderr)
        return None
    return version


def main() -> int:
    versions: dict[str, str] = {}

    for manifest in _MANIFESTS:
        if not manifest.exists():
            print(f"ERROR: manifest not found: {manifest}", file=sys.stderr)
            return 2
        version = _read_version(manifest)
        if version is None:
            return 2
        try:
            key = str(manifest.relative_to(_REPO_ROOT))
        except ValueError:
            key = str(manifest)
        versions[key] = version

    unique = set(versions.values())
    if len(unique) == 1:
        v = next(iter(unique))
        print(f"Plugin manifest versions match: {v}")
        return 0

    print("PLUGIN MANIFEST VERSION MISMATCH", file=sys.stderr)
    for path, ver in sorted(versions.items()):
        print(f"  {path}: {ver}", file=sys.stderr)
    print(
        "\nFix: bump both manifests to the same version and commit together.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
