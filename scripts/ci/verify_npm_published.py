#!/usr/bin/env python3
"""Verify that an npm package version is visible on the registry after publish.

Retries up to 5 times with 10-second delays before failing. Reads the expected
version from package.json in --package-dir.
Replaces the inline shell retry loop in publish.yml (issue #3533).

EXIT CODES (ADR-035):
  0  - Package version is live on npm
  1  - Version not visible after all retries
  2  - Usage error
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

EXIT_OK = 0
EXIT_NOT_PUBLISHED = 1
EXIT_USAGE = 2

_MAX_RETRIES = 5
_RETRY_DELAY_SECONDS = 10
_PACKAGE_NAME = "@rjmurillo/ai-agents"


def get_published_version(package: str, version: str) -> str:
    """Return the published version string, or empty string on failure."""
    result = subprocess.run(
        ["npm", "view", f"{package}@{version}", "version"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    return result.stdout.strip()


def wait_for_publish(
    package: str,
    version: str,
    max_retries: int = _MAX_RETRIES,
    delay_seconds: int = _RETRY_DELAY_SECONDS,
) -> bool:
    """Poll npm until the version is visible. Return True if found."""
    print(f"Expecting {package}@{version}")
    for attempt in range(1, max_retries + 1):
        time.sleep(delay_seconds)
        published = get_published_version(package, version)
        if published == version:
            print(f"Verified: {package}@{version} is live on npm")
            return True
        print(f"Attempt {attempt}: version {version} not yet visible, retrying...")
    return False


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
        return EXIT_NOT_PUBLISHED

    pkg = json.loads(pkg_json.read_text(encoding="utf-8"))
    version = pkg.get("version", "")
    if not version:
        print("ERROR: version field missing from package.json", file=sys.stderr)
        return EXIT_NOT_PUBLISHED

    if wait_for_publish(_PACKAGE_NAME, version):
        return EXIT_OK

    timeout_sec = _MAX_RETRIES * _RETRY_DELAY_SECONDS
    print(f"::error::Version {version} not visible on npm after {timeout_sec}s")
    return EXIT_NOT_PUBLISHED


if __name__ == "__main__":
    sys.exit(main())
