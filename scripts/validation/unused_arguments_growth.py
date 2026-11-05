"""Baseline-growth check for ``check_unused_arguments.py``.

The baseline may only shrink. This module reads it as committed at the merge
base and reports every line the branch added, following git renames.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from scripts.validation.unused_arguments_git import (
    KEY_SEPARATOR,
    Deadline,
    ExternalToolError,
    GateConfigError,
    run_git,
)

DEFAULT_BASE_REFS = ("refs/remotes/origin/HEAD", "origin/main", "main")


@dataclass(frozen=True)
class Growth:
    """Baseline lines the branch has that the merge base lacks."""

    added: list[str]
    note: str


def parse_baseline(text: str) -> list[str]:
    """Return baseline keys, skipping blank lines and ``#`` comments."""
    keys: list[str] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        path, sep, message = line.partition(KEY_SEPARATOR)
        if not sep or not path or not message:
            raise GateConfigError(f"baseline line {lineno} is not '<path>: <message>': {raw!r}")
        keys.append(line)
    return keys


def default_base_ref(repo_root: Path, deadline: Deadline) -> str | None:
    """Return the first ref in ``DEFAULT_BASE_REFS`` that resolves, or None."""
    for ref in DEFAULT_BASE_REFS:
        probe = run_git(repo_root, ["rev-parse", "--verify", "--quiet", ref], deadline)
        if probe.returncode == 0:
            return ref
    return None


def fork_point(repo_root: Path, base_ref: str, deadline: Deadline) -> str:
    """Return the commit where HEAD left ``base_ref``, or raise exit 3."""
    proc = run_git(repo_root, ["merge-base", "--", base_ref, "HEAD"], deadline)
    fork = proc.stdout.strip()
    if proc.returncode != 0 or not fork:
        raise ExternalToolError(
            f"unused-argument gate: FORK POINT UNREADABLE. git merge-base {base_ref} HEAD "
            f"failed: {proc.stderr.strip() or 'no output'}. Fetch the base branch (and the "
            f"full history when the clone is shallow) and re-run."
        )
    return fork


def _renames_since(repo_root: Path, fork: str, deadline: Deadline) -> dict[str, str]:
    """Map old path to new path for files git reports as renamed since ``fork``."""
    proc = run_git(
        repo_root, ["diff", "-M", "--name-status", "-z", "--diff-filter=R", fork, "--"], deadline
    )
    if proc.returncode != 0:
        raise ExternalToolError(
            f"unused-argument gate: git diff against {fork[:12]} failed: "
            f"{proc.stderr.strip() or 'no output'}"
        )
    fields = proc.stdout.split("\0")
    renames: dict[str, str] = {}
    for index in range(0, len(fields) - 2, 3):
        if fields[index].startswith("R"):
            renames[fields[index + 1]] = fields[index + 2]
    return renames


def _baseline_at(repo_root: Path, fork: str, relpath: str, deadline: Deadline) -> str | None:
    """Return the baseline text committed at ``fork``, or None when it has none."""
    listing = run_git(repo_root, ["ls-tree", "--name-only", fork, "--", relpath], deadline)
    if listing.returncode != 0:
        raise ExternalToolError(
            f"unused-argument gate: git ls-tree {fork[:12]} failed: "
            f"{listing.stderr.strip() or 'no output'}"
        )
    if not listing.stdout.strip():
        return None
    shown = run_git(repo_root, ["show", f"{fork}:{relpath}"], deadline)
    if shown.returncode != 0:
        raise ExternalToolError(
            f"unused-argument gate: git show {fork[:12]}:{relpath} failed: "
            f"{shown.stderr.strip() or 'no output'}"
        )
    return shown.stdout


def _follow_renames(keys: Iterable[str], renames: dict[str, str]) -> list[str]:
    moved: list[str] = []
    for key in keys:
        path, sep, message = key.partition(KEY_SEPARATOR)
        moved.append(f"{renames.get(path, path)}{sep}{message}")
    return moved


def baseline_growth(
    repo_root: Path,
    baseline_path: Path,
    baseline: Sequence[str],
    base_ref: str | None,
    deadline: Deadline,
) -> Growth:
    """Return the baseline lines the branch added since the merge base."""
    if base_ref is None:
        base_ref = default_base_ref(repo_root, deadline)
        if base_ref is None:
            return Growth([], "baseline growth NOT CHECKED: no base ref resolved")
    try:
        relpath = baseline_path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError as exc:
        raise GateConfigError(f"baseline {baseline_path} is outside {repo_root}") from exc
    fork = fork_point(repo_root, base_ref, deadline)
    text = _baseline_at(repo_root, fork, relpath, deadline)
    if text is None:
        return Growth([], f"baseline growth not checked: {base_ref} has no baseline yet")
    base_keys = _follow_renames(parse_baseline(text), _renames_since(repo_root, fork, deadline))
    added = sorted((Counter(baseline) - Counter(base_keys)).elements())
    return Growth(added, f"baseline growth vs merge base {fork[:12]}: {len(added)} line(s)")
