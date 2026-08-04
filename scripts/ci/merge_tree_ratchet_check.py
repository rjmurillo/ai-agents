#!/usr/bin/env python3
"""Merge-tree ratchet: evaluate all three count ratchets on the merged result.

Issue #4398. Closes the stale-branch hole: a PR branch can pass every ratchet
individually, yet the merged result still breaches the ceiling, because the
branch is measured against an old main that held a looser baseline.

PR #4272 is the canonical example: it grew a file past the taste-lint 500-line
ceiling and merged green because strict_required_status_checks_policy is false
on this repository's ruleset. A stale-base merge can pass while the merged
result fails.

DOES NOT CLOSE the concurrent-admission hole (issue #4345, reserve-band
mechanism). Three PRs each passing against the same current main all show a
clean merge-tree individually; the union breaches only when all three land.
These two fixes are complementary. Say so in any PR that ships this gate.

Mechanism:
    git merge-tree --write-tree <base> <head>
    git archive <tree-oid>, extract with Python tarfile into <scratch>
    git init <scratch>, git -C <scratch> add -A, git -C <scratch> commit
    run current_count() from each ratchet against <scratch>
    compare against baselines at <base>

Timing (measured on this repo, 7925 tracked files):
    merge-tree:      0.017 s
    git archive+tar: 0.63 s
    three ratchets:  sub-second each
    total:           ~1-2 s vs 13.5 min p50 CI critical path

Conflict policy: when the merge conflicts, the PR cannot land anyway, so
blocking here would duplicate the mergeability check. Skip with a clear
message; let the merge-conflict gate handle it.

Scratch cleanup: always, on every exit path including exceptions.

Exit codes (AGENTS.md contract):
    0 - ok (all counts <= baselines)
    1 - regression (at least one count > baseline)
    2 - config error (baseline missing, bad args)
    3 - external error (git, ruff, or taste-lints could not run)
"""

from __future__ import annotations

import argparse
import io
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.ci import ruff_count_ratchet as _ruff
from scripts.ci import taste_count_ratchet as _taste
from scripts.ci import type_ignore_count_ratchet as _type_ignore

EXIT_OK = 0
EXIT_REGRESSION = 1
EXIT_CONFIG = 2
EXIT_EXTERNAL = 3


def _git(cwd: Path, *argv: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(cwd), *argv],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def _merge_tree_oid(repo_root: Path, base_ref: str) -> tuple[str | None, bool]:
    """Return (tree-oid, conflicts). oid is None on git failure."""
    proc = _git(repo_root, "merge-tree", "--write-tree", base_ref, "HEAD")
    if proc.returncode == 0:
        oid = proc.stdout.strip().splitlines()[0] if proc.stdout.strip() else None
        return oid, False
    if proc.returncode == 1:
        # exit 1 means conflicts; stdout still has the partial tree oid on line 1
        lines = proc.stdout.strip().splitlines()
        oid = lines[0] if lines else None
        return oid, True
    sys.stderr.write(f"git merge-tree failed (rc {proc.returncode}):\n{proc.stderr}\n")
    if "unrelated histories" in proc.stderr:
        sys.stderr.write(
            "merge-tree-ratchet: no merge base was reachable. This is a shallow-fetch\n"
            "regression, not a ratchet breach: a `git fetch --depth=1` writes\n"
            ".git/shallow and cuts history traversal, so any branch behind the base\n"
            "aborts here. Fetch the base ref at full depth (issue #4518).\n"
        )
    return None, False


def _is_safe_archive_member(name: str) -> bool:
    """Return True when a git archive member stays inside the extract root."""
    path = PurePosixPath(name)
    return not path.is_absolute() and ".." not in path.parts


def _write_archive_member(
    archive: tarfile.TarFile,
    member: tarfile.TarInfo,
    dest: Path,
) -> bool:
    """Write one safe git archive member without tarfile.extract* helpers."""
    if not _is_safe_archive_member(member.name):
        sys.stderr.write(f"unsafe archive member rejected: {member.name}\n")
        return False

    target = dest / member.name
    if member.isdir():
        target.mkdir(parents=True, exist_ok=True)
        return True

    target.parent.mkdir(parents=True, exist_ok=True)
    if member.isreg():
        source = archive.extractfile(member)
        if source is None:
            sys.stderr.write(f"archive member unreadable: {member.name}\n")
            return False
        with source, target.open("wb") as output:
            shutil.copyfileobj(source, output)
        target.chmod(member.mode & 0o777)
        return True

    if member.issym():
        if not _is_safe_archive_member(member.linkname):
            sys.stderr.write(f"unsafe archive symlink rejected: {member.name}\n")
            return False
        target.symlink_to(member.linkname)
        return True

    sys.stderr.write(f"unsupported archive member type: {member.name}\n")
    return False


def _extract_tree(repo_root: Path, tree_oid: str, dest: Path) -> bool:
    """Extract git tree into dest. Returns True on success."""
    dest.mkdir(parents=True, exist_ok=True)
    archive_proc = subprocess.run(
        ["git", "-C", str(repo_root), "archive", tree_oid],
        capture_output=True,
        check=False,
    )
    if archive_proc.returncode != 0:
        sys.stderr.write(
            f"git archive failed (rc {archive_proc.returncode}):\n"
            f"{archive_proc.stderr.decode('utf-8', errors='replace')}\n"
        )
        return False
    try:
        with tarfile.open(fileobj=io.BytesIO(archive_proc.stdout), mode="r|") as archive:
            for member in archive:
                if not _write_archive_member(archive, member, dest):
                    return False
    except (tarfile.TarError, OSError) as exc:
        sys.stderr.write(
            "tarfile extraction failed:\n"
            f"{exc}\n"
        )
        return False
    return True


def _init_scratch_repo(scratch: Path) -> bool:
    """Init a minimal git repo in scratch so tracked_files() works.

    LEFTHOOK=0 and GIT_CONFIG_NOSYSTEM=1 prevent hooks from firing during the
    scratch commit. --no-verify skips any other hook system (e.g. husky).
    Without these guards, git commit triggers the repo's pre-commit lefthook
    suite, which fails because pyproject.toml in the scratch tree triggers a
    package build.
    """
    _env = {
        "HOME": str(Path.home()),
        "PATH": "/usr/bin:/bin:/usr/local/bin",
        "LEFTHOOK": "0",
        "GIT_CONFIG_NOSYSTEM": "1",
    }
    for cmd in (
        ["git", "init", "-q", "-b", "main", str(scratch)],
        ["git", "-C", str(scratch), "config", "user.email", "ci@example.com"],
        ["git", "-C", str(scratch), "config", "user.name", "ci"],
        ["git", "-C", str(scratch), "add", "-A"],
        ["git", "-C", str(scratch), "commit", "--no-verify", "-qm", "merge-tree snapshot"],
    ):
        proc = subprocess.run(cmd, capture_output=True, check=False, env=_env)
        if proc.returncode != 0:
            sys.stderr.write(
                f"git init step failed: {cmd}\n"
                f"{proc.stderr.decode('utf-8', errors='replace')}\n"
            )
            return False
    return True


def _read_baseline_at_ref(repo_root: Path, ref: str, rel_path: str) -> int | None:
    """Read an integer baseline from a git ref, or None on failure."""
    proc = _git(repo_root, "show", f"{ref}:{rel_path}")
    if proc.returncode != 0:
        return None
    try:
        return int(proc.stdout.strip())
    except ValueError:
        return None


def _check_one(
    label: str,
    count: int | None,
    baseline: int | None,
) -> tuple[int, str]:
    """Return (exit code, message)."""
    if count is None:
        return EXIT_EXTERNAL, f"{label}: EXTERNAL ERROR - counter returned None"
    if baseline is None:
        return EXIT_CONFIG, f"{label}: CONFIG ERROR - baseline at base ref unreadable"
    if count > baseline:
        return (
            EXIT_REGRESSION,
            f"{label}: REGRESSION. {count} > baseline {baseline} (+{count - baseline}).",
        )
    return EXIT_OK, f"{label}: OK. {count} <= {baseline}."


def _evaluate_merged_tree(repo_root: Path, base_ref: str) -> int:
    """Extract merged tree, run counters, compare. Returns an EXIT_* code."""
    tree_oid, conflicts = _merge_tree_oid(repo_root, base_ref)
    if tree_oid is None:
        sys.stderr.write("merge-tree-ratchet: git merge-tree did not produce a tree OID.\n")
        return EXIT_EXTERNAL
    if conflicts:
        print(
            f"merge-tree-ratchet: merge into {base_ref} has conflicts; "
            "skipping (the PR cannot merge until conflicts are resolved)."
        )
        return EXIT_OK

    _ci_rel = "scripts/ci"
    _baseline_map = {
        "ruff count ratchet": f"{_ci_rel}/ruff_count_baseline.txt",
        "taste count ratchet": f"{_ci_rel}/taste_count_baseline.txt",
        "type-ignore count ratchet": f"{_ci_rel}/type_ignore_count_baseline.txt",
    }

    scratch_root = Path(tempfile.mkdtemp(prefix="merge-tree-ratchet-"))
    try:
        if not _extract_tree(repo_root, tree_oid, scratch_root):
            return EXIT_EXTERNAL
        if not _init_scratch_repo(scratch_root):
            return EXIT_EXTERNAL

        baselines = {
            label: _read_baseline_at_ref(repo_root, base_ref, rel)
            for label, rel in _baseline_map.items()
        }
        counts = {
            "ruff count ratchet": _ruff.current_count(scratch_root),
            "taste count ratchet": _taste.current_count(scratch_root),
            "type-ignore count ratchet": _type_ignore.current_count(scratch_root),
        }
    finally:
        shutil.rmtree(scratch_root, ignore_errors=True)

    exit_code = EXIT_OK
    for label, count in counts.items():
        code, msg = _check_one(label, count, baselines[label])
        exit_code = max(exit_code, code)
        if code != EXIT_OK:
            print(f"merge-tree-ratchet: {msg}", file=sys.stderr)
        else:
            print(f"merge-tree-ratchet: {msg}")

    if exit_code != EXIT_OK:
        print(
            "\nmerge-tree-ratchet: BLOCKED. The merged result breaches a ratchet ceiling.\n"
            "This means your branch is measured against a stale main, or your changes\n"
            "genuinely exceed the baseline. Merge or rebase from origin/main and re-check.\n"
            "If the ceiling is still breached after rebasing, fix the violations.\n"
            "(See issue #4398 for context.)",
            file=sys.stderr,
        )
        return exit_code

    print(
        f"merge-tree-ratchet: OK. Merged tree passes all three ratchets "
        f"(base: {base_ref})."
    )
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate all three count ratchets on the result of merging HEAD into "
            "base-ref. Closes the stale-branch hole (issue #4398)."
        )
    )
    parser.add_argument(
        "--base-ref",
        default="origin/main",
        help="Git ref to merge HEAD into and read baselines from (default: origin/main).",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="Repository root (default: cwd).",
    )
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    return _evaluate_merged_tree(args.repo_root.resolve(), args.base_ref)


if __name__ == "__main__":
    sys.exit(main())
