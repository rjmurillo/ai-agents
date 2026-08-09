#!/usr/bin/env python3
"""Trusted co-located markdown verifier for the push guard.

Invoked by absolute path from ``invoke_markdownlint_guard.py``. Uses
``npx markdownlint-cli2@<pinned>`` with the shipped safe config so consumer
``node_modules`` binaries, consumer ``.markdownlint-cli2.yaml``, consumer
plugins, and consumer custom rules are never consulted.

Interface:
    python _markdownlint_verifier.py --markdown-lint-only -- <file> [<file>...]

Exit codes:
    0 = All files pass.
    1 = Violations found (diagnostics on stdout/stderr).
    2 = Infrastructure failure (missing npx, config, etc.).

Environment:
    MARKDOWNLINT_CONFIG_PATH  Absolute path to the shipped safe config.
                              Required; exits 2 if absent or non-existent.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

_PINNED_PACKAGE = "markdownlint-cli2@0.23.1"
_TIMEOUT = 55  # seconds; slightly under the caller's 60s timeout


def _parse_files(args: list[str]) -> list[str] | None:
    """Return target files from args, or None on parse failure (prints usage)."""
    if "--markdown-lint-only" not in args:
        print("usage: _markdownlint_verifier.py --markdown-lint-only -- <files>", file=sys.stderr)
        return None
    try:
        sep_idx = args.index("--")
    except ValueError:
        print("missing -- separator", file=sys.stderr)
        return None
    return args[sep_idx + 1:]


def _resolve_config() -> Path | None:
    """Return the safe config path, or None on failure (prints reason)."""
    config_path_str = os.environ.get("MARKDOWNLINT_CONFIG_PATH", "")
    if not config_path_str:
        print("MARKDOWNLINT_CONFIG_PATH not set", file=sys.stderr)
        return None
    config_path = Path(config_path_str)
    if not config_path.is_file():
        print(f"safe config not found: {config_path}", file=sys.stderr)
        return None
    return config_path


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]

    files = _parse_files(args)
    if files is None:
        return 2
    if not files:
        return 0

    config_path = _resolve_config()
    if config_path is None:
        return 2

    npx = shutil.which("npx")
    if npx is None:
        print("npx not found on PATH; cannot run markdownlint-cli2", file=sys.stderr)
        return 2

    command = [npx, _PINNED_PACKAGE, "--config", str(config_path), "--no-globs", "--", *files]

    try:
        proc = subprocess.run(
            command, capture_output=True, text=True, timeout=_TIMEOUT, shell=False, check=False,
        )
    except subprocess.TimeoutExpired:
        print(f"markdownlint-cli2 timed out after {_TIMEOUT}s", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"failed to invoke npx: {exc}", file=sys.stderr)
        return 2

    if proc.returncode == 0:
        return 0

    output = proc.stdout or proc.stderr
    if output:
        print(output, end="")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
