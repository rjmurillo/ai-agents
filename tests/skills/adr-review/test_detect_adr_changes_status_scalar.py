"""``_get_adr_status`` must reject a non-scalar ``status`` value, across both shipped trees.

Split out rather than appended to ``test_detect_adr_changes.py`` (494 lines,
against the 500-line taste-lint ceiling), matching the same reasoning
``test_detect_adr_changes_encoding.py`` and
``test_detect_adr_changes_duplicate_keys.py`` already recorded for their own
splits.

The contract: a YAML sequence or mapping under ``status:`` is not a status a
human ever intends (ADR-073's schema declares a bare scalar enum), but it is
valid YAML and reaches ``_get_adr_status`` all the same. Before this fix,
``str(status).strip().lower()`` ran on it unconditionally and returned a
Python repr such as ``"['accepted']"`` instead of the ``unknown`` sentinel
every other undeclared-status path already returns (Copilot, PR #5209
round-6 review). The fix mirrors
``scripts/validation/check_adr_lifecycle.py``'s ``_status_of()`` verbatim:
``if value is None or isinstance(value, (list, dict)): return ""`` (:409-414).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "tests" / "skills"))

from claude_skills_import import import_skill_script

_DETECTOR_TREES = [
    ".claude/skills/adr-review/scripts/detect_adr_changes.py",
    "src/copilot-cli/skills/adr-review/scripts/detect_adr_changes.py",
]


class TestNonScalarStatusIsUnknown:
    """A sequence or mapping under ``status:`` is undeclared, not a value to stringify."""

    @pytest.mark.parametrize("tree", _DETECTOR_TREES)
    @pytest.mark.parametrize(
        "frontmatter",
        [
            "id: A\nstatus:\n  - accepted\n",
            "id: A\nstatus: [accepted, proposed]\n",
            "id: A\nstatus:\n  value: accepted\n",
        ],
        ids=["block-sequence", "flow-sequence", "mapping"],
    )
    def test_sequence_or_mapping_status_returns_unknown(
        self, tmp_path: Path, tree: str, frontmatter: str
    ) -> None:
        detector = import_skill_script(tree)
        adr = tmp_path / "ADR-900-x.md"
        adr.write_text(f"---\n{frontmatter}---\n\n# ADR-900: X\n", encoding="utf-8")

        assert detector._get_adr_status(adr) == detector.STATUS_UNKNOWN

    @pytest.mark.parametrize("tree", _DETECTOR_TREES)
    def test_scalar_status_still_returns_the_declared_value(
        self, tmp_path: Path, tree: str
    ) -> None:
        """Negative control: the fix must not reject the ordinary scalar case."""
        detector = import_skill_script(tree)
        adr = tmp_path / "ADR-900-x.md"
        adr.write_text("---\nid: A\nstatus: accepted\n---\n\n# ADR-900: X\n", encoding="utf-8")

        assert detector._get_adr_status(adr) == "accepted"
