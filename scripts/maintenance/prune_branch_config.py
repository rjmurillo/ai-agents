#!/usr/bin/env python3
"""Prune stale ``[branch "<name>"]`` sections from the shared ``.git/config``.

Issue #5360 follows issue #4698. Every ``git branch --track``, ``git switch``
with upstream setup, and IDE merge-base write adds a ``[branch "<name>"]``
section to ``.git/config``. Git never removes it when the branch is deleted, so
the file grows without bound (measured: 44648 bytes with 416 sections in the
original incident, 55496 bytes with 1033 ``branch.*`` keys against 781 local
branches later).

A section is stale when ``refs/heads/<name>`` does not exist. The source of
truth is ``git for-each-ref refs/heads``, which covers loose refs, packed refs,
and reftable. Two sets of branches are always kept even without a ref:

- the branch each worktree's ``HEAD`` points at, so an unborn branch (fresh
  ``git init`` or ``git switch --orphan``) keeps its upstream settings;
- sections with no subsection (``branch.autoSetupMerge`` and similar), which
  are global settings and not per-branch data.

The default run reports only. ``--apply`` backs up the config file beside
itself, removes each stale section with ``git config --remove-section``, and
verifies git still parses the result. A prune lock file keeps two ``--apply``
runs apart, and the stale set is computed again under that lock so a branch
created after the first look is never pruned. On any failure, including an
interrupt, only the sections this run removed are written back from the backup.
A concurrent ``git config`` write to another section survives the rollback.
When the live config no longer parses, the whole backup is copied back instead.

``--fail-on-stale`` makes a run that leaves stale sections exit 1, so a
report-only caller such as the pre-push ``branch-config-prune-report`` job can
tell findings from a clean config. Without it a dry run always exits 0.

EXIT CODES (ADR-035):
  0 - success (including nothing to prune and a dry-run report)
  1 - stale sections remain and --fail-on-stale was passed
  2 - configuration error (not a git repository)
  3 - external error (git failed or timed out, or another prune holds the lock;
      --apply restores the sections it removed)
"""

from __future__ import annotations

import argparse
import contextlib
import os
import shutil
import subprocess
import sys
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_CONFIG = 2
EXIT_EXTERNAL = 3

_GIT_TIMEOUT_SECONDS = 30
_BRANCH_PREFIX = "branch."
_HEADS_PREFIX = "refs/heads/"
_GIT_ENV_KEYS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE")


class GitError(RuntimeError):
    """A git command failed, timed out, or could not start."""


class NotARepositoryError(GitError):
    """The target path is not inside a git repository."""


@dataclass(frozen=True, slots=True)
class PruneResult:
    """Outcome of one prune pass."""

    config_path: Path
    configured: tuple[str, ...]
    stale: tuple[str, ...]
    removed: int = 0
    backup_path: Path | None = None


def _clean_env() -> dict[str, str]:
    env = os.environ.copy()
    for key in _GIT_ENV_KEYS:
        env.pop(key, None)
    return env


def run_git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run git in ``repo`` with a clean environment and a timeout."""
    try:
        return subprocess.run(
            ["git", *args],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            cwd=repo,
            env=_clean_env(),
            timeout=_GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GitError(f"git {' '.join(args)} failed: {exc}") from exc


def _git_ok(repo: Path, *args: str) -> str:
    result = run_git(repo, *args)
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip()
        raise GitError(f"git {' '.join(args)} failed: {message}")
    return result.stdout


def resolve_config_path(repo: Path) -> Path:
    """Return the shared config file path for a repository or linked worktree."""
    if not repo.is_dir():
        raise NotARepositoryError(f"{repo} is not a directory")
    probe = run_git(repo, "rev-parse", "--git-common-dir")
    if probe.returncode != 0:
        raise NotARepositoryError(f"{repo} is not inside a git repository")
    common_dir = Path(probe.stdout.strip())
    if not common_dir.is_absolute():
        common_dir = repo / common_dir
    return common_dir.resolve() / "config"


def branch_name_from_key(key: str) -> str | None:
    """Extract the branch name from a ``branch.<name>.<variable>`` config key.

    Git lowercases the section and variable but keeps the subsection, so the
    name is everything between the first and last dot. Branch names may hold
    dots and slashes. A key with one dot after ``branch`` has no subsection and
    returns None.
    """
    if not key.lower().startswith(_BRANCH_PREFIX):
        return None
    remainder = key[len(_BRANCH_PREFIX) :]
    name, dot, variable = remainder.rpartition(".")
    if not dot or not name or not variable:
        return None
    return name


def list_configured_branches(repo: Path) -> tuple[str, ...]:
    """Return the sorted branch names that own a section in the local config."""
    result = run_git(repo, "config", "--local", "--name-only", "-z", "--get-regexp", r"^branch\.")
    if result.returncode == 1:
        return ()
    if result.returncode != 0:
        raise GitError(f"git config --get-regexp failed: {result.stderr.strip()}")
    names = {
        name
        for key in result.stdout.split("\0")
        if key and (name := branch_name_from_key(key)) is not None
    }
    return tuple(sorted(names))


def list_local_branches(repo: Path) -> frozenset[str]:
    """Return every branch name with a ref under ``refs/heads``."""
    output = _git_ok(repo, "for-each-ref", "--format=%(refname)", _HEADS_PREFIX)
    return frozenset(
        line[len(_HEADS_PREFIX) :] for line in output.splitlines() if line.startswith(_HEADS_PREFIX)
    )


def list_checked_out_branches(repo: Path) -> frozenset[str]:
    """Return branches that HEAD names in this checkout or any linked worktree.

    An unborn branch has no ref yet but its config is live.
    """
    output = _git_ok(repo, "worktree", "list", "--porcelain")
    heads = {
        line.split(" ", 1)[1][len(_HEADS_PREFIX) :]
        for line in output.splitlines()
        if line.startswith(f"branch {_HEADS_PREFIX}")
    }
    current = run_git(repo, "symbolic-ref", "--quiet", "HEAD")
    if current.returncode == 0 and current.stdout.startswith(_HEADS_PREFIX):
        heads.add(current.stdout.strip()[len(_HEADS_PREFIX) :])
    return frozenset(heads)


def find_stale_branches(
    configured: Iterable[str],
    local: frozenset[str],
    checked_out: frozenset[str],
) -> tuple[str, ...]:
    """Return configured branch names with no ref and no checkout."""
    return tuple(name for name in configured if name not in local and name not in checked_out)


def _backup_config(config_path: Path) -> Path:
    base = config_path.with_name(f"{config_path.name}.before-prune")
    backup = base
    suffix = 0
    while backup.exists():
        suffix += 1
        if suffix >= 1000:
            raise GitError("could not choose a config backup path")
        backup = base.with_name(f"{base.name}.{suffix}")
    shutil.copy2(config_path, backup)
    return backup


def _verify_config(repo: Path) -> None:
    _git_ok(repo, "config", "--local", "--list")
    _git_ok(repo, "for-each-ref", "--format=%(refname)", _HEADS_PREFIX)


def _remove_sections(repo: Path, names: Iterable[str], touched: list[str]) -> int:
    """Remove each named section and record it in ``touched`` before the call.

    The name is recorded first so an interrupt during the git call still
    lands the in-flight section on the rollback list.
    """
    removed = 0
    for name in names:
        touched.append(name)
        _git_ok(repo, "config", "--local", "--remove-section", f"{_BRANCH_PREFIX}{name}")
        removed += 1
    return removed


def _parse_config_entries(listing: str) -> list[tuple[str, str | None]]:
    """Split ``git config --list -z`` output into ``(key, value)`` pairs.

    Each entry is ``key NL value NUL``. A key with no value has no NL and
    yields ``None``. That is a boolean true in git, which an empty string is not.
    """
    entries: list[tuple[str, str | None]] = []
    for chunk in listing.split("\0"):
        if not chunk:
            continue
        key, sep, value = chunk.partition("\n")
        entries.append((key, value if sep else None))
    return entries


def _restore_sections(repo: Path, backup: Path, names: Iterable[str]) -> None:
    """Write the named sections from ``backup`` back into the live config.

    Only the sections this run touched are restored, so a concurrent writer's
    change to another section is not overwritten the way a whole-file copy
    would. A section that is still present (its removal never happened) is
    skipped, which keeps the restore from duplicating values. A valueless key
    is restored as ``true``, the boolean it means, never as an empty string.
    """
    wanted = set(names)
    if not wanted:
        return
    present = set(list_configured_branches(repo))
    listing = _git_ok(repo, "config", "--file", str(backup), "--list", "-z")
    for key, value in _parse_config_entries(listing):
        name = branch_name_from_key(key)
        if name in wanted and name not in present:
            _git_ok(repo, "config", "--local", "--add", key, "true" if value is None else value)


def _rollback(repo: Path, config_path: Path, backup: Path, touched: list[str]) -> None:
    """Undo a failed prune, preferring a section-only restore.

    When the live config does not parse, or the section restore raises, no
    concurrent write can be kept in a file git cannot read, so the whole
    backup is copied back. A copy that fails too names the backup.
    """
    try:
        _restore_sections(repo, backup, touched)
        return
    except GitError as section_error:
        failure = section_error
    try:
        shutil.copy2(backup, config_path)
    except OSError as exc:
        raise GitError(
            f"rollback failed; the original config is saved at {backup}: {failure}; {exc}"
        ) from exc


@contextlib.contextmanager
def _prune_lock(config_path: Path) -> Iterator[None]:
    """Hold an exclusive lock file so two ``--apply`` runs cannot interleave.

    ``O_EXCL`` creation is atomic on local filesystems and works on Windows.
    The file is separate from git's own ``config.lock`` because the prune
    calls ``git config``, which needs that one itself.
    """
    lock_path = config_path.with_name(f"{config_path.name}.prune-lock")
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise GitError(
            f"another prune holds {lock_path}; remove the file if no prune is running"
        ) from exc
    except OSError as exc:
        raise GitError(f"could not create prune lock {lock_path}: {exc}") from exc
    try:
        os.write(fd, f"{os.getpid()}\n".encode())
        os.close(fd)
        yield
    finally:
        with contextlib.suppress(OSError):
            lock_path.unlink()


def _find_stale(repo: Path) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return ``(configured, stale)`` from the live refs and worktrees."""
    configured = list_configured_branches(repo)
    stale = find_stale_branches(
        configured, list_local_branches(repo), list_checked_out_branches(repo)
    )
    return configured, stale


def prune_branch_config(repo: Path, apply: bool = False) -> PruneResult:
    """Find stale branch sections and remove them when ``apply`` is true."""
    config_path = resolve_config_path(repo)
    if not apply:
        configured, stale = _find_stale(repo)
        return PruneResult(config_path=config_path, configured=configured, stale=stale)

    with _prune_lock(config_path):
        # Listed again under the lock: a branch created since any earlier look
        # must not lose its section.
        configured, stale = _find_stale(repo)
        if not stale:
            return PruneResult(config_path=config_path, configured=configured, stale=stale)
        backup = _backup_config(config_path)
        touched: list[str] = []
        completed = False
        try:
            removed = _remove_sections(repo, stale, touched)
            _verify_config(repo)
            completed = True
        finally:
            # A finally block, not except GitError: an interrupt or any other
            # error must not leave a partly pruned config.
            if not completed:
                _rollback(repo, config_path, backup, touched)
    return PruneResult(config_path, configured, stale, removed=removed, backup_path=backup)


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument(
        "--path",
        type=Path,
        default=Path.cwd(),
        help="Repository or worktree path. Defaults to the current directory.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Remove the stale sections. Without it the run only reports.",
    )
    parser.add_argument(
        "--fail-on-stale",
        action="store_true",
        help="Exit 1 when stale sections remain after the run, for report-only callers.",
    )
    return parser


def format_result(result: PruneResult, apply: bool) -> str:
    """Render a result as plain text."""
    lines = [
        f"config: {result.config_path}",
        f"branch sections: {len(result.configured)}, stale: {len(result.stale)}",
    ]
    lines.extend(f"  stale: {name}" for name in result.stale)
    if result.removed:
        lines.append(f"removed {result.removed} section(s); backup: {result.backup_path}")
    elif result.stale and not apply:
        lines.append("dry run: pass --apply to remove them")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Run the prune and map failures to exit codes."""
    args = build_parser().parse_args(argv)
    try:
        result = prune_branch_config(args.path, apply=args.apply)
    except NotARepositoryError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    except GitError as exc:
        print(f"ERROR: branch config prune failed: {exc}", file=sys.stderr)
        return EXIT_EXTERNAL
    print(format_result(result, args.apply))
    if args.fail_on_stale and result.stale and not result.removed:
        return EXIT_FINDINGS
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
