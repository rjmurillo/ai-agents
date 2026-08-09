#!/usr/bin/env python3
"""Markdownlint verifier using vendored markdownlint-cli2.

Invokes an immutable vendored markdownlint-cli2 0.23.1 via absolute path
with integrity verification, environment scrubbing, and sterile temp dir
isolation to prevent consumer config/plugin pickup.

Security model:
- System Node.js resolved from known safe directories only
- NODE_OPTIONS, NODE_PATH, npm_* vars scrubbed from environment
- Files copied to sterile temp dir before linting (no consumer config leak)
- Entry point integrity verified via SHA-256 manifest
- No consumer PATH, registry, node_modules, config, or plugins used
- Fail closed if trusted tooling absent
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_VENDOR = _HERE / "_vendor" / "markdownlint"
_ENTRY = _VENDOR / "node_modules" / "markdownlint-cli2" / "markdownlint-cli2-bin.mjs"
_CONFIG = _HERE / "markdownlint-safe-config.yaml"
_INTEGRITY = _VENDOR / "INTEGRITY.sha256"

# Known safe directories for Node.js (system-managed, not consumer-controlled)
_SAFE_NODE_DIRS = (
    "/usr/bin",
    "/usr/local/bin",
    "/opt/homebrew/bin",
    "/snap/bin",
)

# Environment variables to scrub (prevent consumer influence)
_SCRUB_VARS = (
    "NODE_OPTIONS",
    "NODE_PATH",
    "NODE_EXTRA_CA_CERTS",
    "NPM_CONFIG_PREFIX",
    "NPM_CONFIG_GLOBALCONFIG",
    "NPM_CONFIG_USERCONFIG",
    "NPM_CONFIG_REGISTRY",
    "npm_config_prefix",
    "npm_config_globalconfig",
    "npm_config_userconfig",
    "npm_config_registry",
)


def _resolve_system_node() -> Path | None:
    """Resolve Node.js from trusted system directories only.

    Checks _MARKDOWNLINT_TRUSTED_NODE env var first (for test environments),
    then searches known safe system directories.
    """
    # Test override (e.g., ~/.nvm node not in system dirs)
    override = os.environ.get("_MARKDOWNLINT_TRUSTED_NODE")
    if override:
        p = Path(override)
        if p.is_file() and os.access(p, os.X_OK):
            return p

    for d in _SAFE_NODE_DIRS:
        candidate = Path(d) / "node"
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    return None


def _scrubbed_env() -> dict[str, str]:
    """Return environment with dangerous variables removed."""
    env = dict(os.environ)
    for var in _SCRUB_VARS:
        env.pop(var, None)
    # Also remove npm_config_* pattern
    for key in list(env.keys()):
        if key.lower().startswith("npm_config_"):
            del env[key]
    return env


def _verify_integrity() -> bool:
    """Verify entry point integrity against shipped manifest."""
    if not _INTEGRITY.is_file():
        return False
    manifest: dict[str, str] = {}
    for line in _INTEGRITY.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("  ", 1)
        if len(parts) == 2:
            manifest[parts[1]] = parts[0]

    # Verify entry point
    entry_rel = str(_ENTRY.relative_to(_VENDOR))
    expected = manifest.get(entry_rel)
    if not expected:
        return False
    actual = hashlib.sha256(_ENTRY.read_bytes()).hexdigest()
    return actual == expected


def main(files: list[str]) -> int:
    """Verify markdown files using vendored markdownlint-cli2.

    Returns 0 if all files pass, 1 if violations found, 2 if infrastructure
    error (fail closed).
    """
    if not files:
        return 0

    # Fail closed: require all components
    node = _resolve_system_node()
    if node is None:
        print("BLOCK: No trusted system Node.js found", file=sys.stderr)
        return 2

    if not _ENTRY.is_file():
        print("BLOCK: Vendored markdownlint-cli2 not found", file=sys.stderr)
        return 2

    if not _verify_integrity():
        print("BLOCK: Integrity verification failed", file=sys.stderr)
        return 2

    if not _CONFIG.is_file():
        print("BLOCK: Safe config not found", file=sys.stderr)
        return 2

    # Copy files to sterile temp dir (prevents consumer .markdownlint.yaml pickup)
    with tempfile.TemporaryDirectory(prefix="mdlint-") as tmp:
        tmp_path = Path(tmp)
        tmp_files = []
        for f in files:
            src = Path(f)
            if not src.is_file():
                continue
            dst = tmp_path / src.name
            # Handle duplicate names
            counter = 0
            while dst.exists():
                counter += 1
                dst = tmp_path / f"{src.stem}_{counter}{src.suffix}"
            shutil.copy2(src, dst)
            tmp_files.append(str(dst))

        if not tmp_files:
            return 0

        # Copy config to sterile dir
        shutil.copy2(_CONFIG, tmp_path / ".markdownlint-cli2.yaml")

        env = _scrubbed_env()
        env["HOME"] = tmp  # Prevent ~/.markdownlint* pickup

        try:
            proc = subprocess.run(
                [str(node), str(_ENTRY),
                 "--config", str(tmp_path / ".markdownlint-cli2.yaml"),
                 *tmp_files],
                cwd=tmp,
                capture_output=True,
                text=True,
                timeout=30,
                env=env,
                check=False,
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            print(f"BLOCK: markdownlint execution failed: {exc}", file=sys.stderr)
            return 2

        if proc.returncode == 0:
            return 0
        if proc.returncode == 1:
            # Violations found
            if proc.stdout:
                print(proc.stdout, file=sys.stderr)
            if proc.stderr:
                print(proc.stderr, file=sys.stderr)
            return 1
        # Unexpected exit code - fail closed
        print(f"BLOCK: markdownlint exited {proc.returncode}", file=sys.stderr)
        if proc.stderr:
            print(proc.stderr, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
