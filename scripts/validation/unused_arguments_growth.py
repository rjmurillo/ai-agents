"""Baseline-growth check for ``check_unused_arguments.py``.

The baseline may only shrink. This module reads it as committed at the merge
base and reports every line the branch added, following git renames. Whether
the merge base already carries the gate is decided by the gate script's own
path, as ``introduced_at`` in ``scripts/ci/base_derived_ratchet.py`` does, so
moving the baseline file cannot read as the first run.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from scripts.ci.count_ratchet import is_shallow_repository
from scripts.validation.unused_arguments_git import (
    KEY_SEPARATOR,
    Deadline,
    ExternalToolError,
    GateConfigError,
    run_git,
)

DEFAULT_BASE_REFS = ("refs/remotes/origin/HEAD", "origin/main", "main")
GATE_SCRIPT = "scripts/validation/check_unused_arguments.py"


@dataclass(frozen=True)
class Growth:
    """Baseline lines the merge base lacks, or an ``error`` that fails the gate."""

    added: list[str]
    note: str
    error: str = ""


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
        cause = (
            "this is a shallow clone, so there is no common history: run "
            "`git fetch --unshallow` and re-run"
            if is_shallow_repository(repo_root)
            else f"{base_ref} is not fetched, is not a valid ref, or shares no history with "
            f"this checkout: fetch the base branch and re-run"
        )
        raise ExternalToolError(
            f"unused-argument gate: FORK POINT UNREADABLE. git merge-base {base_ref} HEAD "
            f"failed ({proc.stderr.strip() or 'no output'}). Probable cause: {cause}."
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


def _present_at(repo_root: Path, fork: str, relpath: str, deadline: Deadline) -> bool:
    """Return True when ``fork`` records ``relpath``; raise exit 3 when git cannot say."""
    listing = run_git(repo_root, ["ls-tree", "--name-only", fork, "--", relpath], deadline)
    if listing.returncode != 0:
        raise ExternalToolError(
            f"unused-argument gate: git ls-tree {fork[:12]} failed: "
            f"{listing.stderr.strip() or 'no output'}"
        )
    return bool(listing.stdout.strip())


def _show_at(repo_root: Path, fork: str, relpath: str, deadline: Deadline) -> str:
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
    gate_script: str = GATE_SCRIPT,
) -> Growth:
    """Return the baseline lines the branch added since the merge base.

    Raises ``GateConfigError`` (exit 2) when no base ref resolves: a run that
    skipped the comparison would read as a pass.
    """
    if base_ref is None:
        base_ref = default_base_ref(repo_root, deadline)
        if base_ref is None:
            raise GateConfigError(
                f"no base ref resolved (tried {', '.join(DEFAULT_BASE_REFS)}), so the baseline "
                f"growth check cannot run. Fetch the base branch or pass --base-ref."
            )
    try:
        relpath = baseline_path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError as exc:
        raise GateConfigError(f"baseline {baseline_path} is outside {repo_root}") from exc
    fork = fork_point(repo_root, base_ref, deadline)
    if not _present_at(repo_root, fork, gate_script, deadline):
        return Growth(
            [],
            f"baseline growth not checked: {base_ref} does not carry {gate_script} yet "
            f"(this change introduces the gate)",
        )
    if not _present_at(repo_root, fork, relpath, deadline):
        return Growth(
            [],
            "baseline growth NOT CHECKED",
            error=(
                f"BASELINE MOVED OR REMOVED. The merge base {fork[:12]} carries {gate_script} "
                f"and has no {relpath}, so there is no ceiling to hold this branch to. Restore "
                f"the baseline at that path; do not move it."
            ),
        )
    text = _show_at(repo_root, fork, relpath, deadline)
    base_keys = _follow_renames(parse_baseline(text), _renames_since(repo_root, fork, deadline))
    added = sorted((Counter(baseline) - Counter(base_keys)).elements())
    return Growth(added, f"baseline growth vs merge base {fork[:12]}: {len(added)} line(s)")
