"""Shared baseline helpers for skill portability validators."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path

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
    """Resolve the baseline path, optionally rejecting root escapes."""
    if baseline is None:
        return root / "scripts" / "validation" / default_baseline_name
    if not reject_outside_root:
        return baseline if baseline.is_absolute() else root / baseline

    root_resolved = root.resolve()
    resolved = (
        baseline.expanduser().resolve()
        if baseline.is_absolute()
        else (root / baseline).expanduser().resolve()
    )
    if not resolved.is_relative_to(root_resolved):
        return Path("")
    return resolved


def write_baseline(
    baseline_path: Path, current: dict[str, int], comment: str, label: str
) -> int:
    """Write a sorted portability baseline and print a standard summary."""
    total = sum(current.values())
    baseline_path.write_text(
        json.dumps(
            {
                "_comment": comment,
                "files": dict(sorted(current.items())),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Baseline written: {len(current)} files, {total} {label}.")
    return 0


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
    """
    coverage: dict[str, tuple[int, int]] = {}
    for name in root_names:
        try:
            proc = subprocess.run(
                ["git", "-C", str(repo_root), "ls-files", "-z", "--", name],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
        except OSError:
            return None
        if proc.returncode != 0:
            return None
        tracked = [rel for rel in proc.stdout.split("\0") if rel]
        coverage[name] = (len(tracked), sum(1 for rel in tracked if not (repo_root / rel).exists()))
    return coverage


def _refuse_partial_worktree(root: Path, scanned_by_root: Mapping[str, int]) -> bool:
    """Refuse a baseline write whose completeness git cannot confirm."""
    coverage = tracked_coverage_by_root(root, scanned_by_root)
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
        "silently forgive its violations. Restore the working tree, or stage the "
        "deletions so git agrees they are gone, then rerun.",
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
