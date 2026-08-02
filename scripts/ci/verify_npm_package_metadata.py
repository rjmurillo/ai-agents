#!/usr/bin/env python3
"""Verify npm package metadata meets publishing requirements.

Reads package.json from --package-dir and checks that the required fields
for a scoped npm publish are present and correctly configured.
Replaces the inline node -e block in publish.yml (issue #3533).

EXIT CODES (ADR-035):
  0  - All metadata checks pass
  1  - One or more checks failed
  2  - Usage error (missing --package-dir)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

EXIT_OK = 0
EXIT_INVALID = 1
EXIT_USAGE = 2


def check_package_metadata(pkg: dict[str, Any]) -> list[str]:
    """Return a list of error messages; empty means all checks pass."""
    errors: list[str] = []
    if pkg.get("name") != "@rjmurillo/ai-agents":
        errors.append("name must be @rjmurillo/ai-agents")
    publish_config = pkg.get("publishConfig") or {}
    if publish_config.get("access") != "public":
        errors.append("publishConfig.access must be public")
    if not publish_config.get("provenance"):
        errors.append("publishConfig.provenance must be true")
    if not pkg.get("bin"):
        errors.append("bin entry required")
    if not pkg.get("files"):
        errors.append("files allowlist required")
    return errors


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--package-dir",
        required=True,
        help="Path to the npm package directory containing package.json",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    pkg_json = Path(args.package_dir) / "package.json"
    if not pkg_json.exists():
        print(f"ERROR: {pkg_json} not found", file=sys.stderr)
        return EXIT_INVALID

    pkg = json.loads(pkg_json.read_text(encoding="utf-8"))
    errors = check_package_metadata(pkg)
    if errors:
        for err in errors:
            print(err, file=sys.stderr)
        return EXIT_INVALID

    print(f"Package metadata OK: {pkg.get('name')}@{pkg.get('version')}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
