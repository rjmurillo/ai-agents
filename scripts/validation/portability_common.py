"""Shared baseline helpers for skill portability validators."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
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
        has_repo_marker = (
            (ancestor / ".git").exists()
            or (ancestor / "pyproject.toml").is_file()
            or (ancestor / "AGENTS.md").is_file()
        )
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
