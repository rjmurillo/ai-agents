#!/usr/bin/env python3
"""Fingerprint the pytest settings that can shape rewritten assertion bytecode.

The workflow pins cached pytest commands to ``pyproject.toml``. Hashing the
whole file would rotate the performance cache for unrelated project metadata,
so this script hashes only the parsed pytest table plus the pytest version.
The output is a step input to the cache key, never a trust decision: pytest
still validates every cached bytecode header against its source hash.

EXIT CODES (ADR-035):
  0 - fingerprint written or printed
  2 - configuration file missing, unreadable as TOML, or malformed
  3 - output file cannot be written
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import sys
from collections.abc import Mapping
from pathlib import Path

import pytest
import tomllib

EXIT_OK = 0
EXIT_CONFIG = 2
EXIT_EXTERNAL = 3
CONFIG_FILE = "pyproject.toml"
FORMAT_VERSION = 1
_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _jsonable(value: object) -> object:
    """Return a deterministic JSON-compatible form of TOML data."""
    if isinstance(value, dict):
        return {str(key): _jsonable(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


def load_pytest_ini_options(path: Path) -> dict[str, object]:
    """Read ``[tool.pytest.ini_options]`` from ``path`` as plain TOML data."""
    try:
        document = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"{path}: pytest configuration file does not exist") from exc
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise ValueError(f"{path}: cannot parse pytest configuration: {exc}") from exc
    tool = document.get("tool", {})
    pytest_table = tool.get("pytest", {}) if isinstance(tool, dict) else {}
    options = pytest_table.get("ini_options", {}) if isinstance(pytest_table, dict) else {}
    if not isinstance(options, dict):
        raise ValueError(f"{path}: [tool.pytest.ini_options] must be a TOML table")
    return dict(options)


def fingerprint_options(options: Mapping[str, object], pytest_version: str) -> str:
    """Hash the effective pytest table and implementation version canonically."""
    payload = {
        "format": FORMAT_VERSION,
        "config_file": CONFIG_FILE,
        "pytest_ini_options": _jsonable(dict(options)),
        "pytest_version": pytest_version,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def fingerprint_file(path: Path) -> str:
    """Fingerprint the pytest table in one configuration file."""
    return fingerprint_options(load_pytest_ini_options(path), pytest.__version__)


def python_runtime() -> str:
    """Return the interpreter implementation and exact version running pytest."""
    return f"{platform.python_implementation().lower()}-{platform.python_version()}"


def _write_output(value: str) -> None:
    output = os.environ.get("GITHUB_OUTPUT", "")
    if output:
        with open(output, "a", encoding="utf-8") as stream:
            stream.write(f"fingerprint={value}\n")
            stream.write(f"python-runtime={python_runtime()}\n")
    else:
        print(f"fingerprint={value}")
        print(f"python-runtime={python_runtime()}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pyproject", type=Path, default=_PROJECT_ROOT / CONFIG_FILE)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        value = fingerprint_file(args.pyproject)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    try:
        _write_output(value)
    except OSError as exc:
        print(f"error: could not write fingerprint output: {exc}", file=sys.stderr)
        return EXIT_EXTERNAL
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
