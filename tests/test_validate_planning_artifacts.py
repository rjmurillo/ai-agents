"""Tests for validate_planning_artifacts module.

Validates planning artifact consistency checks including estimate extraction,
estimate divergence, orphan condition detection, and document discovery.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Add build/scripts to path for imports
_BUILD_SCRIPTS = Path(__file__).resolve().parent.parent / "build" / "scripts"
sys.path.insert(0, str(_BUILD_SCRIPTS))

from validate_planning_artifacts import (  # noqa: E402
    Estimate,
    ValidationSummary,
    check_estimate_consistency,
    extract_estimate,
    find_orphan_conditions,
    find_planning_documents,
    main,
    validate_conditions,
    validate_estimates,
)


class TestExtractEstimate:
    """Tests for estimate extraction from text."""

    def test_range_hours(self) -> None:
        est = extract_estimate("**Effort**: 8-14 hours")
        assert est is not None
        assert est.low == 8.0
        assert est.high == 14.0

    def test_range_hrs(self) -> None:
        est = extract_estimate("Total: 10-12 hrs")
        assert est is not None
        assert est.low == 10.0
        assert est.high == 12.0

    def test_single_hours(self) -> None:
        est = extract_estimate("**Effort**: 5 hours")
        assert est is not None
        assert est.low == 5.0
        assert est.high == 5.0

    def test_single_h(self) -> None:
        est = extract_estimate("Task: 3h")
        assert est is not None
        assert est.low == 3.0
        assert est.high == 3.0

    def test_decimal_estimates(self) -> None:
        est = extract_estimate("Effort: 2.5-4.5 hours")
        assert est is not None
        assert est.low == 2.5
        assert est.high == 4.5

    def test_no_estimate_returns_none(self) -> None:
        assert extract_estimate("No estimates here") is None

    def test_range_preferred_over_single(self) -> None:
        est = extract_estimate("Effort: 8-14 hours, about 10h typical")
        assert est is not None
        assert est.low == 8.0
        assert est.high == 14.0


class TestEstimateMidpoint:
    """Tests for the Estimate midpoint property."""

    def test_symmetric_range(self) -> None:
        est = Estimate(low=8.0, high=12.0)
        assert est.midpoint == 10.0

    def test_single_value(self) -> None:
        est = Estimate(low=5.0, high=5.0)
        assert est.midpoint == 5.0


class TestCheckEstimateConsistency:
    """Tests for estimate consistency comparison."""

    def test_within_threshold(self) -> None:
        source = Estimate(low=10.0, high=12.0)
        derived = Estimate(low=10.0, high=14.0)
        result = check_estimate_consistency(source, derived, 20)
        assert result.consistent is True

    def test_exceeds_threshold(self) -> None:
        source = Estimate(low=8.0, high=14.0)
        derived = Estimate(low=12.0, high=16.0)
        result = check_estimate_consistency(source, derived, 20)
        assert result.consistent is False
        assert result.divergence > 20

    def test_custom_threshold(self) -> None:
        source = Estimate(low=10.0, high=10.0)
        derived = Estimate(low=11.0, high=11.0)
        result = check_estimate_consistency(source, derived, 5)
        assert result.consistent is False

    def test_none_source_is_consistent(self) -> None:
        derived = Estimate(low=5.0, high=10.0)
        result = check_estimate_consistency(None, derived, 20)
        assert result.consistent is True

    def test_none_derived_is_consistent(self) -> None:
        source = Estimate(low=5.0, high=10.0)
        result = check_estimate_consistency(source, None, 20)
        assert result.consistent is True

    def test_zero_source_midpoint(self) -> None:
        source = Estimate(low=0.0, high=0.0)
        derived = Estimate(low=5.0, high=10.0)
        result = check_estimate_consistency(source, derived, 20)
        assert result.consistent is True
        assert result.divergence == 0.0


class TestFindOrphanConditions:
    """Tests for orphan condition detection."""

    def test_no_orphans_when_conditions_in_table(self) -> None:
        content = (
            "| Task | Conditions |\n"
            "|------|------------|\n"
            "| Auth | Security: Use PKCE flow |\n"
            "| Test | QA: Needs test spec file |\n"
        )
        orphans = find_orphan_conditions(content)
        assert orphans == []

    def test_detects_orphan_conditions(self) -> None:
        content = (
            "## Conditions\n"
            "- QA: Needs test specification file\n"
            "- Security: Use PKCE for OAuth\n"
            "\n"
            "## Work Breakdown\n"
            "| Task ID | Description |\n"
            "|---------|-------------|\n"
            "| TASK-001 | Implement OAuth |\n"
        )
        orphans = find_orphan_conditions(content)
        assert len(orphans) == 2
        assert any("QA:" in o for o in orphans)
        assert any("Security:" in o for o in orphans)

    def test_detects_multiple_condition_types(self) -> None:
        content = (
            "## Specialist Conditions\n"
            "- QA: Add integration tests\n"
            "- Security: Encrypt at rest\n"
            "- DevOps: Add monitoring\n"
            "\n"
            "## Tasks\n"
            "| Task | Effort |\n"
            "|------|--------|\n"
            "| Build feature | 2h |\n"
        )
        orphans = find_orphan_conditions(content)
        assert len(orphans) >= 2

    def test_conditions_inside_table_not_orphaned(self) -> None:
        content = (
            "| Task ID | Description | Conditions |\n"
            "|---------|-------------|------------|\n"
            "| T-1 | Auth | Security: Use PKCE flow |\n"
        )
        orphans = find_orphan_conditions(content)
        assert orphans == []

    def test_empty_content(self) -> None:
        orphans = find_orphan_conditions("")
        assert orphans == []


class TestFindPlanningDocuments:
    """Tests for planning document discovery."""

    def test_finds_epic_by_feature_name(self, tmp_path: Path) -> None:
        planning = tmp_path / ".agents" / "planning"
        planning.mkdir(parents=True)
        (planning / "epic-myfeature.md").write_text("# Epic")
        docs = find_planning_documents(tmp_path, "myfeature")
        assert docs is not None
        assert docs.epic is not None
        assert "epic" in docs.epic.name.lower()

    def test_finds_task_by_feature_name(self, tmp_path: Path) -> None:
        planning = tmp_path / ".agents" / "planning"
        planning.mkdir(parents=True)
        (planning / "tasks-myfeature.md").write_text("# Tasks")
        docs = find_planning_documents(tmp_path, "myfeature")
        assert docs is not None
        assert docs.tasks is not None

    def test_finds_prd_by_feature_name(self, tmp_path: Path) -> None:
        planning = tmp_path / ".agents" / "planning"
        planning.mkdir(parents=True)
        (planning / "prd-myfeature.md").write_text("# PRD")
        docs = find_planning_documents(tmp_path, "myfeature")
        assert docs is not None
        assert docs.prd is not None

    def test_finds_plan_by_feature_name(self, tmp_path: Path) -> None:
        planning = tmp_path / ".agents" / "planning"
        planning.mkdir(parents=True)
        (planning / "plan-myfeature.md").write_text("# Plan")
        docs = find_planning_documents(tmp_path, "myfeature")
        assert docs is not None
        assert docs.plan is not None

    def test_finds_by_prefix_no_feature(self, tmp_path: Path) -> None:
        planning = tmp_path / ".agents" / "planning"
        planning.mkdir(parents=True)
        (planning / "epic-something.md").write_text("# Epic")
        (planning / "tasks-something.md").write_text("# Tasks")
        docs = find_planning_documents(tmp_path, "")
        assert docs is not None
        assert docs.epic is not None
        assert docs.tasks is not None

    def test_returns_none_when_no_planning_dir(self, tmp_path: Path) -> None:
        docs = find_planning_documents(tmp_path, "feature")
        assert docs is None

    def test_fallback_to_first_doc_as_plan(self, tmp_path: Path) -> None:
        planning = tmp_path / ".agents" / "planning"
        planning.mkdir(parents=True)
        (planning / "random-doc.md").write_text("# Doc")
        docs = find_planning_documents(tmp_path, "")
        assert docs is not None
        assert docs.plan is not None

    def test_empty_planning_dir(self, tmp_path: Path) -> None:
        planning = tmp_path / ".agents" / "planning"
        planning.mkdir(parents=True)
        docs = find_planning_documents(tmp_path, "feature")
        assert docs is not None
        assert docs.all_docs == []

    def test_all_docs_populated(self, tmp_path: Path) -> None:
        planning = tmp_path / ".agents" / "planning"
        planning.mkdir(parents=True)
        (planning / "doc1.md").write_text("# Doc 1")
        (planning / "doc2.md").write_text("# Doc 2")
        docs = find_planning_documents(tmp_path, "")
        assert docs is not None
        assert len(docs.all_docs) == 2


class TestValidateEstimates:
    """Tests for the validate_estimates function."""

    def test_pass_within_threshold(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        planning = tmp_path / ".agents" / "planning"
        planning.mkdir(parents=True)
        (planning / "epic-feat.md").write_text("**Effort**: 10-12 hours")
        (planning / "tasks-feat.md").write_text("**Total Effort**: 10-14 hours")

        docs = find_planning_documents(tmp_path, "feat")
        assert docs is not None
        summary = ValidationSummary()
        validate_estimates(docs, 20, summary)
        captured = capsys.readouterr()
        assert "[PASS]" in captured.out
        assert summary.warnings == []

    def test_warn_exceeds_threshold(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        planning = tmp_path / ".agents" / "planning"
        planning.mkdir(parents=True)
        (planning / "epic-feat.md").write_text("**Effort**: 8-14 hours")
        (planning / "tasks-feat.md").write_text("**Total Effort**: 12-16 hours")

        docs = find_planning_documents(tmp_path, "feat")
        assert docs is not None
        summary = ValidationSummary()
        validate_estimates(docs, 20, summary)
        captured = capsys.readouterr()
        assert "[WARN]" in captured.out
        assert len(summary.warnings) == 1


class TestValidateConditions:
    """Tests for the validate_conditions function."""

    def test_pass_no_orphans(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        planning = tmp_path / ".agents" / "planning"
        planning.mkdir(parents=True)
        (planning / "plan-feat.md").write_text(
            "| Task | Conditions |\n"
            "|------|------------|\n"
            "| Auth | Security: Use PKCE flow |\n"
        )
        docs = find_planning_documents(tmp_path, "feat")
        assert docs is not None
        summary = ValidationSummary()
        validate_conditions(docs, summary)
        captured = capsys.readouterr()
        assert "[PASS]" in captured.out
        assert summary.errors == []

    def test_fail_with_orphans(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        planning = tmp_path / ".agents" / "planning"
        planning.mkdir(parents=True)
        (planning / "plan-feat.md").write_text(
            "## Conditions\n"
            "- QA: Needs test spec\n"
            "\n"
            "## Tasks\n"
            "| Task |\n"
            "|------|\n"
            "| Work |\n"
        )
        docs = find_planning_documents(tmp_path, "feat")
        assert docs is not None
        summary = ValidationSummary()
        validate_conditions(docs, summary)
        captured = capsys.readouterr()
        assert "[FAIL]" in captured.out
        assert len(summary.errors) == 1


class TestMain:
    """Tests for the main entry point."""

    def test_returns_0_no_planning_dir(self, tmp_path: Path) -> None:
        result = main(["--path", str(tmp_path)])
        assert result == 0

    def test_returns_0_empty_planning_dir(self, tmp_path: Path) -> None:
        (tmp_path / ".agents" / "planning").mkdir(parents=True)
        result = main(["--path", str(tmp_path)])
        assert result == 0

    def test_returns_0_clean_plan(self, tmp_path: Path) -> None:
        planning = tmp_path / ".agents" / "planning"
        planning.mkdir(parents=True)
        (planning / "plan-clean.md").write_text(
            "# Plan\n\n"
            "| Task | Effort |\n"
            "|------|--------|\n"
            "| Task 1 | 2h |\n"
        )
        result = main(["--path", str(tmp_path)])
        assert result == 0

    def test_returns_0_warnings_without_fail_flag(self, tmp_path: Path) -> None:
        planning = tmp_path / ".agents" / "planning"
        planning.mkdir(parents=True)
        (planning / "epic-warn.md").write_text("**Effort**: 5-5 hours")
        (planning / "tasks-warn.md").write_text("**Effort**: 10-10 hours")
        result = main(["--path", str(tmp_path), "--feature-name", "warn"])
        assert result == 0

    def test_returns_1_warnings_with_fail_on_warning(self, tmp_path: Path) -> None:
        planning = tmp_path / ".agents" / "planning"
        planning.mkdir(parents=True)
        (planning / "epic-warn.md").write_text("**Effort**: 5-5 hours")
        (planning / "tasks-warn.md").write_text("**Effort**: 10-10 hours")
        result = main([
            "--path", str(tmp_path),
            "--feature-name", "warn",
            "--fail-on-warning",
        ])
        assert result == 1

    def test_returns_1_errors_with_fail_on_error(self, tmp_path: Path) -> None:
        planning = tmp_path / ".agents" / "planning"
        planning.mkdir(parents=True)
        (planning / "plan-err.md").write_text(
            "## Conditions\n"
            "- QA: Orphan condition\n"
            "\n"
            "## Tasks\n"
            "| Task | Effort |\n"
            "|------|--------|\n"
            "| Task 1 | 2h |\n"
        )
        result = main(["--path", str(tmp_path), "--fail-on-error"])
        assert result == 1

    def test_returns_0_errors_without_fail_flag(self, tmp_path: Path) -> None:
        planning = tmp_path / ".agents" / "planning"
        planning.mkdir(parents=True)
        (planning / "plan-err.md").write_text(
            "## Conditions\n"
            "- QA: Orphan condition\n"
            "\n"
            "## Tasks\n"
            "| Task |\n"
            "|------|\n"
            "| Work |\n"
        )
        result = main(["--path", str(tmp_path)])
        assert result == 0

    def test_custom_threshold(self, tmp_path: Path) -> None:
        planning = tmp_path / ".agents" / "planning"
        planning.mkdir(parents=True)
        (planning / "epic-ct.md").write_text("**Effort**: 10-10 hours")
        (planning / "tasks-ct.md").write_text("**Effort**: 11-11 hours")
        result = main([
            "--path", str(tmp_path),
            "--feature-name", "ct",
            "--estimate-threshold", "5",
            "--fail-on-warning",
        ])
        assert result == 1

    def test_output_shows_document_count(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        planning = tmp_path / ".agents" / "planning"
        planning.mkdir(parents=True)
        (planning / "doc1.md").write_text("# Doc 1")
        (planning / "doc2.md").write_text("# Doc 2")
        main(["--path", str(tmp_path)])
        captured = capsys.readouterr()
        assert "Found 2 planning document(s)" in captured.out

    def test_output_shows_no_docs_message(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        (tmp_path / ".agents" / "planning").mkdir(parents=True)
        main(["--path", str(tmp_path)])
        captured = capsys.readouterr()
        assert "No planning documents found" in captured.out

    def test_output_shows_remediation_for_orphans(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        planning = tmp_path / ".agents" / "planning"
        planning.mkdir(parents=True)
        (planning / "plan-rem.md").write_text(
            "## Conditions\n"
            "- QA: Add test\n"
            "\n"
            "## Tasks\n"
            "| Task |\n"
            "|------|\n"
            "| Work |\n"
        )
        main(["--path", str(tmp_path)])
        captured = capsys.readouterr()
        assert "Remediation" in captured.out
        assert "Conditions" in captured.out

    def test_help_flag(self) -> None:
        with pytest.raises(SystemExit) as exc_info:
            main(["--help"])
        assert exc_info.value.code == 0
