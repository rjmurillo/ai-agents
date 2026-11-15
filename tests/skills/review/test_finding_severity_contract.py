"""Per-finding severity contract for the rendered review (issue #7351).

The review skill once labeled every finding from its axis verdict, so a WARN
axis with one high and one low finding printed both as IMPORTANT. The contract
now lives in ``resources/finding-severity.md``: a finding keeps the severity
its axis recorded, and the axis verdict never flows back down.

The mapping is parsed from the shipped table and applied to mixed-severity
fixtures, so the tests fail when the table changes, not only when a sentence
does.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
REVIEW = PROJECT_ROOT / ".claude" / "skills" / "review"
SKILL = REVIEW / "SKILL.md"
RESOURCE = REVIEW / "resources" / "finding-severity.md"
REFERENCES = REVIEW / "references"
TECHNICAL_REVIEW = REVIEW / "resources" / "technical-review.md"
TEMPLATE = PROJECT_ROOT / "templates" / "skills" / "review.SKILL.md.tmpl"
PROJECTIONS = [
    PROJECT_ROOT / "src" / harness / "skills" / "review"
    for harness in ("claude", "copilot-cli", "codex", "cursor", "muse")
]

UNSPECIFIED = "UNSPECIFIED"
_ROW = re.compile(r"^\|\s*(?P<values>`[^|]+?)\s*\|\s*(?P<label>[A-Z]+)\s*\|\s*$", re.MULTILINE)
_TOKEN = re.compile(r"`([^`]+)`")
_ABSENT_ROW = re.compile(
    r"^\|\s*absent or any other value\s*\|\s*(?P<label>[A-Z]+)\s*\|\s*$", re.MULTILINE
)


def _mapping(text: str) -> dict[str, str]:
    """Parse the value-to-label table out of the resource."""
    table: dict[str, str] = {}
    for row in _ROW.finditer(text):
        for token in _TOKEN.findall(row.group("values")):
            table[token.lower()] = row.group("label")
    return table


def _fallback(text: str) -> str:
    match = _ABSENT_ROW.search(text)
    assert match, "table has no absent-or-other row"
    return match.group("label")


def render(finding: Mapping[str, str | None], table: dict[str, str], fallback: str) -> str:
    """Label one finding from its own value only. Never reads the axis verdict."""
    value = finding.get("severity")
    if value is None:
        return fallback
    return table.get(value.strip().lower(), fallback)


@pytest.fixture(scope="module")
def resource_text() -> str:
    return RESOURCE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def table(resource_text: str) -> dict[str, str]:
    return _mapping(resource_text)


@pytest.fixture(scope="module")
def fallback(resource_text: str) -> str:
    return _fallback(resource_text)


def _axis_severity_tokens() -> set[str]:
    """Every severity token the axis reference files declare."""
    tokens: set[str] = set()
    for path in sorted(REFERENCES.glob("*.md")):
        for match in re.finditer(r'"severity":\s*"([^"]+)"', path.read_text(encoding="utf-8")):
            tokens.update(match.group(1).split("|"))
    return tokens


class TestMappingTable:
    def test_axes_declare_the_four_severities(self) -> None:
        assert _axis_severity_tokens() == {"critical", "high", "medium", "low"}

    def test_every_axis_severity_token_is_mapped(self, table: dict[str, str]) -> None:
        missing = _axis_severity_tokens() - set(table)
        assert not missing, f"axis severity tokens with no row: {sorted(missing)}"

    def test_qa_blocking_is_mapped(self, table: dict[str, str]) -> None:
        assert "blocking" in table

    def test_step_4c_dispositions_are_mapped(self, table: dict[str, str]) -> None:
        text = TECHNICAL_REVIEW.read_text(encoding="utf-8")
        assert "`blocking`, `non-blocking`, or `polish`" in text
        assert {"blocking", "non-blocking", "polish"} <= set(table)

    def test_critical_and_high_are_the_only_ones_above_suggestion(
        self, table: dict[str, str]
    ) -> None:
        assert table["critical"] == "CRITICAL"
        assert table["high"] == "IMPORTANT"
        assert table["medium"] == "SUGGESTION"
        assert table["low"] == "SUGGESTION"

    def test_table_has_no_duplicate_value_with_two_labels(self, resource_text: str) -> None:
        seen: dict[str, str] = {}
        for row in _ROW.finditer(resource_text):
            for token in _TOKEN.findall(row.group("values")):
                key = token.lower()
                assert seen.setdefault(key, row.group("label")) == row.group("label"), key

    def test_missing_severity_has_its_own_label(self, table: dict[str, str], fallback: str) -> None:
        assert fallback == UNSPECIFIED
        assert UNSPECIFIED not in set(table.values())


class TestMixedSeverityFindings:
    """The issue's acceptance criteria, applied through the shipped table."""

    def test_warn_axis_keeps_high_and_low_distinct(
        self, table: dict[str, str], fallback: str
    ) -> None:
        # The axis verdict is WARN. It plays no part in the labels.
        findings = [{"severity": "high"}, {"severity": "low"}]
        labels = [render(f, table, fallback) for f in findings]
        assert labels == ["IMPORTANT", "SUGGESTION"]

    def test_critical_fail_axis_does_not_label_everything_critical(
        self, table: dict[str, str], fallback: str
    ) -> None:
        findings = [{"severity": "critical"}, {"severity": "low"}]
        labels = [render(f, table, fallback) for f in findings]
        assert labels == ["CRITICAL", "SUGGESTION"]

    def test_permuting_findings_changes_no_label(
        self, table: dict[str, str], fallback: str
    ) -> None:
        findings = [
            {"severity": "critical"},
            {"severity": "high"},
            {"severity": "medium"},
            {"severity": "low"},
        ]
        expected = {f["severity"]: render(f, table, fallback) for f in findings}
        for ordering in (findings, findings[::-1], findings[2:] + findings[:2]):
            assert {f["severity"]: render(f, table, fallback) for f in ordering} == expected

    def test_adding_an_unrelated_low_item_changes_no_label(
        self, table: dict[str, str], fallback: str
    ) -> None:
        before = [{"severity": "high"}, {"severity": "medium"}]
        after = [*before, {"severity": "low"}]
        assert [render(f, table, fallback) for f in after[:2]] == [
            render(f, table, fallback) for f in before
        ]

    @pytest.mark.parametrize("value", ["HIGH", "High", " high "])
    def test_value_match_is_case_and_space_insensitive(
        self, value: str, table: dict[str, str], fallback: str
    ) -> None:
        assert render({"severity": value}, table, fallback) == "IMPORTANT"

    @pytest.mark.parametrize(
        "finding", [{}, {"severity": None}, {"severity": "urgent"}, {"severity": ""}]
    )
    def test_missing_or_unknown_value_is_unspecified_not_borrowed(
        self, finding: Mapping[str, str | None], table: dict[str, str], fallback: str
    ) -> None:
        assert render(finding, table, fallback) == UNSPECIFIED

    def test_medium_is_not_promoted_by_a_critical_neighbour(
        self, table: dict[str, str], fallback: str
    ) -> None:
        findings = [{"severity": "critical"}, {"severity": "medium"}]
        assert render(findings[1], table, fallback) == "SUGGESTION"


class TestSkillWiring:
    def test_skill_no_longer_derives_severity_from_the_axis_verdict(self) -> None:
        for root in PROJECTIONS:
            text = (root / "SKILL.md").read_text(encoding="utf-8")
            assert "if its axis verdict is" not in text, root
            assert "Categorize a finding as" not in text, root
        assert "Categorize a finding as" not in TEMPLATE.read_text(encoding="utf-8")

    def test_skill_output_lists_all_four_labels_and_points_to_the_resource(self) -> None:
        text = SKILL.read_text(encoding="utf-8")
        assert "CRITICAL | IMPORTANT | SUGGESTION | UNSPECIFIED" in text
        assert "resources/finding-severity.md" in text
        assert "never its axis verdict" in text

    def test_label_is_display_only(self, resource_text: str) -> None:
        assert "never feeds `merge_verdicts`" in resource_text
        assert "display only" in resource_text.lower()

    def test_every_projection_ships_the_resource_byte_identical(self) -> None:
        canonical = RESOURCE.read_bytes()
        for root in PROJECTIONS:
            assert (root / "resources" / "finding-severity.md").read_bytes() == canonical, root

    def test_every_projection_has_the_same_output_instruction(self) -> None:
        needle = "CRITICAL | IMPORTANT | SUGGESTION | UNSPECIFIED"
        for root in PROJECTIONS:
            assert needle in (root / "SKILL.md").read_text(encoding="utf-8"), root

    def test_aggregate_rules_are_unchanged(self) -> None:
        text = SKILL.read_text(encoding="utf-8")
        assert "any token in `FAIL_VERDICTS`" in text
        assert "-> `CRITICAL_FAIL`; any `WARN` or `PARTIAL` -> `WARN`; any `UNKNOWN`" in text
        assert "UNKNOWN does NOT override real findings" in text
        assert "Flagged notes (not counted)" in text

    def test_resource_has_no_dashes(self, resource_text: str) -> None:
        assert chr(0x2014) not in resource_text
        assert chr(0x2013) not in resource_text
