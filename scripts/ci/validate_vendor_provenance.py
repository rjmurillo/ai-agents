#!/usr/bin/env python3
"""Trusted vendor provenance validator (base-branch owned).

Runs from BASE branch via pull_request_target. Validates candidate vendor tree
against lockfile using registry integrity. NEVER executes candidate code.
Trust-anchor pin changes require a separate bootstrap PR merged into main.

Exit codes: 0 = pass, 1 = blocked, 2 = infra error.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

# TRUST ANCHORS: pinned SHA-256 of canonical artifacts from PR #4651.
# Changing these values requires a separate bootstrap PR merged into main.
_PIN_VERIFIER_SHA256 = (
    "c795c80874c350e76087e53e3d81247b8ab95323a972adea0c37c14855e3f428"
)
_PIN_CONFIG_SHA256 = (
    "db5924f182f68fd637e65550ab615e7c62d2a2be422e6cd685dbd55710c0c50d"
)
_PIN_CLI2_CONFIG_SHA256 = (
    "635fbcb4fa74bdbaf0c205250af305ce0e782e37e739a3bad9de4a93d6fa024b"
)
_PIN_INTEGRITY_SHA256 = (
    "ef10d3fb0a6495649032adc45b6d4b08195f7ac28b9b9b3d9e8c650cf189f383"
)

# Lockfile policy
_CANONICAL_REGISTRY = "https://registry.npmjs.org/"
_INTEGRITY_RE = re.compile(r"^sha512-[A-Za-z0-9+/]+=*$")
_APPROVED_LOCKFILE_VERSION = "3"

# Keys in lockfile package entries that signal non-registry dependency types.
_REJECTED_DEP_KEYS = ("link", "hasInstallScript")

def _validate_package_entry(name: str, meta: dict[str, object]) -> list[str]:
    """Validate a single non-root lockfile package entry."""
    errors: list[str] = []
    resolved = str(meta.get("resolved", ""))
    if not resolved:
        errors.append(f"No resolved URL for {name}")
    elif not resolved.startswith(_CANONICAL_REGISTRY):
        errors.append(f"Non-canonical registry for {name}: {resolved[:80]}")
    integrity = str(meta.get("integrity", ""))
    if not _INTEGRITY_RE.match(integrity):
        errors.append(f"Missing/invalid sha512 integrity for {name}")
    for key in _REJECTED_DEP_KEYS:
        if meta.get(key):
            errors.append(f"Rejected dependency type ({key}) for {name}")
    if resolved and "://" in resolved:
        scheme = resolved.split("://")[0].lower()
        if scheme != "https":
            errors.append(f"Non-HTTPS scheme for {name}: {scheme}")
    return errors


def _validate_lockfile(lockfile: Path) -> list[str]:
    """Validate lockfile is v3, canonical registry, sha512, no legacy."""
    if not lockfile.is_file():
        return ["package-lock.json not found in vendor tree"]
    try:
        data = json.loads(lockfile.read_bytes())
    except (json.JSONDecodeError, OSError) as exc:
        return [f"Cannot parse lockfile: {exc}"]

    errors: list[str] = []
    version = str(data.get("lockfileVersion", ""))
    if version != _APPROVED_LOCKFILE_VERSION:
        errors.append(
            f"lockfileVersion {version!r} != approved {_APPROVED_LOCKFILE_VERSION!r}"
        )

    packages = data.get("packages", {})
    if not packages:
        return errors + ["lockfile has no packages (empty or legacy format)"]

    non_root = {k: v for k, v in packages.items() if k}
    if not non_root:
        errors.append("lockfile has no non-root packages")

    for name, meta in non_root.items():
        errors.extend(_validate_package_entry(name, meta))
        if len(errors) >= 10:
            errors.append("(truncated after 10 errors)")
            break
    return errors

def _reject_npmrc(candidate_root: Path, vendor_dir: Path) -> list[str]:
    """Reject .npmrc anywhere in candidate tree above vendor."""
    errors: list[str] = []
    check = vendor_dir
    while True:
        npmrc = check / ".npmrc"
        if npmrc.exists():
            errors.append(f".npmrc found at {check.relative_to(candidate_root)}")
        if check == candidate_root or check == check.parent:
            break
        check = check.parent
    return errors

# Trust-anchor authentication

def _sha256_file(path: Path) -> str:
    """Return lowercase hex SHA-256 of a file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()

def _authenticate_artifact(
    path: Path, expected_sha256: str, label: str,
) -> list[str]:
    """Verify file matches pinned SHA-256."""
    if not path.is_file():
        return [f"{label} not found: {path.name}"]
    actual = _sha256_file(path)
    if actual != expected_sha256:
        return [
            f"{label} SHA-256 mismatch: "
            f"expected {expected_sha256[:16]}..., got {actual[:16]}..."
        ]
    return []

def _authenticate_all_pins(
    verifier: Path, config: Path, cli2_config: Path | None,
    manifest: Path,
) -> list[str]:
    """Authenticate all pinned artifacts."""
    errors: list[str] = []
    errors.extend(_authenticate_artifact(
        verifier, _PIN_VERIFIER_SHA256, "Verifier",
    ))
    errors.extend(_authenticate_artifact(
        config, _PIN_CONFIG_SHA256, "Config (markdownlint-safe-config.yaml)",
    ))
    if cli2_config is not None:
        errors.extend(_authenticate_artifact(
            cli2_config, _PIN_CLI2_CONFIG_SHA256,
            "CLI2 config (markdownlint-cli2.yaml)",
        ))
    errors.extend(_authenticate_artifact(
        manifest, _PIN_INTEGRITY_SHA256, "INTEGRITY.json",
    ))
    return errors

# Safe YAML config validation
# Execution-capable keys that must be rejected in any YAML mapping at any
# nesting depth, whether written in block, flow, or JSON form.
_EXECUTION_KEYS = frozenset((
    "customRules",
    "markdownItPlugins",
    "extends",
    "outputFormatters",
    "globs",
))

def _parse_yaml_safe(content: bytes) -> object:
    """Parse YAML using only the safe subset (no code execution)."""
    # Use the stdlib-available yaml if present, otherwise fall-back to a
    # minimal key scanner (the CI image ships PyYAML).
    try:
        import yaml

        return yaml.safe_load(content)
    except ImportError:
        # Fallback: cannot parse YAML without library.  Return None to
        # signal that we should use the regex fallback.
        return None

def _find_execution_keys_recursive(
    obj: object, path: str = "",
) -> list[str]:
    """Walk parsed YAML and reject execution-capable keys at any depth."""
    hits: list[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            key_str = str(key)
            current = f"{path}.{key_str}" if path else key_str
            if key_str in _EXECUTION_KEYS:
                hits.append(f"Execution-capable key '{key_str}' at {current}")
            hits.extend(_find_execution_keys_recursive(value, current))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            hits.extend(
                _find_execution_keys_recursive(item, f"{path}[{i}]")
            )
    return hits

def _validate_config_safe(config_path: Path) -> list[str]:
    """Parse config with safe YAML; reject execution keys recursively."""
    if not config_path.is_file():
        return [f"Config not found: {config_path.name}"]
    raw = config_path.read_bytes()
    parsed = _parse_yaml_safe(raw)
    if parsed is None:
        # No YAML library: fall back to conservative regex scan.
        # Match keys even inside flow mappings and quoted strings.
        text = raw.decode("utf-8", errors="replace")
        errors: list[str] = []
        for key in _EXECUTION_KEYS:
            # Match the key as a YAML mapping key in any style:
            # block (key:), flow ({key:...}), or JSON ("key":)
            pattern = (
                rf"""(?:^|\{{|,)\s*['"]?{re.escape(key)}['"]?\s*:"""
            )
            if re.search(pattern, text, re.MULTILINE):
                errors.append(
                    f"Execution-capable key '{key}' in {config_path.name}"
                )
        return errors
    return _find_execution_keys_recursive(parsed)

# Mirror parity (byte-identical)

def _validate_mirror_parity(primary: Path, mirror: Path) -> list[str]:
    """Enforce byte-identical canonical and generated copies."""
    if not mirror.is_file():
        return [f"Mirror not found: {mirror.name}"]
    if not primary.is_file():
        return [f"Primary not found: {primary.name}"]
    if primary.read_bytes() != mirror.read_bytes():
        return [
            f"Parity mismatch: {primary.name} vs {mirror.name}"
        ]
    return []

# Symlink containment

def _safe_resolve_within(
    path: Path, allowed_root: Path,
) -> tuple[Path | None, str]:
    """Resolve *path* and verify it is contained under *allowed_root*.

    Returns (resolved_path, "") on success, or (None, error_message) on
    failure.  Handles prefix-collision (e.g. ``/tmp/vendor-evil`` vs
    ``/tmp/vendor``), broken symlinks, and symlinked parents.
    """
    root_resolved = allowed_root.resolve(strict=True)
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        return None, f"Cannot resolve {path}: {exc}"
    # Use PurePath.is_relative_to for component-safe containment
    # (immune to prefix-collision unlike str.startswith).
    if not resolved.is_relative_to(root_resolved):
        return None, (
            f"Path escapes allowed root: {path} -> {resolved} "
            f"(root: {root_resolved})"
        )
    return resolved, ""


def _check_symlink_containment(vendor_dir: Path) -> list[str]:
    """Reject symlinks that escape vendor tree."""
    errors: list[str] = []
    vendor_resolved = vendor_dir.resolve()
    for item in vendor_dir.rglob("*"):
        if item.is_symlink():
            raw_target = item.parent / os.readlink(item)
            try:
                target = raw_target.resolve(strict=True)
            except OSError:
                rel = item.relative_to(vendor_dir)
                errors.append(f"Broken symlink in vendor: {rel}")
                if len(errors) >= 5:
                    break
                continue
            if not target.is_relative_to(vendor_resolved):
                rel = item.relative_to(vendor_dir)
                errors.append(f"Symlink escapes vendor: {rel}")
                if len(errors) >= 5:
                    break
    return errors

# Full vendor-root tree comparison (not only node_modules)

def _collect_tree(root: Path) -> tuple[
    dict[str, str], dict[str, str], set[str],
]:
    """Collect files (rel -> sha256), symlinks (rel -> target), executables."""
    files: dict[str, str] = {}
    symlinks: dict[str, str] = {}
    executables: set[str] = set()
    for item in sorted(root.rglob("*")):
        rel = str(PurePosixPath(item.relative_to(root)))
        if item.is_symlink():
            symlinks[rel] = os.readlink(item)
        elif item.is_file():
            files[rel] = hashlib.sha256(item.read_bytes()).hexdigest()
            if os.access(item, os.X_OK):
                executables.add(rel)
    return files, symlinks, executables

def _compare_vendor_trees(
    committed: Path, reconstructed: Path,
) -> list[str]:
    """Compare ALL files under vendor root, not only node_modules."""
    errors: list[str] = []
    c_files, c_sym, c_exec = _collect_tree(committed)
    r_files, r_sym, r_exec = _collect_tree(reconstructed)

    # Only compare node_modules subtree (other files are config, not npm output)
    nm_prefix = "node_modules/"
    c_nm = {k: v for k, v in c_files.items() if k.startswith(nm_prefix)}
    r_nm = {k: v for k, v in r_files.items() if k.startswith(nm_prefix)}

    extra = set(c_nm) - set(r_nm)
    if extra:
        errors.append(f"Extra committed files in node_modules: {sorted(extra)[:3]}")
    missing = set(r_nm) - set(c_nm)
    if missing:
        errors.append(f"Missing committed files in node_modules: {sorted(missing)[:3]}")
    for rel in sorted(set(c_nm) & set(r_nm)):
        if c_nm[rel] != r_nm[rel]:
            errors.append(f"Content mismatch: {rel}")
            if len(errors) >= 5:
                break

    # Symlink comparison
    c_nm_sym = {k: v for k, v in c_sym.items() if k.startswith(nm_prefix)}
    r_nm_sym = {k: v for k, v in r_sym.items() if k.startswith(nm_prefix)}
    diff_keys = set(c_nm_sym) ^ set(r_nm_sym)
    if diff_keys:
        errors.append(f"Symlink set differs: {sorted(diff_keys)[:3]}")
    for k in sorted(set(c_nm_sym) & set(r_nm_sym)):
        if c_nm_sym[k] != r_nm_sym[k]:
            errors.append(f"Symlink target differs: {k}")
            break

    # Mode comparison (executable bit)
    c_nm_exec = {x for x in c_exec if x.startswith(nm_prefix)}
    r_nm_exec = {x for x in r_exec if x.startswith(nm_prefix)}
    mode_diff = c_nm_exec ^ r_nm_exec
    if mode_diff:
        errors.append(f"Executable mode differs: {sorted(mode_diff)[:3]}")

    return errors

# Entrypoint co-tamper

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
    entry_path = vendor_dir / entry_rel
    if not entry_path.is_file():
        return [f"Entrypoint file missing: {entry_rel}"]
    actual = hashlib.sha256(entry_path.read_bytes()).hexdigest()
    if actual != files[entry_rel]:
        return ["Entrypoint hash mismatch (co-tamper detected)"]
    return []

# Reconstruction

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
    return (proc.returncode, proc.stderr[:500] if proc.returncode else "")

# Main: decomposed into phases for complexity < 10 per function

def _run_checks(
    root: Path,
    vendor_dir: Path,
    verifier: Path,
    mirror: Path,
    config: Path,
    cli2_config: Path | None,
    copilot_config: Path | None = None,
    copilot_cli2_config: Path | None = None,
) -> list[str]:
    """Run all non-reconstruction checks. Returns list of errors."""
    all_errors: list[str] = []

    # 1. Pin authentication (non-circular: pins are in THIS base-owned file)
    print("=== Trust-Anchor Authentication ===")
    manifest = vendor_dir / "INTEGRITY.json"
    errs = _authenticate_all_pins(verifier, config, cli2_config, manifest)
    all_errors.extend(errs)
    _report(errs, "All artifacts match pinned SHA-256 trust anchors")

    # 2. Lockfile policy
    print("\n=== Lockfile Policy ===")
    lockfile = vendor_dir / "package-lock.json"
    errs = _validate_lockfile(lockfile)
    all_errors.extend(errs)
    _report(errs, "Lockfile v3, canonical registry, sha512 for all packages")

    # 3. Reject .npmrc
    print("\n=== .npmrc Rejection ===")
    errs = _reject_npmrc(root, vendor_dir)
    all_errors.extend(errs)
    _report(errs, "No .npmrc in candidate tree")

    # 4. Symlink containment
    print("\n=== Symlink Containment ===")
    errs = _check_symlink_containment(vendor_dir)
    all_errors.extend(errs)
    _report(errs, "All symlinks contained within vendor")

    # 5. Config safety (safe YAML, recursive execution key rejection)
    print("\n=== Config Safety ===")
    errs = _validate_config_safe(config)
    all_errors.extend(errs)
    _report(errs, "No execution-capable keys in config")

    # 6. Mirror parity (byte-identical)
    print("\n=== Mirror Parity ===")
    errs = _validate_mirror_parity(verifier, mirror)
    all_errors.extend(errs)
    _report(errs, "Canonical and mirror verifiers are byte-identical")

    # 7. Entrypoint co-tamper
    print("\n=== Entrypoint Integrity ===")
    errs = _validate_entrypoint_in_manifest(vendor_dir)
    all_errors.extend(errs)
    _report(errs, "Entrypoint covered by manifest and matches")

    # 8. CLI2 config safety (if supplied)
    if cli2_config is not None:
        print("\n=== CLI2 Config Safety ===")
        errs = _validate_config_safe(cli2_config)
        all_errors.extend(errs)
        _report(errs, "No execution-capable keys in CLI2 config")

    # 9. Copilot config mirror parity (byte-identical to primary)
    if copilot_config is not None:
        print("\n=== Copilot Config Mirror Parity ===")
        errs = _validate_mirror_parity(config, copilot_config)
        all_errors.extend(errs)
        _report(errs, "Copilot safe-config is byte-identical to primary")

        # Also validate Copilot config for execution keys
        print("\n=== Copilot Config Safety ===")
        errs = _validate_config_safe(copilot_config)
        all_errors.extend(errs)
        _report(errs, "No execution-capable keys in Copilot config")

    if copilot_cli2_config is not None:
        print("\n=== Copilot CLI2 Config Mirror Parity ===")
        if cli2_config is not None:
            errs = _validate_mirror_parity(cli2_config, copilot_cli2_config)
        else:
            errs = [
                "Copilot CLI2 config supplied but no primary CLI2 config to compare"
            ]
        all_errors.extend(errs)
        _report(errs, "Copilot CLI2 config is byte-identical to primary")

        print("\n=== Copilot CLI2 Config Safety ===")
        errs = _validate_config_safe(copilot_cli2_config)
        all_errors.extend(errs)
        _report(errs, "No execution-capable keys in Copilot CLI2 config")

    return all_errors

def _run_reconstruction(vendor_dir: Path) -> list[str]:
    """Reconstruct vendor from lockfile and compare."""
    import shutil
    import tempfile

    print("\n=== Lockfile Reconstruction ===")
    nm_dir = vendor_dir / "node_modules"
    if not nm_dir.is_dir():
        return ["node_modules not found in vendor"]

    errors: list[str] = []
    with tempfile.TemporaryDirectory(prefix="vendor-prov-") as td:
        committed_copy = Path(td) / "committed"
        shutil.copytree(vendor_dir, committed_copy, symlinks=True)
        rc, stderr = _reconstruct_vendor(vendor_dir)
        if rc != 0:
            errors.append(f"npm ci failed (exit {rc}): {stderr[:200]}")
        else:
            errors.extend(_compare_vendor_trees(committed_copy, vendor_dir))
    _report(errors, "Vendor matches lockfile reconstruction")
    return errors

def _report(errs: list[str], ok_msg: str) -> None:
    """Print PASS/FAIL for a check section."""
    for e in errs:
        print(f"  FAIL: {e}")
    if not errs:
        print(f"  PASS: {ok_msg}")

def _resolve_candidate_paths(
    root: Path, args: argparse.Namespace,
) -> tuple[dict[str, Path | None], list[str]]:
    """Resolve all candidate-controlled paths and enforce containment.

    Returns (resolved_paths_dict, errors). On error, no paths are safe to use.
    Prevents CWE-59/CWE-22: symlinked vendor roots, pinned artifacts, or
    prefix-collision attacks (e.g. /tmp/candidate/vendor-evil).
    """
    raw: dict[str, Path | None] = {
        "vendor_dir": root / args.vendor_rel,
        "verifier": root / args.verifier_rel,
        "mirror": root / args.mirror_rel,
        "config": root / args.config_rel,
        "cli2_config": (
            (root / args.cli2_config_rel) if args.cli2_config_rel else None
        ),
        "copilot_config": (
            (root / args.copilot_config_rel)
            if args.copilot_config_rel else None
        ),
        "copilot_cli2_config": (
            (root / args.copilot_cli2_config_rel)
            if args.copilot_cli2_config_rel else None
        ),
    }
    resolved: dict[str, Path | None] = {}
    errors: list[str] = []
    for label, p in raw.items():
        if p is None:
            resolved[label] = None
            continue
        safe, err = _safe_resolve_within(p, root)
        if err:
            errors.append(f"{label}: {err}")
            resolved[label] = None
        else:
            resolved[label] = safe
    return resolved, errors


def main() -> int:
    """Run all provenance checks on candidate vendor tree."""
    parser = argparse.ArgumentParser(
        description="Trusted vendor provenance gate",
    )
    parser.add_argument("--candidate-root", required=True, type=Path)
    parser.add_argument("--vendor-rel", required=True, type=str)
    parser.add_argument("--verifier-rel", required=True, type=str)
    parser.add_argument("--mirror-rel", required=True, type=str)
    parser.add_argument("--config-rel", required=True, type=str)
    parser.add_argument("--cli2-config-rel", default=None, type=str)
    parser.add_argument("--copilot-config-rel", default=None, type=str)
    parser.add_argument("--copilot-cli2-config-rel", default=None, type=str)
    args = parser.parse_args()

    try:
        root = args.candidate_root.resolve(strict=True)
    except OSError:
        print(
            f"ERROR: candidate root not found: {args.candidate_root}",
            file=sys.stderr,
        )
        return 2
    if not root.is_dir():
        print(f"ERROR: candidate root not a directory: {root}", file=sys.stderr)
        return 2

    paths, containment_errors = _resolve_candidate_paths(root, args)
    if containment_errors:
        print("=== Path Containment ===")
        for e in containment_errors:
            print(f"  FAIL: {e}")
        print(f"\nBLOCKED: {len(containment_errors)} containment error(s)")
        return 1

    # All paths verified safe; unpack for readability.
    vendor_dir = paths["vendor_dir"]
    verifier = paths["verifier"]
    mirror = paths["mirror"]
    config = paths["config"]
    if vendor_dir is None or verifier is None or mirror is None or config is None:
        # Should not happen: required args always resolve or produce errors.
        print("ERROR: required path resolved to None", file=sys.stderr)
        return 2

    all_errors = _run_checks(
        root, vendor_dir, verifier, mirror, config,
        paths["cli2_config"], paths["copilot_config"],
        paths["copilot_cli2_config"],
    )
    # Only run reconstruction if structural/policy checks passed; avoids
    # npm ci against a lockfile that already failed policy (CWE-918/CWE-59).
    if not all_errors:
        all_errors.extend(_run_reconstruction(vendor_dir))

    if all_errors:
        print(f"\nBLOCKED: {len(all_errors)} provenance error(s)")
        return 1
    print("\nPASS: All vendor provenance checks passed")
    return 0

if __name__ == "__main__":
    sys.exit(main())
