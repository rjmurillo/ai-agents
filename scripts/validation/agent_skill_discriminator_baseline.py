"""Baseline ratchet helpers for check_agent_skill_discriminator.py."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

DEFAULT_BASELINE_NAME = "agent_skill_discriminator_baseline.json"


@dataclass(frozen=True, slots=True)
class BaselineComparison:
    """Full-corpus comparison against the recorded candidate baseline."""

    current: dict[str, int]
    baseline: dict[str, int]

    @property
    def regressions(self) -> dict[str, int]:
        """Candidates absent from the baseline."""
        return {
            path: count
            for path, count in self.current.items()
            if count > self.baseline.get(path, 0)
        }

    @property
    def existing(self) -> dict[str, int]:
        """Candidates already recorded in the baseline."""
        return {
            path: count
            for path, count in self.current.items()
            if path not in self.regressions
        }

    @property
    def improvements(self) -> dict[str, int]:
        """Baseline entries that are no longer candidates."""
        return {
            path: count
            for path, count in self.baseline.items()
            if self.current.get(path, 0) < count
        }


def collect_agent_paths(
    repo_root: Path, is_agent_path: Callable[[str], bool]
) -> tuple[list[str], dict[str, int]]:
    """Return every agent path plus scan counts for the baseline guard."""
    roots = {
        ".claude/agents": repo_root / ".claude" / "agents",
        "templates/agents": repo_root / "templates" / "agents",
    }
    paths: list[str] = []
    scanned_by_root: dict[str, int] = {}
    for root_name, directory in roots.items():
        count = 0
        if directory.is_dir():
            for path in sorted(directory.rglob("*.md")):
                rel = str(path.relative_to(repo_root))
                if is_agent_path(rel):
                    paths.append(rel)
                    count += 1
        scanned_by_root[root_name] = count
    return paths, scanned_by_root


def load_candidate_baseline(path: Path) -> dict[str, int]:
    """Read the candidate baseline JSON."""
    if not path.is_file():
        raise FileNotFoundError(f"Baseline file not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Baseline must be a JSON object")
    candidates = data.get("candidates")
    if not isinstance(candidates, dict):
        raise ValueError("Baseline 'candidates' must be a JSON object")

    baseline: dict[str, int] = {}
    for key, value in candidates.items():
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError(
                f"Baseline count for {key!r} must be a JSON integer, "
                f"got {type(value).__name__}"
            )
        baseline[str(key)] = value
    return baseline


def compare_baseline(
    current: Mapping[str, int], baseline: Mapping[str, int]
) -> BaselineComparison:
    """Compare current candidates to the recorded baseline."""
    return BaselineComparison(current=dict(current), baseline=dict(baseline))


def print_baseline_comparison(comparison: BaselineComparison) -> int:
    """Print full-corpus ratchet output and return its exit code."""
    print()
    print("Full-corpus baseline ratchet (Issue #4087)")
    print(
        f"  Baseline candidates: {len(comparison.baseline)}; "
        f"current candidates: {len(comparison.current)}"
    )
    if comparison.existing:
        print("  Existing candidates recorded in baseline:")
        for path in sorted(comparison.existing):
            print(f"    - {path}")
    if comparison.improvements:
        print("  Candidates no longer present:")
        for path in sorted(comparison.improvements):
            print(f"    - {path}")
    if comparison.regressions:
        print("  New unbaselined candidates:")
        for path in sorted(comparison.regressions):
            print(f"    - {path}")
        return 1
    print("PASS: no new full-corpus discriminator candidates.")
    return 0


def resolve_baseline_path(repo_root: Path, baseline: Path | None) -> Path:
    """Resolve the discriminator baseline path."""
    baseline_path = (
        (repo_root / "scripts" / "validation" / DEFAULT_BASELINE_NAME)
        if baseline is None
        else baseline
    )
    if baseline_path.is_absolute():
        return baseline_path
    return repo_root / baseline_path


def write_candidate_baseline(
    repo_root: Path,
    baseline_path: Path,
    current: Mapping[str, int],
    scanned_by_root: Mapping[str, int],
    allow_shrink: bool,
) -> int:
    """Write the candidate baseline with the shared unsafe-write guard."""
    _ensure_repo_root_on_path(repo_root)
    from scripts.validation.portability_baseline import write_baseline_json
    from scripts.validation.portability_common import refuse_unsafe_baseline_write

    counted = {"candidates": dict(sorted(current.items()))}
    if refuse_unsafe_baseline_write(
        repo_root,
        scanned_by_root,
        baseline_path,
        counted,
        "agent-skill candidates",
        allow_shrink,
    ):
        return 2

    payload = {
        "_comment": (
            "Agent-skill discriminator full-corpus baseline for issue #4087. "
            "The candidates object records current unescaped skill-shape agents. "
            "Lower values are better; new entries fail the ratchet."
        ),
        "candidates": counted["candidates"],
    }
    rc = write_baseline_json(
        repo_root,
        baseline_path,
        payload,
        counted,
        "agent-skill candidates",
        allow_shrink,
    )
    if rc:
        return rc
    print(
        f"Baseline written: {len(current)} candidates in "
        f"{baseline_path.relative_to(repo_root)}."
    )
    return 0


def _ensure_repo_root_on_path(repo_root: Path) -> None:
    """Make shared validation helpers importable when this file runs by path."""
    root = str(repo_root)
    if root not in sys.path:
        sys.path.insert(0, root)
