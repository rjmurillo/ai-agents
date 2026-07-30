"""Regression tests for ADR-079 issue #3875.

Issue #3875 measured the unmeasured traffic assumption in ADR-079 point 4 and
found it false: 33% of recently merged PRs touched packaged plugin source. The
ADR must record that measurement instead of continuing to rely on the older
"believed to be a small fraction" claim.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ADR_PATH = PROJECT_ROOT / ".agents" / "architecture" / "ADR-079-merge-time-plugin-version-bump.md"
_DASH_PATTERN = re.compile("[\u2013\u2014]")


@pytest.fixture(scope="module")
def adr_text() -> str:
    assert ADR_PATH.is_file(), f"ADR file not found at canonical path: {ADR_PATH}"
    return ADR_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def normalized_adr_text(adr_text: str) -> str:
    return re.sub(r"\s+", " ", adr_text)


class TestIssue3875Measurement:
    def test_replaces_unmeasured_small_fraction_claim(self, normalized_adr_text: str) -> None:
        assert "believed to be a small fraction" not in normalized_adr_text
        assert "unmeasured assumption" not in normalized_adr_text
        assert "60 most recently merged PRs" in normalized_adr_text
        assert "20 touched packaged plugin source" in normalized_adr_text
        assert "33%" in normalized_adr_text

    def test_records_open_pr_sample_as_context_not_decision_basis(
        self, normalized_adr_text: str
    ) -> None:
        assert "26 open PRs" in normalized_adr_text
        assert "14 that touched packaged plugin source" in normalized_adr_text
        assert "54%" in normalized_adr_text
        assert "biased" in normalized_adr_text.lower()
        assert "33%" in normalized_adr_text

    def test_cost_statement_includes_gate_rerun_not_only_rebase(
        self, normalized_adr_text: str
    ) -> None:
        assert "pre-push hook" in normalized_adr_text
        assert "gate chain" in normalized_adr_text
        assert "not just a rebase" in normalized_adr_text

    def test_merge_driver_option_is_evaluated_as_new_alternative(
        self, normalized_adr_text: str
    ) -> None:
        assert "git merge driver" in normalized_adr_text.lower()
        assert "version-only" in normalized_adr_text
        assert "fail closed" in normalized_adr_text
        assert "not chosen" in normalized_adr_text.lower()


class TestAdr079Style:
    def test_contains_no_em_or_en_dash(self, adr_text: str) -> None:
        match = _DASH_PATTERN.search(adr_text)
        assert match is None, f"prohibited dash at offset {match.start()}" if match else ""
