#!/usr/bin/env python3
"""Markdownlint verifier using vendored markdownlint-cli2.

Invokes an immutable vendored markdownlint-cli2 0.23.1 via absolute path
with full integrity verification, environment scrubbing, and sterile temp
dir isolation to prevent consumer config/plugin pickup.

Security model:
- System Node.js resolved from administrator-owned platform directories
- Ownership and permission validation on resolved Node binary
- Full vendor tree integrity verified (every file, symlink, executable mode)
- Strict environment allowlist for subprocess invocation
- Files copied to sterile temp dir (no consumer config leak)
- No consumer PATH, registry, node_modules, config, or plugins used
- Fail closed if any component missing or tampered
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
_VENDOR = _HERE / "_vendor" / "markdownlint"
_ENTRY = _VENDOR / "node_modules" / "markdownlint-cli2" / "markdownlint-cli2-bin.mjs"
_CONFIG = _HERE / "markdownlint-safe-config.yaml"
_INTEGRITY = _VENDOR / "INTEGRITY.json"

_PLATFORM_NODE_DIRS: tuple[str, ...] = (
    "/usr/bin",
    "/usr/local/bin",
    "/opt/homebrew/bin",
    "/snap/bin",
)

_ENV_ALLOWLIST: frozenset[str] = frozenset((
    "HOME", "LANG", "LC_ALL", "PATH",
    "SYSTEMROOT", "TEMP", "TMP", "TMPDIR",
    "USER", "LOGNAME",
))


def _is_admin_owned_not_user_writable(path: Path) -> bool:
    """Verify path is owned by root and not world/group-writable."""
    try:
        st = path.stat()
    except OSError:
        return False
    if hasattr(st, "st_uid") and st.st_uid != 0:
        return False
    if st.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        return False
    return True


def _resolve_system_node() -> Path | None:
    """Resolve Node.js from trusted administrator-owned platform dirs."""
    for d in _PLATFORM_NODE_DIRS:
        dir_path = Path(d)
        if not dir_path.is_dir():
            continue
        if not _is_admin_owned_not_user_writable(dir_path):
            continue
        candidate = dir_path / "node"
        if not candidate.is_file():
            continue
        if not os.access(candidate, os.X_OK):
            continue
        if not _is_admin_owned_not_user_writable(candidate):
            continue
        return candidate
    return None


def _allowlisted_env(tmp_dir: str, node: Path) -> dict[str, str]:
    """Return strict allowlisted environment for subprocess."""
    env: dict[str, str] = {}
    for key in _ENV_ALLOWLIST:
        val = os.environ.get(key)
        if val is not None:
            env[key] = val
    env["HOME"] = tmp_dir
    env["PATH"] = str(node.parent)
    return env


def _load_manifest() -> dict[str, Any] | None:
    """Load and parse the integrity manifest. Returns None on failure."""
    if not _INTEGRITY.is_file():
        return None
    try:
        result: dict[str, Any] = json.loads(_INTEGRITY.read_text(encoding="utf-8"))
        return result
    except (json.JSONDecodeError, OSError):
        return None


def _collect_actual_tree() -> tuple[dict[str, str], dict[str, str]]:
    """Walk vendor tree, return (files_with_hashes, symlinks)."""
    actual_files: dict[str, str] = {}
    actual_symlinks: dict[str, str] = {}
    for item in sorted(_VENDOR.rglob("*")):
        rel = str(item.relative_to(_VENDOR))
        if rel in ("INTEGRITY.json", "INTEGRITY.sha256"):
            continue
        if item.is_symlink():
            actual_symlinks[rel] = os.readlink(item)
        elif item.is_file():
            actual_files[rel] = hashlib.sha256(item.read_bytes()).hexdigest()
    return actual_files, actual_symlinks


def _check_extra_or_missing(
    actual: dict[str, str], expected: dict[str, str], label: str,
) -> str | None:
    """Check for extra or missing entries. Returns error or None."""
    extra = set(actual.keys()) - set(expected.keys())
    if extra:
        return f"extra {label}: {sorted(extra)[:3]}"
    missing = set(expected.keys()) - set(actual.keys())
    if missing:
        return f"missing {label}: {sorted(missing)[:3]}"
    return None


def _check_hashes(
    actual: dict[str, str], expected: dict[str, str],
) -> str | None:
    """Verify all file hashes match. Returns error or None."""
    for rel, expected_hash in expected.items():
        if actual.get(rel) != expected_hash:
            return f"hash mismatch: {rel}"
    return None


def _check_symlinks(
    actual: dict[str, str], expected: dict[str, str],
) -> str | None:
    """Verify symlink targets match. Returns error or None."""
    for rel, target in expected.items():
        if actual.get(rel) != target:
            return f"symlink mismatch: {rel}"
    return None


def _verify_full_integrity() -> str | None:
    """Verify every file, symlink, and mode in vendor tree."""
    manifest = _load_manifest()
    if manifest is None:
        return "INTEGRITY.json not found or invalid"

    expected_files = manifest.get("files", {})
    expected_symlinks = manifest.get("symlinks", {})
    actual_files, actual_symlinks = _collect_actual_tree()

    err = _check_extra_or_missing(actual_files, expected_files, "files")
    if err:
        return err
    err = _check_extra_or_missing(
        actual_symlinks, expected_symlinks, "symlinks",
    )
    if err:
        return err
    err = _check_hashes(actual_files, expected_files)
    if err:
        return err
    err = _check_symlinks(actual_symlinks, expected_symlinks)
    if err:
        return err

    for rel in manifest.get("executables", []):
        if not os.access(_VENDOR / rel, os.X_OK):
            return f"expected executable: {rel}"
    return None


def _check_prerequisites(node: Path | None) -> str | None:
    """Validate all prerequisites. Returns error message or None."""
    if node is None:
        return "No trusted system Node.js found"
    if not _ENTRY.is_file():
        return "Vendored markdownlint-cli2 not found"
    if not _CONFIG.is_file():
        return "Safe config not found"
    return _verify_full_integrity()


def _copy_to_sterile_dir(
    files: list[str], tmp_path: Path,
) -> list[str]:
    """Copy files to sterile temp dir, return paths in temp."""
    tmp_files: list[str] = []
    for f in files:
        src = Path(f)
        if not src.is_file():
            continue
        dst = tmp_path / src.name
        counter = 0
        while dst.exists():
            counter += 1
            dst = tmp_path / f"{src.stem}_{counter}{src.suffix}"
        shutil.copy2(src, dst)
        tmp_files.append(str(dst))
    return tmp_files


def _run_linter(
    node: Path, tmp_files: list[str], tmp: str,
) -> int:
    """Invoke markdownlint-cli2. Returns 0, 1, or 2."""
    tmp_path = Path(tmp)
    shutil.copy2(_CONFIG, tmp_path / ".markdownlint-cli2.yaml")
    env = _allowlisted_env(tmp, node)
    config_path = str(tmp_path / ".markdownlint-cli2.yaml")

    try:
        proc = subprocess.run(
            [str(node), str(_ENTRY), "--config", config_path,
             *tmp_files],
            cwd=tmp, capture_output=True, text=True,
            timeout=30, env=env, check=False,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        print(f"BLOCK: execution failed: {exc}", file=sys.stderr)
        return 2

    if proc.returncode == 0:
        return 0
    if proc.returncode == 1:
        if proc.stdout:
            print(proc.stdout, file=sys.stderr)
        if proc.stderr:
            print(proc.stderr, file=sys.stderr)
        return 1
    print(f"BLOCK: exited {proc.returncode}", file=sys.stderr)
    return 2


def main(files: list[str]) -> int:
    """Verify markdown files. Returns 0/1/2 (pass/violation/block)."""
    if not files:
        return 0

    node = _resolve_system_node()
    error = _check_prerequisites(node)
    if error:
        print(f"BLOCK: {error}", file=sys.stderr)
        return 2

    with tempfile.TemporaryDirectory(prefix="mdlint-") as tmp:
        tmp_files = _copy_to_sterile_dir(files, Path(tmp))
        if not tmp_files:
            return 0
        assert node is not None  # guaranteed by _check_prerequisites
        return _run_linter(node, tmp_files, tmp)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
