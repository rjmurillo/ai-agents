"""Drift detection between CI-FEEDBACK-SUBLOOP.md and the canonical axis list.

The governance doc `.agents/governance/CI-FEEDBACK-SUBLOOP.md` historically
restated a partial 7-entry allowlist of review axes, which drifted from the
12-axis `CANONICAL_ROLES` tuple in `tests/lib/test_axis_schema.py`. PR #2425
resolved this by removing the restated list and pointing readers at
`CANONICAL_ROLES` as the single source of truth.

This test guards against regression: if the doc is reintroduced or rewritten,
it must reference both `CANONICAL_ROLES` (the canonical Python identifier)
and `tests/lib/test_axis_schema.py` (the canonical file path). Restating a
partial list would omit those references and fail the assertion.

The test conditionally skips when the doc file is absent (today's state on
`main`), so it lands cleanly now and activates the moment PR #2425 merges.

Fixes: https://github.com/rjmurillo/ai-agents/issues/2452
Analysis: https://github.com/rjmurillo/ai-agents/issues/2452#issuecomment-4636552877
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CI_FEEDBACK_SUBLOOP_DOC = REPO_ROOT / ".agents" / "governance" / "CI-FEEDBACK-SUBLOOP.md"


def test_ci_feedback_subloop_references_canonical_axis_source() -> None:
    """If the doc exists, it must defer to CANONICAL_ROLES instead of restating axes.

    Asserting the canonical reference is present prevents anyone from
    re-introducing a hardcoded partial allowlist that would drift from
    `tests/lib/test_axis_schema.py::CANONICAL_ROLES`.
    """
    if not CI_FEEDBACK_SUBLOOP_DOC.exists():
        pytest.skip(
            f"{CI_FEEDBACK_SUBLOOP_DOC.relative_to(REPO_ROOT)} not present on this branch; "
            "drift check activates when PR #2425 (or successor) lands the doc on main."
        )

    body = CI_FEEDBACK_SUBLOOP_DOC.read_text(encoding="utf-8")

    assert "CANONICAL_ROLES" in body, (
        f"{CI_FEEDBACK_SUBLOOP_DOC.relative_to(REPO_ROOT)} must reference the "
        "`CANONICAL_ROLES` identifier instead of restating the axis list. "
        "Update the doc to point readers at tests/lib/test_axis_schema.py::CANONICAL_ROLES."
    )
    assert "tests/lib/test_axis_schema.py" in body, (
        f"{CI_FEEDBACK_SUBLOOP_DOC.relative_to(REPO_ROOT)} must reference the "
        "canonical file path `tests/lib/test_axis_schema.py` so readers can locate "
        "the authoritative axis tuple."
    )
