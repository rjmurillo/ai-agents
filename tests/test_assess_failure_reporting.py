"""`_assess_files` must report a file that fails, never drop it.

Dropping it made the failure invisible downstream: `summary.file_count` is the
length of the returned list, so a run that lost four of five files still looked
internally consistent, and a consumer could read the survivor as evidence that
the whole change was assessed. `/review`'s verdict adapter is such a consumer.

Kept out of ``test_assess_regression.py`` so that module stays under the
taste-lints size warning; this concern is a different one from the regression
gate it covers.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

# sys.path manipulation is required before the assess import. The skill's
# scripts directory is not on sys.path by default.
_SKILL_SCRIPTS = (
    Path(__file__).resolve().parents[1]
    / ".claude"
    / "skills"
    / "code-qualities-assessment"
    / "scripts"
)
sys.path.insert(0, str(_SKILL_SCRIPTS))

# ruff: noqa: E402
import assess


class TestAssessFilesReportsFailures:
    """A file that fails to assess is reported, never dropped.

    Dropping it made the failure invisible: `summary.file_count` is the length
    of the returned list, so a run that lost four of five files still looked
    internally consistent and a consumer could read the survivor as evidence
    that the whole change was assessed.
    """

    def test_failed_file_is_recorded_as_unscored(self, tmp_path):
        good = tmp_path / "good.py"
        good.write_text("def f():\n    return 1\n", encoding="utf-8")
        bad = tmp_path / "bad.py"
        bad.write_text("def g():\n    return 2\n", encoding="utf-8")

        real = assess.assess_file

        def _explode(path, context, use_serena):
            if path == bad:
                raise RuntimeError("boom")
            return real(path, context, use_serena)

        with patch.object(assess, "assess_file", side_effect=_explode):
            results = assess._assess_files([good, bad], "production", False)

        assert len(results) == 2, "the failed file must still appear in the list"
        by_path = {r.file_path: r for r in results}
        failed = by_path[str(bad)]
        assert failed.cohesion.confidence == 0.0
        assert any("assessment failed" in r for r in failed.cohesion.reasons)
        assert by_path[str(good)].cohesion.confidence > 0.0

    def test_all_files_failing_yields_all_unscored(self, tmp_path):
        """Negative control: nothing is silently salvaged."""
        f = tmp_path / "a.py"
        f.write_text("def f():\n    return 1\n", encoding="utf-8")
        with patch.object(assess, "assess_file", side_effect=RuntimeError("boom")):
            results = assess._assess_files([f], "production", False)
        assert len(results) == 1
        assert results[0].cohesion.confidence == 0.0
