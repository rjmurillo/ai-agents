"""Consumer-side invariant tests for the memory health result parser (#3971).

Split out of ``test_parse_memory_health_results.py`` to keep both files under
the 500-line taste-lint ceiling. The helpers are imported from that module
rather than duplicated, matching the sibling-import convention already used by
``test_adr006_scanner_heredoc.py`` and ``test_validation_scripts_are_reachable.py``.

These classes exist because a report read from disk never passes through
``HealthReport.__post_init__``. The producer enforces three invariants at
construction; a consumer whose whole job is detecting drift has to re-check
them itself or it will render broken parts as a plausible banner.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from scripts.ci import parse_memory_health_results as parser
from tests.ci.test_parse_memory_health_results import (
    HEALTHY_REPORT,
    _outputs,
    _parsed,
    _report,
    _with,
)


class TestCitationSumIsChecked:
    """The consumer mirrors the producer's citation-sum invariant.

    A report read from disk never passes through ``HealthReport.__post_init__``,
    so parts that do not add up would render as a plausible banner instead of
    surfacing the drift this script exists to catch.
    """

    def test_matching_sum_is_accepted(self, tmp_path: Path, monkeypatch) -> None:
        """Positive: a real report's parts add up and must still pass."""
        out = _outputs(tmp_path, monkeypatch)
        payload = _with(
            total_citations=6,
            valid_citations=3,
            stale_citations=1,
            broken_citations=1,
            unverified_citations=1,
        )
        assert parser.main(["--results", str(_report(tmp_path, payload))]) == 0
        assert _parsed(out)["total_citations"] == "6"

    @pytest.mark.parametrize(
        "overrides",
        [
            {"total_citations": 9},
            {"valid_citations": 7},
            {"broken_citations": 1},
            {"stale_citations": 2, "valid_citations": 8},
            {"unverified_citations": 4},
        ],
    )
    def test_mismatched_sum_is_rejected(
        self, tmp_path: Path, monkeypatch, capsys, overrides: dict[str, Any]
    ) -> None:
        """Negative: every part is load-bearing, so any one of them can break it."""
        _outputs(tmp_path, monkeypatch)
        assert parser.main(["--results", str(_report(tmp_path, _with(**overrides)))]) == 1
        assert "sum to total_citations" in capsys.readouterr().out

    def test_a_zero_citation_report_is_accepted(self, tmp_path: Path, monkeypatch) -> None:
        """Edge: an empty corpus sums to zero and must not read as drift."""
        _outputs(tmp_path, monkeypatch)
        payload = _with(total_citations=0, valid_citations=0)
        assert parser.main(["--results", str(_report(tmp_path, payload))]) == 0


class TestProducerInvariantsAreMirrored:
    """The consumer's guards must track the producer's, not a magic constant.

    These construct the real ``HealthReport`` rather than asserting on a
    literal. If the producer ever widens ``health_score`` past 0..1 or drops the
    citation-sum rule, the consumer's stricter guard becomes a false failure and
    these tests say so at that commit instead of in a red CI run months later.
    """

    @staticmethod
    def _kwargs(**overrides: Any) -> dict[str, Any]:
        return {**HEALTHY_REPORT, **overrides}

    def test_the_producer_type_is_constructible(self) -> None:
        """Negative control: if construction always raised, the rest is vacuous.

        Asserts only that a valid payload yields an instance. Asserting a
        particular ``health_score`` here would couple the control to the
        fixture's value, so a producer that changed the healthy score while
        staying constructible would fail this test for the wrong reason.
        """
        from scripts.memory_enhancement.models import HealthReport

        assert isinstance(HealthReport(**self._kwargs()), HealthReport)

    @pytest.mark.parametrize("score", [1.5, -0.1])
    def test_the_producer_rejects_out_of_range_scores(self, score: float) -> None:
        """Positive: proves the consumer's 0..1 bound is the producer's bound."""
        from scripts.memory_enhancement.models import HealthReport

        with pytest.raises(ValueError, match="health_score"):
            HealthReport(**self._kwargs(health_score=score))

    @pytest.mark.parametrize("score", [0.0, 1.0])
    def test_the_producer_accepts_the_bounds(self, score: float) -> None:
        """Edge: the producer's bound is inclusive, so the consumer's must be."""
        from scripts.memory_enhancement.models import HealthReport

        assert HealthReport(**self._kwargs(health_score=score)) is not None

    def test_the_producer_rejects_a_mismatched_citation_sum(self) -> None:
        """Positive: proves the consumer's sum check mirrors a real invariant."""
        from scripts.memory_enhancement.models import HealthReport

        with pytest.raises(ValueError, match="sum to total_citations"):
            HealthReport(**self._kwargs(total_citations=9, valid_citations=1))

    def test_the_shared_fixture_satisfies_the_producer(self) -> None:
        """Negative control: an invalid fixture would make every test above weak."""
        from scripts.memory_enhancement.models import HealthReport

        assert HealthReport(**self._kwargs()) is not None
