#!/usr/bin/env python3
"""Markdownlint verifier using vendored markdownlint-cli2.

Invokes an immutable vendored markdownlint-cli2 0.23.1 via absolute path
with full integrity verification, environment scrubbing, and sterile temp
dir isolation to prevent consumer config/plugin pickup.

Security model:
- Manifest digest pinned in this source file (outside vendor tree)
- Vendor tree materialized into private sterile copy during verification
- TOCTOU eliminated: hashes verified during copy, execution uses only the copy
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
_ENTRY_REL = os.path.join(
    "node_modules", "markdownlint-cli2", "markdownlint-cli2-bin.mjs",
)
_CONFIG = _HERE / "markdownlint-safe-config.yaml"
_INTEGRITY_REL = "INTEGRITY.json"

# Pinned digest of INTEGRITY.json - authenticates the manifest from outside
# the vendor tree. Regenerate with:
#   sha256sum .claude/hooks/PreToolUse/_vendor/markdownlint/INTEGRITY.json
_INTEGRITY_SHA256 = (
    "ef10d3fb0a6495649032adc45b6d4b08195f7ac28b9b9b3d9e8c650cf189f383"
)

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


def _authenticate_manifest() -> dict[str, Any] | None:
    """Load manifest and verify its digest against pinned value."""
    manifest_path = _VENDOR / _INTEGRITY_REL
    if not manifest_path.is_file():
        return None
    try:
        raw = manifest_path.read_bytes()
    except OSError:
        return None
    digest = hashlib.sha256(raw).hexdigest()
    if digest != _INTEGRITY_SHA256:
        return None
    try:
        result: dict[str, Any] = json.loads(raw)
        return result
    except (json.JSONDecodeError, ValueError):
        return None


def _safe_copy_file(src: Path, dst: Path) -> bytes:
    """Read file without following symlinks, write to dst. Return content."""
    fd = os.open(src, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        content = os.read(fd, 50_000_000)  # 50MB max
    finally:
        os.close(fd)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(content)
    return content


def _materialize_verified_copy(
    manifest: dict[str, Any], dest: Path,
) -> str | None:
    """Copy vendor tree to dest, verifying integrity during copy.

    Returns error string or None on success. Uses O_NOFOLLOW for regular
    files to prevent symlink-swap TOCTOU attacks.
    """
    expected_files: dict[str, str] = manifest.get("files", {})
    expected_symlinks: dict[str, str] = manifest.get("symlinks", {})
    expected_execs: list[str] = manifest.get("executables", [])
    all_expected = set(expected_files.keys()) | set(expected_symlinks.keys())

    # Check for extra files/symlinks in source tree
    actual_entries: set[str] = set()
    for item in sorted(_VENDOR.rglob("*")):
        rel = str(item.relative_to(_VENDOR))
        if rel == _INTEGRITY_REL:
            continue
        if item.is_symlink() or item.is_file():
            actual_entries.add(rel)
    extra = actual_entries - all_expected
    if extra:
        return f"extra files in vendor tree: {sorted(extra)[:3]}"
    missing = all_expected - actual_entries
    if missing:
        return f"missing files in vendor tree: {sorted(missing)[:3]}"

    # Copy and verify regular files
    for rel, expected_hash in expected_files.items():
        src = _VENDOR / rel
        dst = dest / rel
        try:
            content = _safe_copy_file(src, dst)
        except OSError as exc:
            return f"cannot read {rel}: {exc}"
        actual_hash = hashlib.sha256(content).hexdigest()
        if actual_hash != expected_hash:
            return f"hash mismatch: {rel}"

    # Verify and recreate symlinks
    for rel, expected_target in expected_symlinks.items():
        src = _VENDOR / rel
        if not src.is_symlink():
            return f"expected symlink: {rel}"
        actual_target = os.readlink(src)
        if actual_target != expected_target:
            return f"symlink mismatch: {rel}"
        # Verify symlink is contained within vendor tree
        resolved = (src.parent / actual_target).resolve()
        if not str(resolved).startswith(str(_VENDOR)):
            return f"symlink escapes vendor: {rel}"
        dst = dest / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(actual_target, dst)

    # Verify and set executable modes
    for rel in expected_execs:
        src = _VENDOR / rel
        if not os.access(src, os.X_OK):
            return f"expected executable: {rel}"
        dst = dest / rel
        if dst.is_file():
            dst.chmod(dst.stat().st_mode | stat.S_IXUSR)

    # Make entire copy read-only
    for item in dest.rglob("*"):
        if item.is_file() and not item.is_symlink():
            item.chmod(stat.S_IRUSR | stat.S_IRGRP)
    for item in dest.rglob("*"):
        if item.is_dir():
            item.chmod(stat.S_IRUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP)

    return None


def _check_prerequisites(node: Path | None) -> str | None:
    """Validate all prerequisites. Returns error message or None."""
    if node is None:
        return "No trusted system Node.js found"
    if not _CONFIG.is_file():
        return "Safe config not found"
    manifest = _authenticate_manifest()
    if manifest is None:
        return "INTEGRITY.json missing, invalid, or digest mismatch"
    return None


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
    node: Path, entry: Path, tmp_files: list[str], tmp: str,
) -> int:
    """Invoke markdownlint-cli2 from verified copy. Returns 0, 1, or 2."""
    tmp_path = Path(tmp)
    shutil.copy2(_CONFIG, tmp_path / ".markdownlint-cli2.yaml")
    env = _allowlisted_env(tmp, node)
    config_path = str(tmp_path / ".markdownlint-cli2.yaml")

    try:
        proc = subprocess.run(
            [str(node), str(entry), "--config", config_path,
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
    assert node is not None  # guaranteed by _check_prerequisites

    manifest = _authenticate_manifest()
    assert manifest is not None  # guaranteed by _check_prerequisites

    with tempfile.TemporaryDirectory(prefix="mdlint-") as tmp:
        # Materialize verified vendor copy (eliminates TOCTOU)
        vendor_copy = Path(tmp) / "_vendor"
        vendor_copy.mkdir()
        mat_error = _materialize_verified_copy(manifest, vendor_copy)
        if mat_error:
            print(f"BLOCK: integrity: {mat_error}", file=sys.stderr)
            return 2

        entry = vendor_copy / _ENTRY_REL
        if not entry.is_file():
            print("BLOCK: entry point missing in verified copy", file=sys.stderr)
            return 2

        # Make entry executable for Node
        entry.chmod(stat.S_IRUSR | stat.S_IXUSR)

        # Copy markdown files to separate sterile subdir
        md_dir = Path(tmp) / "_md"
        md_dir.mkdir()
        tmp_files = _copy_to_sterile_dir(files, md_dir)
        if not tmp_files:
            return 0
        return _run_linter(node, entry, tmp_files, str(md_dir))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
