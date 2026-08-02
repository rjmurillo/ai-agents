"""Shared baseline helpers for skill portability validators."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path

from scripts.validation.portability_baseline import (
    read_previous_sections,
    refuse_dropped_entries,
    refuse_oversized_baseline,
    refuse_symlinked_baseline,
    refuse_undiffable_baseline,
    write_baseline_json,
)

RegressionMessageFactory = Callable[[str, int, int], str]


def load_baseline(path: Path) -> dict[str, int]:
    """Read and validate a portability ratchet baseline."""
    if not path.is_file():
        raise FileNotFoundError(f"Baseline file not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Baseline must be a JSON object")
    files = data["files"] if "files" in data else data
    if not isinstance(files, dict):
        raise ValueError("Baseline 'files' must be a JSON object")

    baseline: dict[str, int] = {}
    for key, value in files.items():
        if value is None:
            raise ValueError(f"Baseline count for {key!r} is null")
        try:
            baseline[str(key)] = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Baseline count for {key!r} is not an integer") from exc
    return baseline


def diff_against_baseline(
    current: dict[str, int],
    baseline: dict[str, int],
    regression_message: RegressionMessageFactory,
) -> tuple[list[str], list[str]]:
    """Return regressions and improvements for a baseline comparison."""
    regressions: list[str] = []
    for rel, count in sorted(current.items()):
        allowed = baseline.get(rel, 0)
        if count > allowed:
            regressions.append(regression_message(rel, count, allowed))

    improvements: list[str] = []
    for rel, allowed in sorted(baseline.items()):
        count = current.get(rel, 0)
        if count < allowed:
            improvements.append(f"{rel}: {count} refs (baseline {allowed})")
    return regressions, improvements


def build_portability_parser(
    description: str | None, default_baseline_name: str
) -> argparse.ArgumentParser:
    """Build the common CLI parser for portability ratchets."""
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repository root (default: walk up for .claude/skills).",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=None,
        help=f"Baseline JSON (default: scripts/validation/{default_baseline_name}).",
    )
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Rewrite the baseline to the current state and exit 0.",
    )
    parser.add_argument(
        "--allow-baseline-shrink",
        action="store_true",
        help="Permit a rewrite that drops recorded entries.",
    )
    parser.add_argument(
        "--output-format",
        choices=("human", "json"),
        default="human",
    )
    return parser


def resolve_root(repo_root: Path | None, start: Path, require_repo_marker: bool) -> Path:
    """Resolve the repository root for a portability scan."""
    if repo_root:
        return repo_root.resolve()

    base = start if start.is_dir() else start.parent
    for ancestor in (base, *base.parents):
        has_skills = (ancestor / ".claude" / "skills").is_dir()
        if not has_skills:
            continue
        has_repo_marker = (ancestor / ".git").exists() or (
            ancestor / "pyproject.toml"
        ).is_file()
        if has_repo_marker or not require_repo_marker:
            return ancestor
    return base


def resolve_baseline_path(
    root: Path,
    baseline: Path | None,
    default_baseline_name: str,
    reject_outside_root: bool,
) -> Path:
    """Resolve the baseline path, optionally rejecting root escapes.

    The single home for this reasoning. Every checker that accepts `--baseline`
    delegates here rather than keeping a copy, because the copies drifted into
    the same defect independently once already: both resolved the path before
    handing it on, which erased the symlink the guard downstream exists to
    refuse. Returns `Path("")` when the candidate escapes the root.
    """
    if baseline is None:
        return root / "scripts" / "validation" / default_baseline_name
    if not reject_outside_root:
        return baseline if baseline.is_absolute() else root / baseline

    root_resolved = root.resolve()
    candidate = baseline.expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    if not candidate.expanduser().resolve().is_relative_to(root_resolved):
        return Path("")
    # Return the candidate exactly as written, neither resolved nor textually
    # normalised. `resolve()` follows every symlink, which erases the evidence
    # the symlink guard exists to find. Collapsing `..` textually looks safer
    # but is not: `link/../victim.json` is containment-tested as the directory
    # the link points into and then collapses to a sibling of the link, so the
    # guard vets one file and hands back another, with no symlink left in the
    # result for the downstream check to catch. Kept whole, that same path
    # still names the link, and the link is refused.
    return candidate


def resolve_checked_baseline(
    root: Path,
    baseline: Path | None,
    default_baseline_name: str,
) -> Path | None:
    """Resolve the baseline and vet it, or explain on stderr and return None.

    Every checker that accepts `--baseline` needs the same two answers before
    it may trust the file: the path must stay inside the repository, and git
    must still show a reader when a count inside it goes down. Both were
    written out per checker once, and `resolve_baseline_path` above records
    what that cost: the copies drifted into the same defect independently.

    So this is the single gate rather than a third copy of the pair. Returning
    `None` for either refusal keeps the sentinel uniform too; the checkers had
    split into `None` and `Path("")` for the same condition, which is the same
    drift starting again in the return type.

    The symlink refusal belongs here and not only on the write path. The diff
    attribute is read from the pathname handed in, while `read_text()` follows
    the link, so a committed symlink lets the vetted name and the consumed file
    be two different files. Hiding the target rather than the name then lands
    every later lowering unseen, which is the attribute finding one indirection
    deeper. Refusing the link closes both, and it runs first because a link is
    the more basic objection: the target need not be inside the tree at all.
    """
    resolved = resolve_baseline_path(
        root, baseline, default_baseline_name, reject_outside_root=True
    )
    if resolved == Path(""):
        print(
            f"Refusing a --baseline outside the repository root: {baseline}. "
            "The ratchet only owns the artifact git tracks.",
            file=sys.stderr,
        )
        return None
    if refuse_symlinked_baseline(root, resolved):
        return None
    if refuse_undiffable_baseline(root, resolved):
        return None
    if refuse_oversized_baseline(resolved):
        return None
    return resolved


def write_baseline(
    baseline_path: Path,
    current: dict[str, int],
    comment: str,
    label: str,
    *,
    repo_root: Path,
    allow_shrink: bool,
) -> int:
    """Write a sorted portability baseline and print a standard summary.

    `repo_root` and `allow_shrink` are required and keyword-only on purpose.
    Both were optional once, and a checker that forgot them got a guard which
    looked for the committed baseline in the wrong directory and an escape
    hatch its own `--allow-baseline-shrink` flag could not reach. Nothing
    failed; the protection just quietly was not there. Required arguments turn
    the same omission into a TypeError at the call site.
    """
    total = sum(current.values())
    entries = dict(sorted(current.items()))
    rc = write_baseline_json(
        repo_root,
        baseline_path,
        {"_comment": comment, "files": entries},
        {"files": entries},
        label,
        allow_shrink,
    )
    if rc:
        return rc
    print(f"Baseline written: {len(current)} files, {total} {label}.")
    return 0


_GIT_ENV_OVERRIDES = (
    "GIT_INDEX_FILE",
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_COMMON_DIR",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_CEILING_DIRECTORIES",
)


def _git_lines(repo_root: Path, args: list[str]) -> list[str] | None:
    """Run a git plumbing command, None when git cannot answer.

    The ambient environment is stripped of repository-discovery variables.
    Inheriting GIT_INDEX_FILE lets a caller point the coverage probe at an
    index that agrees with a truncated disk, which is the one input that makes
    the probe confirm what it is supposed to test.
    """
    env = {
        key: value
        for key, value in os.environ.items()
        if key.upper() not in _GIT_ENV_OVERRIDES
    }
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
            check=False,
        )
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    return [line for line in proc.stdout.split("\0") if line]


def tracked_coverage_by_root(
    repo_root: Path, root_names: Iterable[str]
) -> dict[str, tuple[int, int]] | None:
    """Return (tracked, missing) file counts per root, None when git cannot answer.

    Presence is not coverage. Every root can hold one readable file and the
    checkout still be missing hundreds, which a per-root non-zero rule accepts.
    Git already knows what the tree should contain, so comparing the index
    against disk detects a sparse clone, a partial checkout, or a mistargeted
    root without persisting expected counts that would then drift.

    The tracked total is carried alongside the missing total because zero
    missing is not evidence of a full tree when zero files are indexed. An
    untracked root, a tree that is not a repository, and a mistargeted root all
    produce an empty listing that a missing count alone reads as complete.

    Intent-to-add entries are excluded. Git lists them as tracked while holding
    none of their content, so one `git add -N` would otherwise convert an
    untracked root into a vouched-for one.
    """
    names = list(root_names)
    intent_args = ["diff-files", "--diff-filter=A", "-z", "--name-only", "--", *names]
    pending = _git_lines(repo_root, intent_args)
    if pending is None:
        return None
    unreal = set(pending)
    coverage: dict[str, tuple[int, int]] = {}
    for name in names:
        tracked = _git_lines(repo_root, ["ls-files", "-z", "--", name])
        if tracked is None:
            return None
        real = [rel for rel in tracked if rel not in unreal]
        missing = sum(1 for rel in real if not (repo_root / rel).is_file())
        coverage[name] = (len(real), missing)
    return coverage


def _refuse_partial_worktree(root: Path, scanned_by_root: Mapping[str, int]) -> bool:
    """Refuse a baseline write whose completeness git cannot confirm."""
    names = list(scanned_by_root)
    unmerged = _git_lines(root, ["ls-files", "-u", "-z", "--", *names])
    if unmerged:
        print(
            "Refusing to write a baseline from a tree with unresolved conflicts under "
            "a scanned root. Conflict markers and half-merged content are not the "
            "state the ratchet should record. Finish the merge, then rerun.",
            file=sys.stderr,
        )
        return True
    coverage = tracked_coverage_by_root(root, names)
    if coverage is None:
        print(
            "Refusing to write a baseline that git cannot vouch for: no index could "
            f"be read for {root}. A baseline write replaces the record for every "
            "shipped root, so it needs proof the tree is whole, and an unreadable "
            "index is the state where that proof is most likely to be missing. "
            "Point --repo-root at a checkout of this repository.",
            file=sys.stderr,
        )
        return True
    untracked = sorted(name for name, (tracked, _) in coverage.items() if not tracked)
    if untracked:
        print(
            f"Refusing to write a baseline from roots git does not track: {', '.join(untracked)}. "
            "An empty index listing is what a mistargeted root, an unstaged tree, and "
            "a complete checkout all look like from the missing count alone, so a "
            "write here would drop every shipped file and forgive its violations. "
            "Stage the files, or point --repo-root at a checkout of this repository.",
            file=sys.stderr,
        )
        return True
    short = {name: missing for name, (_, missing) in sorted(coverage.items()) if missing}
    if not short:
        return False
    detail = ", ".join(f"{name} ({count} missing)" for name, count in short.items())
    print(
        f"Refusing to write a baseline from an incomplete checkout: {detail}. Git "
        "tracks files under those roots that are not on disk, so the scan read a "
        "subset and writing now would drop every absent file from the ratchet and "
        "silently forgive its violations. Restore the working tree, then rerun. A "
        "removal that is genuinely intended is declared with --allow-baseline-shrink, "
        "not by staging it: a reflexive `git add -A` would otherwise relabel an "
        "accidental wipe as intentional.",
        file=sys.stderr,
    )
    return True


def refuse_uncovered_scan(root: Path, scanned_by_root: Mapping[str, int], unit: str) -> bool:
    """Report and refuse a baseline write that did not cover every shipped root.

    Both portability ratchets share one hazard. A scan root can exist and still
    yield nothing to read, from a partial checkout, a sparse clone, or a
    mistargeted repo root. The offending-file mapping is empty in that case and
    equally empty for a genuinely clean tree, so the write path cannot tell them
    apart from counts alone.

    Coverage is per root, never a sum. A total stays positive while one root of
    several reads nothing, so summing hides the partial checkout this exists to
    catch: the write succeeds, exits 0, and drops every file the unread root
    owned. Presence is not coverage either, so a root that did read something is
    then checked against git: tracked files missing from disk mean the scan saw
    a subset. Completeness that git cannot confirm is refused rather than
    permitted, because an unreadable index and an untracked root are exactly the
    states where the tree is least likely to be whole. Returns True when the
    caller must refuse.
    """
    unread = sorted(name for name, found in scanned_by_root.items() if found < 1)
    if scanned_by_root and not unread:
        return _refuse_partial_worktree(root, scanned_by_root)
    names = ", ".join(unread) or "no scan roots were enumerated at all"
    read = ", ".join(
        f"{name} ({found})" for name, found in sorted(scanned_by_root.items()) if found
    )
    print(
        f"Refusing to write a baseline that read 0 {unit} under: {names}. "
        f"Roots that were read: {read or 'none'}. A shipped scan root holds nothing "
        "to read, so writing now would drop every file that root owns from the "
        "ratchet and silently forgive its violations. Check that --repo-root points "
        f"at a full checkout of {root}.",
        file=sys.stderr,
    )
    return True


def refuse_unsafe_baseline_write(
    root: Path,
    scanned_by_root: Mapping[str, int],
    baseline_path: Path,
    current: Mapping[str, Mapping[str, int]],
    unit: str,
    allow_shrink: bool,
) -> bool:
    """Decide whether a baseline rewrite is safe. True means the caller must refuse.

    Both ratchets ask the same question, so they ask it in one place rather than
    each growing a copy that drifts. Coverage runs first because an unread root
    explains the shrink that would otherwise be reported without a cause.
    """
    if refuse_uncovered_scan(root, scanned_by_root, unit):
        return True
    if refuse_symlinked_baseline(root, baseline_path):
        return True
    previous, problem = read_previous_sections(root, baseline_path)
    return refuse_dropped_entries(previous, current, unit, allow_shrink, problem)
