#!/usr/bin/env python3
"""Trusted vendor provenance validator (base-branch owned, standalone).

Runs from BASE branch via pull_request_target. Authenticates every
pre-verification executable, generated counterpart, config, manifest, and
vendor tree in a candidate PR. Imports NO candidate modules before or
during verification. Trust-anchor pin changes require a separate bootstrap
PR merged into main.

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

# ── Trust-anchor pins (SHA-256, lowercase hex) ──
# Each entry: (relative path in candidate, expected sha256, label).
# Pins cover every file that executes BEFORE or DURING verification,
# plus generated counterparts and configs. Future vendor/runtime PRs
# add new pins here via a bootstrap update PR.
_PINNED_ARTIFACTS: list[tuple[str, str, str]] = [
    # --- Hook executables (pre-verification) ---
    (
        ".claude/hooks/PreToolUse/_bootstrap.py",
        "8f1af9122ae5d58e6b4ccd2c9918005c0832bb6b8e4c16cf449c2f53420ccbf1",
        "Hook bootstrap",
    ),
    (
        ".claude/hooks/PreToolUse/invoke_markdownlint_guard.py",
        "236e1310f325bbb5c6fea8d71af61a578e58e7fe72c9f2c14a6903bb9122fb76",
        "Markdownlint guard invoker",
    ),
    (
        ".claude/hooks/PreToolUse/push_guard_base.py",
        "06350d22bfe67737ffede2abd71dcd761d751dd41081da83d30254a8c14785ff",
        "Push guard base",
    ),
    # --- Generated counterparts (copilot-cli mirrors) ---
    (
        "src/copilot-cli/hooks/PreToolUse/_bootstrap.py",
        "8f1af9122ae5d58e6b4ccd2c9918005c0832bb6b8e4c16cf449c2f53420ccbf1",
        "Generated bootstrap mirror",
    ),
    (
        "src/copilot-cli/hooks/PreToolUse/push_guard_base.py",
        "080ecaed5dfc7bc26db053ab824ed2f22b8f3b99d80e401bbd09e9a8d467f6ba",
        "Generated push_guard_base mirror",
    ),
    (
        "src/copilot-cli/hooks/PreToolUse/"
        "invoke_markdownlint_guard__Bash_git_push_0e93bf.py",
        "2016218b8e3be302820c0b0c97cd7f95370381d6b171cb244919e9a2e3215e92",
        "Generated markdownlint guard mirror",
    ),
    # --- Copilot-CLI dispatch ---
    (
        "src/copilot-cli/hooks/PreToolUse/_dispatch.py",
        "9324714377e69ea297dd429acc3a7eafa24c43af75f06cdba29596d25090eef9",
        "Generated dispatch",
    ),
    # --- Generator surface ---
    (
        "build/scripts/generate_hooks_events.py",
        "2d3b7c11ee600e57483b950f67f40c1da52ff80ce0f14db584fdc93ea3cbe8eb",
        "Hook event generator",
    ),
    # --- Vendor artifacts (added by vendor/runtime PR) ---
    # Uncomment and pin when the vendor PR is created:
    # (".claude/hooks/PreToolUse/_markdownlint_verifier.py", "<sha256>", "Verifier"),
    # (".claude/hooks/PreToolUse/markdownlint-safe-config.yaml", "<sha256>", "Config"),
    # (".claude/hooks/PreToolUse/markdownlint-cli2.yaml", "<sha256>", "CLI2 config"),
    # (".claude/hooks/PreToolUse/_vendor/markdownlint/INTEGRITY.json", "<sha256>", "Manifest"),
]

# ── Lockfile policy ──
_CANONICAL_REGISTRY = "https://registry.npmjs.org/"
_INTEGRITY_RE = re.compile(r"^sha512-[A-Za-z0-9+/]+=*$")
_APPROVED_LOCKFILE_VERSION = "3"
_REJECTED_DEP_KEYS = ("link", "hasInstallScript")

# ── Config safety: execution-capable keys ──
_EXECUTION_KEYS = frozenset((
    "customRules", "markdownItPlugins", "extends",
    "outputFormatters", "globs",
))


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ── Artifact authentication ──

def _authenticate_pinned(candidate: Path) -> list[str]:
    """Authenticate every pinned artifact against its trust anchor."""
    errors: list[str] = []
    for rel, expected, label in _PINNED_ARTIFACTS:
        fpath = candidate / rel
        if not fpath.is_file():
            # File absent: it may not exist yet (vendor pins before vendor PR).
            # Only flag if the file IS present but mismatches.
            continue
        actual = _sha256_file(fpath)
        if actual != expected:
            errors.append(
                f"{label} ({rel}): SHA-256 mismatch "
                f"(expected {expected[:16]}..., got {actual[:16]}...)"
            )
    return errors


def _check_unpinned_executables(candidate: Path) -> list[str]:
    """Flag hook executables present in candidate but not pinned."""
    errors: list[str] = []
    pinned_rels = {rel for rel, _, _ in _PINNED_ARTIFACTS}
    hook_dirs = [
        candidate / ".claude" / "hooks" / "PreToolUse",
        candidate / "src" / "copilot-cli" / "hooks" / "PreToolUse",
    ]
    for hdir in hook_dirs:
        if not hdir.is_dir():
            continue
        for f in sorted(hdir.iterdir()):
            if not f.is_file():
                continue
            if f.suffix not in (".py", ".sh", ".mjs", ".js"):
                continue
            if f.name.startswith(".") or f.name == "CLAUDE.md":
                continue
            rel = str(PurePosixPath(f.relative_to(candidate)))
            if rel not in pinned_rels:
                errors.append(
                    f"Unpinned executable: {rel} "
                    f"(sha256: {_sha256_file(f)[:16]}...)"
                )
    return errors


# ── Mirror parity ──

_MIRROR_PAIRS: list[tuple[str, str]] = [
    (
        ".claude/hooks/PreToolUse/_bootstrap.py",
        "src/copilot-cli/hooks/PreToolUse/_bootstrap.py",
    ),
    # push_guard_base.py: generated mirror strips noqa comments, so byte
    # parity does not hold. Both are independently pinned above.
]


def _check_mirror_parity(candidate: Path) -> list[str]:
    errors: list[str] = []
    for canon_rel, mirror_rel in _MIRROR_PAIRS:
        canon = candidate / canon_rel
        mirror = candidate / mirror_rel
        if canon.is_file() and mirror.is_file():
            if canon.read_bytes() != mirror.read_bytes():
                errors.append(f"Parity mismatch: {canon_rel} vs {mirror_rel}")
    return errors


# ── Lockfile validation ──

def _validate_package_entry(name: str, meta: dict[str, object]) -> list[str]:
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
    if not lockfile.is_file():
        return []  # No vendor tree yet: not an error
    try:
        data = json.loads(lockfile.read_bytes())
    except (json.JSONDecodeError, OSError) as exc:
        return [f"Cannot parse lockfile: {exc}"]
    errors: list[str] = []
    version = str(data.get("lockfileVersion", ""))
    if version != _APPROVED_LOCKFILE_VERSION:
        errors.append(f"lockfileVersion {version!r} != {_APPROVED_LOCKFILE_VERSION!r}")
    packages = data.get("packages", {})
    non_root = {k: v for k, v in packages.items() if k}
    if not non_root and lockfile.is_file():
        errors.append("lockfile has no non-root packages")
    for name, meta in non_root.items():
        errors.extend(_validate_package_entry(name, meta))
        if len(errors) >= 10:
            errors.append("(truncated)")
            break
    return errors


# ── Config safety ──

def _validate_config_safe(config_path: Path) -> list[str]:
    if not config_path.is_file():
        return []  # Config not present yet
    raw = config_path.read_bytes()
    try:
        import yaml
        parsed = yaml.safe_load(raw)
    except ImportError:
        parsed = None
    if parsed is not None:
        return _find_exec_keys(parsed)
    # Regex fallback
    text = raw.decode("utf-8", errors="replace")
    errors: list[str] = []
    for key in _EXECUTION_KEYS:
        pat = rf"""(?:^|\{{|,)\s*['"]?{re.escape(key)}['"]?\s*:"""
        if re.search(pat, text, re.MULTILINE):
            errors.append(f"Execution-capable key '{key}' in config")
    return errors


def _find_exec_keys(obj: object, path: str = "") -> list[str]:
    hits: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            cur = f"{path}.{k}" if path else str(k)
            if str(k) in _EXECUTION_KEYS:
                hits.append(f"Execution-capable key '{k}' at {cur}")
            hits.extend(_find_exec_keys(v, cur))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            hits.extend(_find_exec_keys(item, f"{path}[{i}]"))
    return hits


# ── Symlink containment ──

def _check_symlink_containment(vendor_dir: Path) -> list[str]:
    if not vendor_dir.is_dir():
        return []
    errors: list[str] = []
    vr = vendor_dir.resolve()
    for item in vendor_dir.rglob("*"):
        if item.is_symlink():
            target = (item.parent / os.readlink(item)).resolve()
            if not str(target).startswith(str(vr) + os.sep) and target != vr:
                errors.append(
                    f"Symlink escapes vendor: {item.relative_to(vendor_dir)}"
                )
                if len(errors) >= 5:
                    break
    return errors


# ── .npmrc rejection ──

def _reject_npmrc(candidate: Path, vendor_dir: Path) -> list[str]:
    if not vendor_dir.is_dir():
        return []
    check = vendor_dir
    errors: list[str] = []
    while True:
        if (check / ".npmrc").exists():
            errors.append(f".npmrc at {check.relative_to(candidate)}")
        if check == candidate or check == check.parent:
            break
        check = check.parent
    return errors


# ── Vendor reconstruction ──

def _reconstruct_and_compare(vendor_dir: Path) -> list[str]:
    if not (vendor_dir / "package-lock.json").is_file():
        return []  # No vendor tree
    import shutil
    import tempfile
    nm = vendor_dir / "node_modules"
    if not nm.is_dir():
        return ["vendor has lockfile but no node_modules"]
    errors: list[str] = []
    with tempfile.TemporaryDirectory(prefix="vendor-prov-") as td:
        copy = Path(td) / "committed"
        shutil.copytree(vendor_dir, copy, symlinks=True)
        try:
            proc = subprocess.run(
                ["npm", "ci", "--ignore-scripts", "--audit=false"],
                cwd=vendor_dir, capture_output=True,
                encoding="utf-8", errors="replace",
                timeout=120,
                env={**os.environ, "npm_config_fund": "false",
                     "npm_config_registry": _CANONICAL_REGISTRY},
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            return [f"npm ci failed: {exc}"]
        if proc.returncode != 0:
            return [f"npm ci exit {proc.returncode}: {proc.stderr[:200]}"]
        errors.extend(_compare_nm(copy / "node_modules", vendor_dir / "node_modules"))
    return errors


def _collect_tree(root: Path) -> tuple[dict[str, str], dict[str, str], set[str]]:
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


def _compare_nm(committed: Path, reconstructed: Path) -> list[str]:
    errors: list[str] = []
    if not committed.is_dir() or not reconstructed.is_dir():
        return ["node_modules missing for comparison"]
    cf, cs, ce = _collect_tree(committed)
    rf, rs, re_ = _collect_tree(reconstructed)
    extra = set(cf) - set(rf)
    if extra:
        errors.append(f"Extra committed: {sorted(extra)[:3]}")
    miss = set(rf) - set(cf)
    if miss:
        errors.append(f"Missing committed: {sorted(miss)[:3]}")
    for k in sorted(set(cf) & set(rf)):
        if cf[k] != rf[k]:
            errors.append(f"Content mismatch: {k}")
            if len(errors) >= 5:
                break
    if cs != rs:
        errors.append("Symlink set/target differs")
    if ce ^ re_:
        errors.append(f"Executable mode differs: {sorted(ce ^ re_)[:3]}")
    return errors


# ── Main ──

def _run_phase(label: str, errors: list[str]) -> None:
    print(f"\n=== {label} ===")
    for e in errors:
        print(f"  FAIL: {e}")
    if not errors:
        print("  PASS")


def main() -> int:
    parser = argparse.ArgumentParser(description="Trusted vendor provenance gate")
    parser.add_argument("--candidate-root", required=True, type=Path)
    args = parser.parse_args()
    root = args.candidate_root.resolve()
    if not root.is_dir():
        print(f"ERROR: candidate root not found: {root}", file=sys.stderr)
        return 2

    all_errors: list[str] = []
    vendor = root / ".claude" / "hooks" / "PreToolUse" / "_vendor" / "markdownlint"
    config = root / ".claude" / "hooks" / "PreToolUse" / "markdownlint-safe-config.yaml"

    # 1. Authenticate pinned artifacts
    errs = _authenticate_pinned(root)
    _run_phase("Trust-Anchor Authentication", errs)
    all_errors.extend(errs)

    # 2. Flag unpinned executables
    errs = _check_unpinned_executables(root)
    _run_phase("Unpinned Executable Scan", errs)
    all_errors.extend(errs)

    # 3. Mirror parity
    errs = _check_mirror_parity(root)
    _run_phase("Mirror Parity", errs)
    all_errors.extend(errs)

    # 4. Lockfile policy
    errs = _validate_lockfile(vendor / "package-lock.json")
    _run_phase("Lockfile Policy", errs)
    all_errors.extend(errs)

    # 5. Config safety
    errs = _validate_config_safe(config)
    _run_phase("Config Safety", errs)
    all_errors.extend(errs)

    # 6. Symlink containment
    errs = _check_symlink_containment(vendor)
    _run_phase("Symlink Containment", errs)
    all_errors.extend(errs)

    # 7. .npmrc rejection
    errs = _reject_npmrc(root, vendor)
    _run_phase(".npmrc Rejection", errs)
    all_errors.extend(errs)

    # 8. Vendor reconstruction
    errs = _reconstruct_and_compare(vendor)
    _run_phase("Lockfile Reconstruction", errs)
    all_errors.extend(errs)

    if all_errors:
        print(f"\nBLOCKED: {len(all_errors)} error(s)")
        return 1
    print("\nPASS: All vendor provenance checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
