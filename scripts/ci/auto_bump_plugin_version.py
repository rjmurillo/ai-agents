#!/usr/bin/env python3
"""Auto-bump parity plugin manifest versions (ADR-091 post-merge bot).

This script is invoked by ``.github/workflows/post-merge-version-bump.yml``
immediately after a push lands on ``main``.  It increments the patch version in
both parity manifests (``project-toolkit`` plugin for Claude and Copilot CLI)
when the push included non-manifest plugin source changes.

Behavior
--------

1. Inspect the changed files between ``PUSH_BEFORE_SHA`` and ``PUSH_AFTER_SHA``
   (passed as environment variables by the workflow).
2. If no non-manifest plugin source files changed, exit 0 with "nothing to do".
   This prevents the bot from bumping on its own bump commit.
3. Parse the current SemVer patch from one of the parity manifests, increment
   it, and write the new value to both manifests.
4. Also run the taste and ruff count ratchets with ``--update`` so improved
   baselines are recorded atomically in the same bot commit.

The script does NOT run ``git commit`` or ``git push``; those are the calling
workflow's responsibility (the workflow needs the resulting exit code and the
list of mutated files).

CLI
---

::

    python3 scripts/ci/auto_bump_plugin_version.py
    python3 scripts/ci/auto_bump_plugin_version.py --dry-run

EXIT CODES (per ADR-035)
------------------------

0 - wrote new versions (or nothing to do on a dry run)
1 - plugin source changed but bump failed (version parse error, write error)
2 - configuration error (missing env, missing manifest, git error)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# The two parity manifests that this bot manages (ADR-091).
_PARITY_MANIFESTS: tuple[str, ...] = (
    ".claude/.claude-plugin/plugin.json",
    "src/copilot-cli/.claude-plugin/plugin.json",
)

# Source dirs owned by the parity manifests (excluding the manifests themselves).
_PARITY_SOURCE_DIRS: tuple[str, ...] = (".claude/", "src/copilot-cli/")


def _git_diff_files(before: str, after: str, repo_root: Path) -> list[str] | None:
    """Return files changed between ``before`` and ``after`` SHAs.

    Returns ``None`` on git failure.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), "diff", "--name-only", f"{before}..{after}"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"error: git diff failed: {exc}", file=sys.stderr)
        return None
    if proc.returncode != 0:
        print(
            f"error: git diff {before}..{after} exit {proc.returncode}: {proc.stderr.strip()}",
            file=sys.stderr,
        )
        return None
    return [ln for ln in proc.stdout.splitlines() if ln.strip()]


def _has_non_manifest_plugin_changes(changed: list[str]) -> bool:
    """True when ``changed`` includes at least one non-manifest parity source file."""
    manifests = set(_PARITY_MANIFESTS)
    for path in changed:
        for src_dir in _PARITY_SOURCE_DIRS:
            if path.startswith(src_dir) and path not in manifests:
                return True
    return False


def _read_version(manifest_path: Path) -> str | None:
    """Return the ``version`` string from a plugin.json, or ``None``."""
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    v = data.get("version")
    return v if isinstance(v, str) else None


def _bump_patch(version: str) -> str | None:
    """Return version with patch incremented, or None if not valid MAJOR.MINOR.PATCH.

    Accepts an optional pre-release suffix; strips it and bumps patch.
    ``0.6.5446`` -> ``0.6.5447``.
    """
    core = version.split("-")[0].split("+")[0]
    parts = core.split(".")
    if len(parts) != 3:
        return None
    try:
        major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])
    except ValueError:
        return None
    return f"{major}.{minor}.{patch + 1}"


def _write_version(manifest_path: Path, new_version: str) -> bool:
    """Write ``new_version`` into the manifest's ``version`` field.

    Returns True on success, False on error.
    """
    try:
        text = manifest_path.read_text(encoding="utf-8")
        data = json.loads(text)
    except (OSError, ValueError, TypeError) as exc:
        print(f"error: could not read {manifest_path}: {exc}", file=sys.stderr)
        return False
    if not isinstance(data, dict):
        print(f"error: {manifest_path} is not a JSON object", file=sys.stderr)
        return False
    data["version"] = new_version
    try:
        manifest_path.write_text(
            json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    except OSError as exc:
        print(f"error: could not write {manifest_path}: {exc}", file=sys.stderr)
        return False
    return True


def _run_ratchet_update(script: Path, repo_root: Path) -> None:
    """Run a count ratchet with --update; log but do not fail on errors."""
    try:
        proc = subprocess.run(
            [sys.executable, str(script), "--update"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"warning: ratchet {script.name} could not run: {exc}", file=sys.stderr)
        return
    if proc.stdout:
        print(proc.stdout, end="")
    if proc.returncode not in (0, 1):
        # Exit 1 = regression (count went up); log but don't stop the bump.
        if proc.stderr:
            print(proc.stderr, end="", file=sys.stderr)


def _should_bump(before_sha: str, after_sha: str, repo_root: Path) -> tuple[bool, int]:
    """Return (do_bump, exit_code).  exit_code is non-zero if we must stop early."""
    if not before_sha or before_sha == "0" * 40:
        print("PUSH_BEFORE_SHA is empty or zero SHA (first push); bumping unconditionally.")
        return True, 0
    changed = _git_diff_files(before_sha, after_sha, repo_root)
    if changed is None:
        return False, 2
    if not _has_non_manifest_plugin_changes(changed):
        print("No non-manifest parity source changes; nothing to bump.")
        return False, 0
    return True, 0


def _compute_new_version(repo_root: Path) -> tuple[str | None, int]:
    """Parse the current version and compute the next patch level.

    Returns (new_version, exit_code).  exit_code is non-zero on failure.
    """
    primary = repo_root / _PARITY_MANIFESTS[0]
    current = _read_version(primary)
    if current is None:
        print(f"error: cannot read version from {primary}", file=sys.stderr)
        return None, 1
    new_version = _bump_patch(current)
    if new_version is None:
        print(f"error: cannot parse version {current!r} from {primary}", file=sys.stderr)
        return None, 1
    print(f"Bumping parity plugin version: {current} -> {new_version}")
    return new_version, 0


def _write_manifests(repo_root: Path, new_version: str, dry_run: bool) -> int:
    """Write new_version into every parity manifest.  Returns exit code."""
    for manifest_rel in _PARITY_MANIFESTS:
        if dry_run:
            print(f"  [dry-run] would write {new_version} to {manifest_rel}")
            continue
        manifest_path = repo_root / manifest_rel
        if not _write_version(manifest_path, new_version):
            return 1
        print(f"  wrote {new_version} to {manifest_rel}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Auto-bump parity plugin manifest versions after a merge to main."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute and print the new version without writing any files.",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Override repo root (default: derived from script path).",
    )
    args = parser.parse_args(argv)
    repo_root = (args.repo_root or _REPO_ROOT).resolve()

    before_sha = os.environ.get("PUSH_BEFORE_SHA", "")
    after_sha = os.environ.get("PUSH_AFTER_SHA", "HEAD")

    do_bump, rc = _should_bump(before_sha, after_sha, repo_root)
    if rc != 0 or not do_bump:
        return rc

    new_version, rc = _compute_new_version(repo_root)
    if rc != 0 or new_version is None:
        return rc

    rc = _write_manifests(repo_root, new_version, args.dry_run)
    if rc != 0:
        return rc

    if not args.dry_run:
        for ratchet_name in ("taste_count_ratchet.py", "ruff_count_ratchet.py"):
            ratchet = repo_root / "scripts" / "ci" / ratchet_name
            if ratchet.is_file():
                _run_ratchet_update(ratchet, repo_root)

    return 0


if __name__ == "__main__":
    sys.exit(main())
