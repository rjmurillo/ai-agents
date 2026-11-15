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

import json
import re
import sys
from collections.abc import Mapping
from pathlib import Path

import pytest
from ai_review_common.verdict import adapt_local_axis_verdict, merge_verdicts

PROJECT_ROOT = Path(__file__).resolve().parents[3]
_TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if _TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script

doc_accuracy = import_skill_script(
    ".claude/skills/doc-accuracy/scripts/doc_accuracy.py",
    module_name="severity_contract_doc_accuracy",
)
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

GOLDEN_SCANNER = (
    PROJECT_ROOT / ".claude" / "skills" / "golden-principles" / "scripts" / "scan_principles.py"
)
TASTE_SCANNER = PROJECT_ROOT / ".claude" / "skills" / "taste-lints" / "scripts" / "taste_lints.py"
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

    def test_only_critical_and_high_axis_tokens_are_above_suggestion(
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


class TestEveryProjectionIsListed:
    """The converse of the loops above: a tree on disk must be in PROJECTIONS."""

    def test_on_disk_review_trees_equal_the_projection_set(self) -> None:
        on_disk = {path for path in (PROJECT_ROOT / "src").glob("*/skills/review") if path.is_dir()}
        assert on_disk == set(PROJECTIONS), (
            "src/*/skills/review trees and PROJECTIONS differ: "
            f"unlisted {sorted(map(str, on_disk - set(PROJECTIONS)))}, "
            f"missing {sorted(map(str, set(PROJECTIONS) - on_disk))}"
        )


def _scanner_json(error_count: int, warning_count: int, axis: str) -> str:
    """A scanner payload that passes every guard in adapt_local_axis_verdict."""
    payload: dict[str, object] = {
        "files_scanned": 1,
        "error_count": error_count,
        "warning_count": warning_count,
        "violations": [],
    }
    if axis == "golden-principles":
        payload["applicable_files"] = 1
    else:
        payload["files_by_category"] = {"authored": 1, "test": 0, "generated": 0}
    return json.dumps(payload)


class TestScannerSeverityRows:
    """Thread on local scanners: `error` and `warning` carry real per-item values."""

    def test_scanners_emit_only_error_and_warning(self) -> None:
        for scanner in (GOLDEN_SCANNER, TASTE_SCANNER):
            values = set(re.findall(r'severity="([^"]+)"', scanner.read_text(encoding="utf-8")))
            assert values == {"error", "warning"}, scanner

    def test_scanner_values_have_rows(self, table: dict[str, str]) -> None:
        assert table["error"] == "CRITICAL"
        assert table["warning"] == "IMPORTANT"

    def test_scanner_error_and_warning_render_distinct_labels(
        self, table: dict[str, str], fallback: str
    ) -> None:
        findings = [{"severity": "error"}, {"severity": "warning"}]
        assert [render(f, table, fallback) for f in findings] == ["CRITICAL", "IMPORTANT"]

    @pytest.mark.parametrize("value", ["ERROR", "Warning", " error "])
    def test_scanner_values_match_case_and_space_insensitively(
        self, value: str, table: dict[str, str], fallback: str
    ) -> None:
        assert render({"severity": value}, table, fallback) in {"CRITICAL", "IMPORTANT"}

    @pytest.mark.parametrize("value", ["info", "fatal", "warn"])
    def test_other_scanner_values_stay_unspecified(
        self, value: str, table: dict[str, str], fallback: str
    ) -> None:
        assert render({"severity": value}, table, fallback) == UNSPECIFIED

    @pytest.mark.parametrize("axis", ["golden-principles", "taste-lints"])
    def test_error_label_matches_its_effect_on_the_verdict(self, axis: str) -> None:
        """CRITICAL only when the value can fail the merged review."""
        local = adapt_local_axis_verdict(axis, _scanner_json(1, 0, axis), 10)
        assert local == "FAIL"
        assert merge_verdicts([local]) == "CRITICAL_FAIL"

    @pytest.mark.parametrize("axis", ["golden-principles", "taste-lints"])
    def test_warning_label_matches_its_effect_on_the_verdict(self, axis: str) -> None:
        """IMPORTANT, not CRITICAL: a warning alone only reaches WARN."""
        local = adapt_local_axis_verdict(axis, _scanner_json(0, 2, axis), 0)
        assert local == "WARN"
        assert merge_verdicts([local]) == "WARN"

    @pytest.mark.parametrize("axis", ["golden-principles", "taste-lints"])
    def test_a_warning_beside_an_error_does_not_change_the_error_label(
        self, axis: str, table: dict[str, str], fallback: str
    ) -> None:
        assert adapt_local_axis_verdict(axis, _scanner_json(1, 3, axis), 10) == "FAIL"
        findings = [{"severity": "error"}, {"severity": "warning"}]
        assert [render(f, table, fallback) for f in findings] == ["CRITICAL", "IMPORTANT"]

    def test_resource_documents_the_scanner_rule(self, resource_text: str) -> None:
        assert "## Local scanner values" in resource_text
        assert "`golden-principles` and `taste-lints`" in resource_text
        assert "A local axis with a section above takes its labels from that section" in (
            resource_text
        )

    def test_rules_name_every_value_that_can_move_the_verdict(self, resource_text: str) -> None:
        assert (
            "`critical`, `blocking`, scanner `error`, and a `doc-accuracy` finding at or above "
            "the gate threshold can fail the axis." in resource_text
        )
        assert "`high`, `non-blocking`, and scanner `warning` can make it `WARN`." in resource_text
        assert "Only `critical` and `high` move it" not in resource_text
        assert "the axis's own value" not in resource_text


# Gate severities from least to most severe is the reverse of this order.
_GATE_ORDER = ["critical", "high", "medium", "low"]


def doc_accuracy_label(severity: str, threshold: str, table: dict[str, str]) -> str:
    """Apply the resource's doc-accuracy rule: at or above the threshold is CRITICAL."""
    if severity not in _GATE_ORDER:
        return UNSPECIFIED
    if _GATE_ORDER.index(severity) <= _GATE_ORDER.index(threshold):
        return "CRITICAL"
    return table[severity]


def _gate(severity: str, threshold: str) -> dict[str, object]:
    return doc_accuracy.check_gate({"findings": [{"severity": severity}]}, threshold)


class TestDocAccuracyValues:
    """Thread on gate findings: a label must match what the value does to the gate."""

    @pytest.mark.parametrize("threshold", _GATE_ORDER)
    @pytest.mark.parametrize("severity", [*_GATE_ORDER, "info"])
    def test_critical_label_appears_exactly_when_the_finding_fails_the_gate(
        self, severity: str, threshold: str, table: dict[str, str]
    ) -> None:
        fails = _gate(severity, threshold)["verdict"] == "FAIL"
        label = doc_accuracy_label(severity, threshold, table)
        assert (label == "CRITICAL") is fails, (severity, threshold, label)

    def test_default_threshold_fails_on_critical_and_high_only(self) -> None:
        failing = {s for s in [*_GATE_ORDER, "info"] if _gate(s, "high")["verdict"] == "FAIL"}
        assert failing == {"critical", "high"}

    def test_review_runs_the_gate_without_a_threshold_override(self) -> None:
        text = SKILL.read_text(encoding="utf-8")
        line = next(ln for ln in text.splitlines() if ln.startswith("- local axis 2:"))
        assert "--format gate" in line
        assert "--severity-threshold" not in line

    def test_a_high_finding_fails_the_merged_review(self) -> None:
        payload = json.dumps(
            {
                "gate_result": _gate("high", "high"),
                "assessment": {"documentation_files": [{"path": "a.md"}], "changed_files": []},
            }
        )
        local = adapt_local_axis_verdict("doc-accuracy", payload, 10)
        assert local == "FAIL"
        assert merge_verdicts([local]) == "CRITICAL_FAIL"

    def test_a_medium_finding_passes_the_gate_and_stays_a_suggestion(
        self, table: dict[str, str]
    ) -> None:
        gate = _gate("medium", "high")
        assert gate["verdict"] == "PASS"
        assert doc_accuracy_label("medium", "high", table) == "SUGGESTION"

    def test_info_is_unspecified_and_never_blocks(self, table: dict[str, str]) -> None:
        assert _gate("info", "low")["verdict"] == "PASS"
        assert doc_accuracy_label("info", "high", table) == UNSPECIFIED

    def test_resource_documents_the_doc_accuracy_rule(self, resource_text: str) -> None:
        assert "## Doc-accuracy values" in resource_text
        assert "A finding at or above `gate_result.threshold`" in resource_text
        assert "`critical` and `high` render CRITICAL" in resource_text
        assert "`medium` and `low` render SUGGESTION" in resource_text
        assert "`info` marks a finding outside the diff" in resource_text

    def test_local_axis_without_a_section_stays_unspecified(self, resource_text: str) -> None:
        assert "`code-qualities-assessment`" in resource_text
        assert "A local finding with a value the tables list takes that label" not in resource_text
