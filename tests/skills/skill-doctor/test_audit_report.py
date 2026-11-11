#!/usr/bin/env python3
"""Tests for the audit sections of the HTML report and the public export."""

import copy
import json
import re
from pathlib import Path
from typing import Any

import public_export
import pytest
import render_report
import report_audit

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "audit"
GENERATED_AT = re.compile(r"Generated [^<]*<")


def load(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return data


def normalized_html(report: dict[str, Any]) -> str:
    return GENERATED_AT.sub("Generated <", render_report.render_page(report))


def write_report(tmp_path: Path, report: dict[str, Any]) -> Path:
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    return path


class TestHtmlReachability:
    def test_every_definition_hash_and_alias_is_in_the_html(self) -> None:
        report = load("report.json")
        page = render_report.render_page(report)

        for definition in report["audit"]["catalog"]["definitions"]:
            assert definition["sha256"] in page
            assert definition["path"] in page
            for alias in definition["aliases"]:
                assert alias in page

    def test_every_record_and_accepted_score_is_in_the_html(self) -> None:
        report = load("report.json")
        page = render_report.render_page(report)

        for record in report["audit"]["records"]:
            assert record["session_id"] in page
            for result in record["scores"].values():
                assert result["reason"] in page
                assert result["evidence_ref"] in page
                assert result["label"] in page

    def test_applicability_and_fallback_are_shown(self) -> None:
        page = render_report.render_page(load("report.json"))

        assert "not applicable" in page
        assert "insufficient_evidence" in page

    def test_zero_applicability_shows_fallback_basis(self) -> None:
        report = load("report.json")
        dim = report["audit"]["scores"]["dimensions"]["code_quality"]
        dim.update(denominator=0, fallback_used=True)
        report["audit"]["scores"]["evidence_limits"] = ["raw 0.5 is a neutral fallback"]

        page = render_report.render_page(report)

        assert ">fallback<" in page
        assert "neutral fallback" in page

    def test_existing_sections_are_preserved(self) -> None:
        page = render_report.render_page(load("report.json"))

        for marker in ("Sampling", "Findings", "Evaluation status", "Suggested skill changes"):
            assert marker in page
        assert "skillopt handoff prompt" in page
        assert 'data-status="unevaluated"' in page


class TestCountsAndTotals:
    def test_html_counts_match_json(self) -> None:
        report = load("report.json")
        page = render_report.render_page(report)
        counts = report_audit.catalog_counts(report["audit"])

        assert counts == {"definitions": 3, "aliases": 1, "conflicts": 1}
        assert 'data-definitions="3" data-aliases="1" data-conflicts="1"' in page
        assert 'data-records="4"' in page
        assert 'data-sessions="4"' in page

    def test_html_totals_match_artifact(self) -> None:
        report = load("report.json")
        page = render_report.render_page(report)
        total = report["audit"]["scores"]["total_shortfall"]

        assert f"total weighted shortfall {total:.4f} points" in page
        shortfalls = [
            d["weighted_shortfall"] for d in report["audit"]["scores"]["dimensions"].values()
        ]
        assert sum(shortfalls) == pytest.approx(total, abs=1e-9)

    def test_valid_report_has_no_audit_errors(self) -> None:
        assert report_audit.validate_audit(load("report.json")) == []

    @pytest.mark.parametrize("key", ["efficiency", "skill_coverage", "overall"])
    def test_scorecard_mismatch_is_an_error(self, key: str) -> None:
        report = load("report.json")
        report["scores"][key] += 1e-6

        errors = report_audit.validate_audit(report)

        assert any(key in e for e in errors)

    def test_difference_inside_tolerance_is_accepted(self) -> None:
        report = load("report.json")
        report["scores"]["overall"] += 1e-12

        assert report_audit.validate_audit(report) == []

    def test_record_count_mismatch_is_an_error(self) -> None:
        report = load("report.json")
        report["audit"]["records"].pop()

        assert any("records" in e for e in report_audit.validate_audit(report))

    def test_stats_count_mismatch_is_an_error(self) -> None:
        report = load("report.json")
        report["stats"]["sessions_analyzed"] = 99

        assert any("sessions_analyzed" in e for e in report_audit.validate_audit(report))

    def test_missing_dimension_is_an_error(self) -> None:
        report = load("report.json")
        del report["audit"]["scores"]["dimensions"]["verbosity"]

        assert any("verbosity" in e for e in report_audit.validate_audit(report))

    def test_cli_exits_1_on_mismatch_and_writes_no_html(self, tmp_path: Path) -> None:
        report = load("report.json")
        report["scores"]["overall"] = 0.5
        path = write_report(tmp_path, report)

        with pytest.raises(SystemExit) as exc:
            render_report.main([str(path)])

        assert exc.value.code == 1
        assert not (tmp_path / "report.html").exists()

    def test_cli_exits_0_and_writes_html_when_consistent(self, tmp_path: Path) -> None:
        path = write_report(tmp_path, load("report.json"))

        render_report.main([str(path)])

        assert "Audit evidence" in (tmp_path / "report.html").read_text(encoding="utf-8")


class TestInertRendering:
    def test_injection_fixture_has_no_live_markup(self) -> None:
        page = render_report.render_page(load("report_injection.json"))

        assert "<script>alert" not in page
        assert "</script><script>alert" not in page
        assert "<img src=x onerror" not in page
        assert "&lt;/script&gt;&lt;script&gt;alert(1)&lt;/script&gt;" in page
        assert "&lt;img src=x onerror=alert(2)&gt;" in page

    def test_injection_page_has_only_the_two_expected_scripts(self) -> None:
        page = render_report.render_page(load("report_injection.json"))

        assert page.count("<script>") == 2
        assert "onerror=" not in page.replace("onerror=alert(2)&gt;", "")

    def test_esc_is_used_for_names_and_aliases(self) -> None:
        report = load("report_injection.json")
        rendered = report_audit.render_catalog(report["audit"], render_report.esc)

        assert "<script>" not in rendered
        assert "<img" not in rendered


class TestOldReportsUnchanged:
    def test_report_without_audit_renders_no_audit_section(self) -> None:
        report = load("report.json")
        del report["audit"]

        page = render_report.render_page(report)

        assert "Audit evidence" not in page
        assert report_audit.validate_audit(report) == []
        assert report_audit.render_audit(report, render_report.esc) == ""

    def test_partial_audit_renders_only_present_parts(self) -> None:
        report = load("report.json")
        report["audit"] = {"catalog": report["audit"]["catalog"]}

        page = render_report.render_page(report)

        assert "Skill catalog" in page
        assert "Score artifact" not in page
        assert "Per-conversation evidence" not in page

    def test_catalog_accepts_a_bare_list(self) -> None:
        defs = load("report.json")["audit"]["catalog"]["definitions"]

        assert report_audit.catalog_counts({"catalog": defs}) == {
            "definitions": 3,
            "aliases": 1,
            "conflicts": 1,
        }

    def test_catalog_with_bad_shape_counts_zero(self) -> None:
        assert report_audit.catalog_counts({"catalog": "nope"}) == {
            "definitions": 0,
            "aliases": 0,
            "conflicts": 0,
        }


class TestReproducible:
    def test_rendering_twice_gives_identical_normalized_html(self) -> None:
        first = normalized_html(load("report.json"))
        second = normalized_html(load("report.json"))

        assert first == second

    def test_timestamp_is_the_only_allowed_difference(self) -> None:
        a = load("report.json")
        b = copy.deepcopy(a)
        b["generated_at"] = "2027-01-01T00:00:00Z"

        assert render_report.render_page(a) != render_report.render_page(b)
        assert normalized_html(a) == normalized_html(b)

    def test_fixtures_are_synthetic_and_offline(self) -> None:
        for name in ("report.json", "report_injection.json"):
            text = (FIXTURES / name).read_text(encoding="utf-8")
            assert "http://" not in text and "https://" not in text
            assert "CANARY-" in text


class TestPublicExport:
    def test_export_contains_zero_seeded_canaries(self) -> None:
        for name in ("report.json", "report_injection.json"):
            export = json.dumps(public_export.export_public(load(name)))

            assert "CANARY" not in export
            assert "alert(" not in export

    def test_export_carries_the_allowlisted_aggregates(self) -> None:
        report = load("report.json")

        export = public_export.export_public(report)

        assert export["grade"] == "C"
        assert export["overall"] == pytest.approx(report["scores"]["overall"])
        assert set(export["scores"]) == {
            "efficiency",
            "code_quality",
            "procedure_compliance",
            "verbosity",
            "skill_coverage",
        }
        assert export["weighted_shortfall"]["total"] == pytest.approx(
            report["audit"]["scores"]["total_shortfall"]
        )
        assert set(export["weighted_shortfall"]["by_dimension"]) == set(export["scores"])
        assert export["counts"] == {
            "sessions_scored": 4,
            "skills_found": 3,
            "skills_used": 2,
            "catalog": {"definitions": 3, "aliases": 1, "conflicts": 1},
        }
        assert export["suggestion_status_counts"]["unevaluated"] == 1
        assert "Static triage only" in export["evaluation_status"]
        assert "Non-probability" in export["sampling_note"]

    def test_export_keys_are_exactly_the_allowlist(self) -> None:
        export = public_export.export_public(load("report.json"))

        assert set(export) == {
            "grade",
            "overall",
            "scores",
            "weighted_shortfall",
            "counts",
            "evaluation_status",
            "suggestion_status_counts",
            "sampling_note",
        }

    def test_report_without_audit_still_exports(self) -> None:
        report = load("report.json")
        del report["audit"]

        export = public_export.export_public(report)

        assert export["weighted_shortfall"] == {}
        assert "catalog" not in export["counts"]

    def test_forced_session_canary_in_grade_is_refused(self) -> None:
        report = load("report.json")
        report["grade"] = report["audit"]["records"][0]["session_id"]

        with pytest.raises(public_export.CanaryError):
            public_export.export_public(report)

    def test_forced_substring_canary_in_grade_is_refused(self) -> None:
        report = load("report.json")
        reason = report["audit"]["records"][0]["scores"]["efficiency"]["reason"]
        report["grade"] = f"B {reason} B"

        with pytest.raises(public_export.CanaryError):
            public_export.export_public(report)

    def test_forced_path_canary_in_status_counts_key_is_refused(self) -> None:
        deny = {"CANARY-PATH-ONE/x"}

        assert public_export.find_canaries({"CANARY-PATH-ONE/x": 1}, deny) == ["CANARY-PATH-ONE/x"]

    def test_short_values_match_only_exactly(self) -> None:
        assert public_export.find_canaries({"a": "abc def"}, {"abc"}) == []
        assert public_export.find_canaries({"a": "abc"}, {"abc"}) == ["abc"]

    def test_deny_set_covers_private_fields_and_prompts(self) -> None:
        report = load("report.json")

        deny = public_export.deny_set(report)

        assert "CANARY-HANDLE-ONE" in deny
        assert "/CANARY-PATH-ONE/alpha/SKILL.md" in deny
        assert "a" * 64 in deny
        assert any("CANARY-CHANGE-ONE" in value for value in deny)
        assert any(value.startswith("CANARY-SESSION-ONE") for value in deny)


class TestPublicExportCli:
    def test_exit_0_writes_clean_json(self, tmp_path: Path) -> None:
        source = write_report(tmp_path, load("report.json"))
        out = tmp_path / "public.json"

        code = public_export.main([str(source), "--out", str(out)])

        assert code == 0
        text = out.read_text(encoding="utf-8")
        assert "CANARY" not in text
        assert json.loads(text)["grade"] == "C"

    def test_exit_1_on_canary_and_no_file_written(self, tmp_path: Path) -> None:
        report = load("report.json")
        report["grade"] = report["audit"]["records"][0]["session_id"]
        source = write_report(tmp_path, report)
        out = tmp_path / "public.json"

        code = public_export.main([str(source), "--out", str(out)])

        assert code == 1
        assert not out.exists()

    def test_exit_2_on_missing_out_argument(self, tmp_path: Path) -> None:
        with pytest.raises(SystemExit) as exc:
            public_export.main([str(tmp_path / "report.json")])

        assert exc.value.code == 2

    def test_exit_2_on_unreadable_report(self, tmp_path: Path) -> None:
        code = public_export.main([str(tmp_path / "missing.json"), "--out", str(tmp_path / "o")])

        assert code == 2

    def test_exit_2_on_invalid_json(self, tmp_path: Path) -> None:
        bad = tmp_path / "report.json"
        bad.write_text("{not json", encoding="utf-8")

        assert public_export.main([str(bad), "--out", str(tmp_path / "o")]) == 2

    def test_exit_2_on_non_object_json(self, tmp_path: Path) -> None:
        bad = tmp_path / "report.json"
        bad.write_text("[1]", encoding="utf-8")

        assert public_export.main([str(bad), "--out", str(tmp_path / "o")]) == 2

    def test_exit_2_when_output_is_unwritable(self, tmp_path: Path) -> None:
        source = write_report(tmp_path, load("report.json"))

        code = public_export.main([str(source), "--out", str(tmp_path / "no" / "dir" / "o.json")])

        assert code == 2
