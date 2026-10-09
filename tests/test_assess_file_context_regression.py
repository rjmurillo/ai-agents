"""Per-file threshold context for new files in regression mode (issue #6166).
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

# ruff: noqa: E402
from assess_file_context_helpers import CONFIG, assessment, check_regression


class TestRegressionModeNewFiles:
    def test_new_test_file_uses_test_thresholds_without_context(self) -> None:
        a = assessment("tests/test_new.py", "test")
        assert check_regression([], [a], CONFIG, None) == 0

    def test_new_authored_file_keeps_production_thresholds(self) -> None:
        a = assessment("src/mod.py", "authored")
        assert check_regression([], [a], CONFIG, None) == 11

    def test_explicit_production_overrides_new_test_file(self) -> None:
        a = assessment("tests/test_new.py", "test")
        assert check_regression([], [a], CONFIG, "production") == 11
