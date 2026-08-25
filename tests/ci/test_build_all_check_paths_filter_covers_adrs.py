"""The whole-tree build_all.py --check gate must run whenever the ADR corpus changes.

`.agents/architecture/README.md` is generated from every ADR record under
`.agents/architecture/`. The gate that catches drift in that generated file
is the required `Validate Generated Files` job in
`validate-generated-agents.yml`, which runs the whole-tree
`build_all.py --check` staleness check, gated behind a `dorny/paths-filter`
`agents` entry. Without an entry covering the ADR corpus, an ADR-only PR
reports the required check as skipped (green) while a stale committed index
merges undetected: `.claude/rules/ci-scripts.md` names this exact shape,
"Path filters gate the diff, never the tree" (Copilot, PR #5285 review).
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path, PurePosixPath

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github/workflows/validate-generated-agents.yml"
PATHS_FILTER_ACTION = "dorny/paths-filter"


def _paths_filter_step() -> dict:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    for step in workflow["jobs"]["check-paths"]["steps"]:
        if str(step.get("uses", "")).startswith(f"{PATHS_FILTER_ACTION}@"):
            return step
    raise AssertionError(
        f"validate-generated-agents.yml check-paths has no {PATHS_FILTER_ACTION} step"
    )


def _agents_filter() -> list[str]:
    return yaml.safe_load(_paths_filter_step()["with"]["filters"])["agents"]


def _selected(path: str, patterns: Iterable[str]) -> bool:
    """Whether ``dorny/paths-filter`` selects a repo-relative path.

    Same model verified in
    ``tests/ci/test_pytest_paths_filter_covers_episodes.py``: the action
    compiles every entry as ``picomatch(pattern, {dot: true})``, for which
    ``PurePosixPath.full_match`` is a checked stand-in (see that file's
    docstring for the corpus-wide verification against the pinned action
    version).
    """
    return any(PurePosixPath(path).full_match(str(pattern)) for pattern in patterns)


def test_the_filter_covers_the_adr_corpus() -> None:
    assert ".agents/architecture/**" in _agents_filter()


def test_an_adr_only_change_selects_the_validation_job() -> None:
    """Positive control: a real ADR path and the generated index both match."""
    patterns = _agents_filter()
    assert _selected(".agents/architecture/ADR-005-example.md", patterns)
    assert _selected(".agents/architecture/README.md", patterns)


def test_removing_the_adr_entry_leaves_an_adr_change_unselected() -> None:
    """Negative control: no other entry in the list happens to also cover it.

    Proves the ``.agents/architecture/**`` entry is load-bearing rather than
    redundant with a broader pattern already present (Copilot, PR #5285
    review): dropping it and re-checking the same path must fail selection.
    """
    patterns = [p for p in _agents_filter() if p != ".agents/architecture/**"]
    assert not _selected(".agents/architecture/ADR-005-example.md", patterns)
