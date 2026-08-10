#!/usr/bin/env python3
"""Vendor provenance gate for markdownlint-cli2 vendor tree.

Validates that the committed vendor tree exactly matches what npm ci
produces from the lockfile, and that the INTEGRITY.json digest is
correctly pinned in the verifier source. This script is executed from
the BASE BRANCH by the pull_request_target workflow, making it
non-PR-controlled.

Exit codes:
  0 - provenance validated
  1 - provenance mismatch (block merge)
  2 - infrastructure error
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path


def _hash_file(path: Path) -> str:
    """SHA-256 hex digest of a file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _collect_tree(root: Path) -> dict[str, str]:
    """Collect all file hashes in a directory tree."""
    result: dict[str, str] = {}
    for item in sorted(root.rglob("*")):
        if item.is_symlink():
            # Record symlink target as content
            result[str(item.relative_to(root))] = f"symlink:{os.readlink(item)}"
        elif item.is_file():
            result[str(item.relative_to(root))] = _hash_file(item)
    return result


def _check_file_sets(
    actual_files: dict[str, str],
    expected_files: dict[str, str],
) -> list[str]:
    """Check for extra/missing files."""
    errors: list[str] = []
    extra = set(actual_files.keys()) - set(expected_files.keys())
    if extra:
        errors.append(f"Extra files not in manifest: {sorted(extra)[:5]}")
    missing = set(expected_files.keys()) - set(actual_files.keys())
    if missing:
        errors.append(f"Missing files from manifest: {sorted(missing)[:5]}")
    return errors


def _check_file_hashes(
    actual_files: dict[str, str],
    expected_files: dict[str, str],
) -> list[str]:
    """Check file content hashes."""
    for rel, expected_hash in expected_files.items():
        actual_hash = actual_files.get(rel)
        if actual_hash and actual_hash != expected_hash:
            return [f"Hash mismatch: {rel}"]
    return []


def _check_symlink_sets(
    actual_symlinks: dict[str, str],
    expected_symlinks: dict[str, str],
) -> list[str]:
    """Check symlink presence and targets."""
    errors: list[str] = []
    extra = set(actual_symlinks.keys()) - set(expected_symlinks.keys())
    if extra:
        errors.append(f"Extra symlinks: {sorted(extra)[:3]}")
    for rel, target in expected_symlinks.items():
        if actual_symlinks.get(rel) != target:
            errors.append(f"Symlink mismatch: {rel}")
    return errors


def _collect_vendor_tree(
    vendor_dir: Path,
) -> tuple[dict[str, str], dict[str, str]]:
    """Walk vendor tree, return (files_with_hashes, symlinks)."""
    actual_files: dict[str, str] = {}
    actual_symlinks: dict[str, str] = {}
    skip = {"INTEGRITY.json"}
    for item in sorted(vendor_dir.rglob("*")):
        rel = str(item.relative_to(vendor_dir))
        if rel in skip:
            continue
        if item.is_symlink():
            actual_symlinks[rel] = os.readlink(item)
        elif item.is_file():
            actual_files[rel] = hashlib.sha256(item.read_bytes()).hexdigest()
    return actual_files, actual_symlinks


def validate_reconstruction(vendor_dir: Path) -> list[str]:
    """Compare committed node_modules against npm ci reconstruction.

    Assumes npm ci has already been run (by CI step) so vendor_dir/node_modules
    is the reconstructed tree. Compares against INTEGRITY.json manifest.
    """
    manifest_path = vendor_dir / "INTEGRITY.json"
    if not manifest_path.is_file():
        return ["INTEGRITY.json not found in vendor tree"]

    try:
        manifest = json.loads(manifest_path.read_bytes())
    except (json.JSONDecodeError, OSError) as exc:
        return [f"Cannot parse INTEGRITY.json: {exc}"]

    expected_files: dict[str, str] = manifest.get("files", {})
    expected_symlinks: dict[str, str] = manifest.get("symlinks", {})
    actual_files, actual_symlinks = _collect_vendor_tree(vendor_dir)

    errors: list[str] = []
    errors.extend(_check_file_sets(actual_files, expected_files))
    errors.extend(_check_file_hashes(actual_files, expected_files))
    errors.extend(_check_symlink_sets(actual_symlinks, expected_symlinks))
    return errors


def validate_digest_pin(verifier_path: Path, vendor_dir: Path) -> list[str]:
    """Verify INTEGRITY.json digest is pinned in verifier source."""
    errors: list[str] = []
    manifest_path = vendor_dir / "INTEGRITY.json"
    if not manifest_path.is_file():
        errors.append("INTEGRITY.json not found")
        return errors
    if not verifier_path.is_file():
        errors.append(f"Verifier not found: {verifier_path}")
        return errors

    manifest_digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    verifier_source = verifier_path.read_text(encoding="utf-8")

    if manifest_digest not in verifier_source:
        errors.append(
            f"INTEGRITY.json digest {manifest_digest} not pinned in "
            f"{verifier_path.name}. Co-tamper detected."
        )
    return errors


def validate_mirror_parity(
    verifier_path: Path, mirror_path: Path,
) -> list[str]:
    """Verify canonical and mirror verifiers are byte-identical."""
    errors: list[str] = []
    if not mirror_path.is_file():
        errors.append(f"Mirror not found: {mirror_path}")
        return errors
    if verifier_path.read_bytes() != mirror_path.read_bytes():
        errors.append("Verifier and mirror are not byte-identical")
    return errors


def main() -> int:
    """Run all provenance checks."""
    parser = argparse.ArgumentParser(description="Vendor provenance gate")
    parser.add_argument("--vendor-dir", required=True, type=Path)
    parser.add_argument("--verifier", required=True, type=Path)
    parser.add_argument("--mirror", required=True, type=Path)
    args = parser.parse_args()

    all_errors: list[str] = []

    print("=== Vendor Reconstruction Validation ===")
    errs = validate_reconstruction(args.vendor_dir)
    all_errors.extend(errs)
    for e in errs:
        print(f"  FAIL: {e}")
    if not errs:
        print("  PASS: Vendor tree matches lockfile reconstruction")

    print("\n=== Digest Pin Validation ===")
    errs = validate_digest_pin(args.verifier, args.vendor_dir)
    all_errors.extend(errs)
    for e in errs:
        print(f"  FAIL: {e}")
    if not errs:
        print("  PASS: Manifest digest correctly pinned in verifier")

    print("\n=== Mirror Parity ===")
    errs = validate_mirror_parity(args.verifier, args.mirror)
    all_errors.extend(errs)
    for e in errs:
        print(f"  FAIL: {e}")
    if not errs:
        print("  PASS: Canonical and mirror verifiers are identical")

    if all_errors:
        print(f"\nBLOCKED: {len(all_errors)} provenance error(s)")
        return 1
    print("\nPASS: All vendor provenance checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
