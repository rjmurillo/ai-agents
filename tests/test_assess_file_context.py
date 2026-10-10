"""Per-file threshold context in absolute mode (issue #6166).

Without ``--context``, each file is gated on its own category's thresholds.
An explicit ``--context`` overrides the category for every file.
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

# ruff: noqa: E402
from assess_file_context_helpers import CONFIG, assessment, check_thresholds


class TestAbsoluteMode:
    def test_test_file_uses_test_thresholds_without_context(self) -> None:
        a = assessment("tests/test_new.py", "test")
        assert check_thresholds([a], CONFIG, None) == 0

    def test_authored_file_keeps_production_thresholds(self) -> None:
        a = assessment("src/mod.py", "authored")
        assert check_thresholds([a], CONFIG, None) == 11

    def test_generated_file_uses_generated_thresholds(self) -> None:
        a = assessment("gen/out.py", "generated")
        assert check_thresholds([a], CONFIG, None) == 0

    def test_explicit_production_overrides_test_category(self) -> None:
        a = assessment("tests/test_new.py", "test")
        assert check_thresholds([a], CONFIG, "production") == 11

    def test_explicit_test_overrides_authored_category(self) -> None:
        a = assessment("src/mod.py", "authored")
        assert check_thresholds([a], CONFIG, "test") == 0

    def test_mixed_batch_fails_only_on_the_authored_file(self) -> None:
        batch = [
            assessment("tests/test_new.py", "test"),
            assessment("src/mod.py", "authored"),
        ]
        assert check_thresholds(batch, CONFIG, None) == 11

    def test_unknown_category_falls_back_to_production(self) -> None:
        a = assessment("x.py", "mystery")
        assert check_thresholds([a], CONFIG, None) == 11

    def test_missing_context_config_uses_base_thresholds(self) -> None:
        a = assessment("tests/test_new.py", "test")
        cfg = {"thresholds": CONFIG["thresholds"]}
        assert check_thresholds([a], cfg, None) == 11
