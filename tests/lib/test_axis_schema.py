"""Schema validation tests for `.claude/skills/review/references/{role}.md` canonical files.

Implements REQ-008-01 acceptance criteria 1, 2, 3, 4, 6: file presence,
required frontmatter keys, exact level-2 section headings, and Output
Schema field names. A maintainer renaming any required heading or
removing any required frontmatter key fails CI.

Spec: .agents/specs/requirements/REQ-008-review-axes-convergence.md
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.lib.conftest import validate_axis_schema

REPO_ROOT = Path(__file__).resolve().parents[2]
REVIEW_AXES_DIR = REPO_ROOT / ".claude" / "skills" / "review" / "references"

CANONICAL_ROLES: tuple[str, ...] = (
    "analyst",
    "architect",
    "qa",
    "security",
    "devops",
    "roadmap",
)


@pytest.mark.parametrize("role", CANONICAL_ROLES)
def test_canonical_axis_file_exists(role: str) -> None:
    path = REVIEW_AXES_DIR / f"{role}.md"
    assert path.exists(), f"canonical axis file missing: {path}"


@pytest.mark.parametrize("role", CANONICAL_ROLES)
def test_canonical_axis_file_passes_schema(role: str) -> None:
    path = REVIEW_AXES_DIR / f"{role}.md"
    validate_axis_schema(path)


def test_no_unexpected_axis_files() -> None:
    """Every `.md` file under .claude/skills/review/references/ must be a known canonical role.

    Prevents stray files from accumulating in the canonical directory and
    being silently ignored by the build script and `/review`.
    """
    found = {p.stem for p in REVIEW_AXES_DIR.glob("*.md")}
    expected = set(CANONICAL_ROLES)
    extra = found - expected
    missing = expected - found
    assert not extra, f"unexpected axis files in canonical dir: {sorted(extra)}"
    assert not missing, f"missing canonical axis files: {sorted(missing)}"
