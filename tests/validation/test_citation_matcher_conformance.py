"""Conformance of the canonical-source-mirror rule to the citation matchers (#5399).

The rule template states what the citation matcher accepts and rejects. It
names `_CITATION` and `_IGNORE_WITH_REASON` instead of copying their
patterns. These tests run the real matchers against each stated behavior, so
a change to either matcher fails here instead of leaving the rule stale.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from scripts.validation import check_citation_freshness as freshness
from scripts.validation.citation_anchors import _CITATION

RULE_TEMPLATE = (
    Path(__file__).resolve().parents[2] / "templates" / "rules" / "canonical-source-mirror.md"
)


def _cite(path: str, span: str) -> str:
    return f"see {path}:{span} for the contract"


class TestCitationMatcher:
    @pytest.mark.parametrize("path", ["scripts/a.py", "docs/b.md", "cfg/c.toml", "root.yml"])
    def test_listed_extension_with_line_number_matches(self, path: str) -> None:
        match = _CITATION.search(_cite(path, "12"))

        assert match is not None
        assert match.group("path") == path

    def test_line_range_is_captured(self) -> None:
        match = _CITATION.search(_cite("scripts/a.py", "12-15"))

        assert match is not None
        assert (match.group("start"), match.group("end")) == ("12", "15")

    def test_unlisted_extension_never_matches(self) -> None:
        assert _CITATION.search(_cite("scripts/a.unknownext", "12")) is None

    def test_path_without_line_number_never_matches(self) -> None:
        assert _CITATION.search("see scripts/a.py for the contract") is None

    @pytest.mark.parametrize("path", ["/etc/passwd.txt", "C:\\tmp\\a.py", "../up/a.py"])
    def test_absolute_and_parent_relative_paths_never_match(self, path: str) -> None:
        assert _CITATION.search(_cite(path, "3")) is None

    def test_slashless_name_matches_the_pattern_and_leaves_tracking_to_the_gate(self) -> None:
        match = _CITATION.search(_cite("AGENTS.md", "4"))

        assert match is not None
        assert "/" not in match.group("path")


class TestEscapeHatch:
    def test_marker_with_reason_counts(self) -> None:
        line = f"{freshness.IGNORE_MARKER} -- quoting the pre-fix state"

        assert freshness._IGNORE_WITH_REASON.search(line) is not None

    @pytest.mark.parametrize("suffix", ["", " --", " -- ", " no dashes here"])
    def test_marker_without_reason_does_not_count(self, suffix: str) -> None:
        line = f"{freshness.IGNORE_MARKER}{suffix}"

        assert freshness._IGNORE_WITH_REASON.search(line) is None


class TestRuleTemplate:
    def test_rule_names_both_matchers(self) -> None:
        text = RULE_TEMPLATE.read_text(encoding="utf-8")

        assert "`_CITATION`" in text
        assert "`_IGNORE_WITH_REASON`" in text

    def test_rule_does_not_copy_matcher_source(self) -> None:
        text = RULE_TEMPLATE.read_text(encoding="utf-8")

        assert "_CITATION = re.compile" not in text
        assert "_IGNORE_WITH_REASON = re.compile" not in text
        assert "(?P<path>" not in text

    def test_rule_names_symbols_that_exist(self) -> None:
        assert hasattr(freshness, "_IGNORE_WITH_REASON")
        assert isinstance(_CITATION, re.Pattern)
