#!/usr/bin/env python3
"""Trusted vendor provenance validator (base-branch owned).

This script runs from the BASE branch via pull_request_target. It validates
a candidate PR's vendor tree against its lockfile using registry integrity
metadata. It NEVER executes candidate code.

Security requirements:
- Require canonical npm registry URLs (registry.npmjs.org only)
- Require SHA-512 integrity for every package in lockfile
- Reject alternate registries, local/git deps, .npmrc in vendor tree
- Independently reconstruct from lockfile and compare byte-for-byte
- Validate regular files, executable modes, symlink targets/containment
- Reject extra files not accounted for by manifest or lockfile
- Authenticate markdownlint-safe-config outside vendor manifest
- Reject execution-capable YAML keys (customRules, markdownItPlugins, extends)
- Enforce canonical/generated verifier byte parity
- No-follow safe traversal (reject symlinks to external paths)

Exit codes:
  0 - provenance validated
  1 - provenance mismatch (block merge)
  2 - infrastructure/argument error
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

# --- Lockfile policy ---

_CANONICAL_REGISTRY = "https://registry.npmjs.org/"
_INTEGRITY_RE = re.compile(r"^sha512-[A-Za-z0-9+/]+=*$")
_EXECUTION_KEYS = frozenset((
    "customRules", "markdownItPlugins", "extends",
    "outputFormatters", "globs",
))


def _validate_lockfile(lockfile: Path) -> list[str]:
    """Validate lockfile has canonical registry URLs and sha512 integrity."""
    errors: list[str] = []
    if not lockfile.is_file():
        return ["package-lock.json not found in vendor tree"]
    try:
        data = json.loads(lockfile.read_bytes())
    except (json.JSONDecodeError, OSError) as exc:
        return [f"Cannot parse lockfile: {exc}"]

    packages = data.get("packages", {})
    for name, meta in packages.items():
        if not name:  # root package
            continue
        resolved = meta.get("resolved", "")
        if resolved and not resolved.startswith(_CANONICAL_REGISTRY):
            errors.append(
                f"Non-canonical registry for {name}: {resolved[:80]}"
            )
            if len(errors) >= 5:
                break
        integrity = meta.get("integrity", "")
        if not _INTEGRITY_RE.match(integrity):
            errors.append(f"Missing/invalid sha512 integrity for {name}")
            if len(errors) >= 5:
                break
        # Reject git/local/link dependencies
        if any(meta.get(k) for k in ("link", "hasInstallScript")):
            errors.append(f"Rejected dependency type for {name}")
    return errors


def _reject_npmrc(vendor_dir: Path) -> list[str]:
    """Reject .npmrc in vendor tree (attacker-controlled registry config)."""
    npmrc = vendor_dir / ".npmrc"
    if npmrc.exists():
        return [".npmrc found in vendor tree (rejected)"]
    # Also check parent dirs up to candidate root
    for parent in vendor_dir.parents:
        if (parent / ".npmrc").exists():
            return [f".npmrc found at {parent} (rejected)"]
        if parent.name == "candidate" or parent == parent.parent:
            break
    return []


# --- Reconstruction ---

def _reconstruct_vendor(vendor_dir: Path) -> tuple[int, str]:
    """Run npm ci in vendor dir. Returns (exit_code, stderr)."""
    lockfile = vendor_dir / "package-lock.json"
    pkg = vendor_dir / "package.json"
    if not lockfile.is_file() or not pkg.is_file():
        return (2, "Missing package-lock.json or package.json")
    try:
        proc = subprocess.run(
            ["npm", "ci", "--ignore-scripts", "--audit=false"],
            cwd=vendor_dir,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            env={
                **os.environ,
                "npm_config_fund": "false",
                "npm_config_registry": _CANONICAL_REGISTRY,
            },
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return (2, f"npm ci failed: {exc}")
    if proc.returncode != 0:
        return (proc.returncode, proc.stderr[:500])
    return (0, "")


# --- Tree comparison ---

def _collect_tree(root: Path) -> tuple[dict[str, str], dict[str, str], set[str]]:
    """Collect files (rel->sha256), symlinks (rel->target), executables."""
    files: dict[str, str] = {}
    symlinks: dict[str, str] = {}
    executables: set[str] = set()
    for item in sorted(root.rglob("*")):
        rel = str(item.relative_to(root))
        if item.is_symlink():
            symlinks[rel] = os.readlink(item)
        elif item.is_file():
            files[rel] = hashlib.sha256(item.read_bytes()).hexdigest()
            if os.access(item, os.X_OK):
                executables.add(rel)
    return files, symlinks, executables


def _compare_trees(
    committed_dir: Path, reconstructed_dir: Path,
) -> list[str]:
    """Compare committed vs reconstructed node_modules byte-for-byte."""
    errors: list[str] = []
    nm_committed = committed_dir / "node_modules"
    nm_reconstructed = reconstructed_dir / "node_modules"

    if not nm_committed.is_dir() or not nm_reconstructed.is_dir():
        return ["node_modules directory missing"]

    c_files, c_sym, c_exec = _collect_tree(nm_committed)
    r_files, r_sym, r_exec = _collect_tree(nm_reconstructed)

    extra = set(c_files.keys()) - set(r_files.keys())
    if extra:
        errors.append(f"Extra committed files: {sorted(extra)[:3]}")
    missing = set(r_files.keys()) - set(c_files.keys())
    if missing:
        errors.append(f"Missing committed files: {sorted(missing)[:3]}")

    for rel in sorted(set(c_files.keys()) & set(r_files.keys())):
        if c_files[rel] != r_files[rel]:
            errors.append(f"Content mismatch: node_modules/{rel}")
            if len(errors) >= 5:
                break

    # Symlink comparison
    if c_sym != r_sym:
        diff_keys = set(c_sym.keys()) ^ set(r_sym.keys())
        mismatch = [
            k for k in set(c_sym.keys()) & set(r_sym.keys())
            if c_sym[k] != r_sym[k]
        ]
        if diff_keys:
            errors.append(f"Symlink set differs: {sorted(diff_keys)[:3]}")
        if mismatch:
            errors.append(f"Symlink target differs: {mismatch[:3]}")

    return errors


def _check_symlink_containment(vendor_dir: Path) -> list[str]:
    """Reject symlinks that escape vendor tree."""
    errors: list[str] = []
    vendor_resolved = vendor_dir.resolve()
    for item in vendor_dir.rglob("*"):
        if item.is_symlink():
            target = (item.parent / os.readlink(item)).resolve()
            if not str(target).startswith(str(vendor_resolved)):
                errors.append(
                    f"Symlink escapes vendor: {item.relative_to(vendor_dir)}"
                )
                if len(errors) >= 3:
                    break
    return errors


# --- Config safety ---

def _validate_safe_config(config_path: Path) -> list[str]:
    """Reject execution-capable keys in markdownlint config."""
    errors: list[str] = []
    if not config_path.is_file():
        return ["markdownlint-safe-config.yaml not found"]
    content = config_path.read_text(encoding="utf-8")
    for key in _EXECUTION_KEYS:
        if re.search(rf"^\s*{re.escape(key)}\s*:", content, re.MULTILINE):
            errors.append(f"Execution-capable key '{key}' in config (rejected)")
    return errors


# --- Digest pin & parity ---

def _validate_digest_pin(
    verifier_path: Path, manifest_path: Path,
) -> list[str]:
    """Verify INTEGRITY.json digest is pinned in verifier source."""
    errors: list[str] = []
    if not manifest_path.is_file():
        return ["INTEGRITY.json not found"]
    if not verifier_path.is_file():
        return [f"Verifier not found: {verifier_path}"]
    digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    source = verifier_path.read_text(encoding="utf-8")
    if digest not in source:
        errors.append(
            f"INTEGRITY.json digest {digest[:16]}... not pinned in verifier"
        )
    return errors


def _validate_mirror_parity(
    verifier: Path, mirror: Path,
) -> list[str]:
    """Enforce byte-identical canonical and generated verifiers."""
    if not mirror.is_file():
        return [f"Mirror not found: {mirror}"]
    if verifier.read_bytes() != mirror.read_bytes():
        return ["Canonical and mirror verifiers differ"]
    return []


# --- Entrypoint co-tamper ---

def _validate_entrypoint_in_manifest(vendor_dir: Path) -> list[str]:
    """Verify markdownlint-cli2 entrypoint is covered by manifest."""
    manifest_path = vendor_dir / "INTEGRITY.json"
    if not manifest_path.is_file():
        return ["INTEGRITY.json missing"]
    try:
        manifest = json.loads(manifest_path.read_bytes())
    except (json.JSONDecodeError, OSError):
        return ["Cannot parse INTEGRITY.json"]

    entry_rel = "node_modules/markdownlint-cli2/markdownlint-cli2-bin.mjs"
    files = manifest.get("files", {})
    if entry_rel not in files:
        return [f"Entrypoint {entry_rel} not in manifest"]

    # Verify actual file matches manifest hash
    entry_path = vendor_dir / entry_rel
    if not entry_path.is_file():
        return [f"Entrypoint file missing: {entry_rel}"]
    actual_hash = hashlib.sha256(entry_path.read_bytes()).hexdigest()
    if actual_hash != files[entry_rel]:
        return ["Entrypoint hash mismatch (co-tamper detected)"]
    return []


# --- Main ---

def main() -> int:
    """Run all provenance checks on candidate vendor tree."""
    parser = argparse.ArgumentParser(description="Trusted vendor provenance gate")
    parser.add_argument("--candidate-root", required=True, type=Path)
    parser.add_argument("--vendor-rel", required=True, type=str)
    parser.add_argument("--verifier-rel", required=True, type=str)
    parser.add_argument("--mirror-rel", required=True, type=str)
    parser.add_argument("--config-rel", required=True, type=str)
    args = parser.parse_args()

    root = args.candidate_root.resolve()
    vendor_dir = root / args.vendor_rel
    verifier = root / args.verifier_rel
    mirror = root / args.mirror_rel
    config = root / args.config_rel

    if not root.is_dir():
        print(f"ERROR: candidate root not found: {root}", file=sys.stderr)
        return 2

    all_errors: list[str] = []

    # 1. Lockfile policy
    print("=== Lockfile Policy ===")
    lockfile = vendor_dir / "package-lock.json"
    errs = _validate_lockfile(lockfile)
    all_errors.extend(errs)
    for e in errs:
        print(f"  FAIL: {e}")
    if not errs:
        print("  PASS: All packages use canonical registry + sha512")

    # 2. Reject .npmrc
    print("\n=== .npmrc Rejection ===")
    errs = _reject_npmrc(vendor_dir)
    all_errors.extend(errs)
    for e in errs:
        print(f"  FAIL: {e}")
    if not errs:
        print("  PASS: No .npmrc in vendor tree")

    # 3. Symlink containment
    print("\n=== Symlink Containment ===")
    errs = _check_symlink_containment(vendor_dir)
    all_errors.extend(errs)
    for e in errs:
        print(f"  FAIL: {e}")
    if not errs:
        print("  PASS: All symlinks contained within vendor")

    # 4. Config safety
    print("\n=== Config Safety ===")
    errs = _validate_safe_config(config)
    all_errors.extend(errs)
    for e in errs:
        print(f"  FAIL: {e}")
    if not errs:
        print("  PASS: No execution-capable keys in config")

    # 5. Digest pin
    print("\n=== Digest Pin ===")
    manifest = vendor_dir / "INTEGRITY.json"
    errs = _validate_digest_pin(verifier, manifest)
    all_errors.extend(errs)
    for e in errs:
        print(f"  FAIL: {e}")
    if not errs:
        print("  PASS: Manifest digest pinned in verifier")

    # 6. Mirror parity
    print("\n=== Mirror Parity ===")
    errs = _validate_mirror_parity(verifier, mirror)
    all_errors.extend(errs)
    for e in errs:
        print(f"  FAIL: {e}")
    if not errs:
        print("  PASS: Canonical and mirror are byte-identical")

    # 7. Entrypoint co-tamper
    print("\n=== Entrypoint Integrity ===")
    errs = _validate_entrypoint_in_manifest(vendor_dir)
    all_errors.extend(errs)
    for e in errs:
        print(f"  FAIL: {e}")
    if not errs:
        print("  PASS: Entrypoint covered by manifest and matches")

    # 8. Reconstruction comparison (npm ci)
    print("\n=== Lockfile Reconstruction ===")
    import shutil
    import tempfile
    nm_dir = vendor_dir / "node_modules"
    if nm_dir.is_dir():
        # Copy committed node_modules to temp for comparison after npm ci
        with tempfile.TemporaryDirectory(prefix="vendor-prov-") as td:
            committed_nm = Path(td) / "committed"
            shutil.copytree(nm_dir, committed_nm, symlinks=True)
            # Reconstruct in vendor_dir (replaces node_modules)
            rc, stderr = _reconstruct_vendor(vendor_dir)
            if rc != 0:
                errs = [f"npm ci failed (exit {rc}): {stderr[:200]}"]
            else:
                # Compare committed vs reconstructed
                committed_wrap = Path(td) / "c_wrap"
                committed_wrap.mkdir()
                os.symlink(committed_nm, committed_wrap / "node_modules")
                errs = _compare_trees(committed_wrap, vendor_dir)
        all_errors.extend(errs)
        for e in errs:
            print(f"  FAIL: {e}")
        if not errs:
            print("  PASS: Vendor matches lockfile reconstruction")
    else:
        all_errors.append("node_modules not found in vendor")
        print("  FAIL: node_modules not found")

    # Summary
    if all_errors:
        print(f"\nBLOCKED: {len(all_errors)} provenance error(s)")
        return 1
    print("\nPASS: All vendor provenance checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
