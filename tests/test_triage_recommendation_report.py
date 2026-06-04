"""Tests for scripts.triage_recommendation_report.

Covers the Phase 3 recommendation aggregator (issue #2261): the action-policy
mapping from a triaged result to recommended actions, manifest construction,
markdown rendering grouped by category, and the CLI entry point including the
missing-dir and count-mismatch edge cases.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.backlog_triage_summary import (
    DependencyDetection,
    EvidenceCheck,
    ScopeAssessment,
    TriageResult,
)
from scripts.triage_recommendation_report import (
    ACTION_BATCH,
    ACTION_CLOSE,
    ACTION_DECOMPOSE,
    ACTION_PRIORITIZE,
    ACTION_RELABEL,
    RecommendedAction,
    build_manifest,
    main,
    recommend_actions,
    render_report,
)


def _result(
    *,
    number: int = 1,
    title: str = "t",
    verdict: str = "PASS",
    labels: tuple[str, ...] = (),
    area_routing: tuple[str, ...] = (),
    scope_assessment: ScopeAssessment | None = None,
) -> TriageResult:
    return TriageResult(
        number=number,
        title=title,
        verdict=verdict,
        labels=labels,
        area_routing=area_routing,
        dependency_detection=DependencyDetection(),
        scope_assessment=scope_assessment or ScopeAssessment(),
        evidence_check=EvidenceCheck(),
        findings="",
    )


def _write_result(directory: Path, name: str, payload: dict | str) -> Path:
    path = directory / name
    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
    else:
        path.write_text(json.dumps(payload), encoding="utf-8")
    return path


class TestRecommendActions:
    def test_close_verdict_yields_close_action(self):
        actions = recommend_actions(_result(number=5, verdict="STALE"))
        expected = RecommendedAction(
            issue=5,
            category=ACTION_CLOSE,
            rationale="verdict STALE",
        )
        assert expected in actions

    def test_pass_verdict_yields_no_close(self):
        actions = recommend_actions(_result(number=5, verdict="PASS"))
        assert all(a.category != ACTION_CLOSE for a in actions)

    def test_area_routing_yields_relabel_action(self):
        actions = recommend_actions(
            _result(number=7, area_routing=("agent-implementer", "agent-qa")),
        )
        relabel = [a for a in actions if a.category == ACTION_RELABEL]
        assert len(relabel) == 1
        assert relabel[0].labels == ("agent-implementer", "agent-qa")

    def test_priority_label_yields_prioritize_action(self):
        actions = recommend_actions(_result(number=8, labels=("priority:P1",)))
        prioritize = [a for a in actions if a.category == ACTION_PRIORITIZE]
        assert len(prioritize) == 1
        assert prioritize[0].priority == "P1"

    def test_needs_decomposition_yields_decompose_action(self):
        actions = recommend_actions(
            _result(
                number=9,
                scope_assessment=ScopeAssessment(
                    status="too_broad", needs_decomposition=True, notes="split it",
                ),
            ),
        )
        decompose = [a for a in actions if a.category == ACTION_DECOMPOSE]
        assert len(decompose) == 1
        assert decompose[0].rationale == "split it"

    def test_can_batch_yields_batch_action(self):
        actions = recommend_actions(
            _result(number=10, scope_assessment=ScopeAssessment(can_batch=True)),
        )
        assert any(a.category == ACTION_BATCH for a in actions)

    def test_clean_result_yields_no_actions(self):
        assert recommend_actions(_result(number=11, verdict="PASS")) == []

    def test_non_priority_label_does_not_yield_prioritize(self):
        actions = recommend_actions(_result(number=12, labels=("bug",)))
        assert all(a.category != ACTION_PRIORITIZE for a in actions)


class TestBuildManifest:
    def test_manifest_is_unapproved_by_default(self):
        manifest = build_manifest([_result(number=1, verdict="STALE")])
        assert manifest["approved"] is False
        assert manifest["version"] == 1

    def test_manifest_aggregates_actions_across_issues(self):
        results = [
            _result(number=1, verdict="STALE"),
            _result(number=2, labels=("priority:P2",)),
        ]
        manifest = build_manifest(results)
        assert manifest["issues_triaged"] == 2
        categories = {a["category"] for a in manifest["actions"]}
        assert categories == {ACTION_CLOSE, ACTION_PRIORITIZE}

    def test_empty_results_yield_empty_actions(self):
        manifest = build_manifest([])
        assert manifest["actions"] == []
        assert manifest["issues_triaged"] == 0

    def test_relabel_entry_carries_labels_list(self):
        manifest = build_manifest([_result(number=3, area_routing=("agent-qa",))])
        relabel = next(a for a in manifest["actions"] if a["category"] == ACTION_RELABEL)
        assert relabel["labels"] == ["agent-qa"]


class TestRenderReport:
    def test_empty_state_message(self):
        text = render_report([])
        assert "No actions recommended" in text
        assert "Backlog Triage Recommendations" in text

    def test_groups_by_category(self):
        results = [
            _result(number=1, verdict="DUPLICATE"),
            _result(number=2, area_routing=("agent-architect",)),
        ]
        text = render_report(results)
        assert f"### {ACTION_CLOSE} (1)" in text
        assert f"### {ACTION_RELABEL} (1)" in text
        assert "- #1 - verdict DUPLICATE" in text
        assert "- #2 [agent-architect] - suggested area routing" in text

    def test_newline_in_rationale_collapsed(self):
        results = [
            _result(
                number=3,
                scope_assessment=ScopeAssessment(needs_decomposition=True, notes="a\nb"),
            ),
        ]
        text = render_report(results)
        assert "a b" in text
        assert "a\nb" not in text


class TestMain:
    def test_writes_manifest_and_report(self, tmp_path: Path, capsys):
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        _write_result(
            results_dir, "r.json",
            {"number": 1, "title": "t", "verdict": "STALE"},
        )
        manifest_path = tmp_path / "manifest.json"
        report_path = tmp_path / "report.md"
        rc = main([
            "--results-dir", str(results_dir),
            "--manifest", str(manifest_path),
            "--report", str(report_path),
        ])
        assert rc == 0
        manifest = json.loads(manifest_path.read_text())
        assert manifest["approved"] is False
        assert manifest["actions"][0]["category"] == ACTION_CLOSE
        assert "Backlog Triage Recommendations" in report_path.read_text()
        assert "manifest" in capsys.readouterr().out

    def test_missing_dir_writes_empty_manifest(self, tmp_path: Path):
        manifest_path = tmp_path / "manifest.json"
        report_path = tmp_path / "report.md"
        rc = main([
            "--results-dir", str(tmp_path / "absent"),
            "--manifest", str(manifest_path),
            "--report", str(report_path),
        ])
        assert rc == 0
        manifest = json.loads(manifest_path.read_text())
        assert manifest["actions"] == []
        assert "No actions recommended" in report_path.read_text()

    def test_malformed_result_skipped_other_issue_kept(self, tmp_path: Path):
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        _write_result(results_dir, "bad.json", "{not json")
        _write_result(
            results_dir, "ok.json",
            {"number": 2, "title": "t", "verdict": "STALE"},
        )
        manifest_path = tmp_path / "manifest.json"
        report_path = tmp_path / "report.md"
        rc = main([
            "--results-dir", str(results_dir),
            "--manifest", str(manifest_path),
            "--report", str(report_path),
        ])
        assert rc == 0
        manifest = json.loads(manifest_path.read_text())
        assert manifest["issues_triaged"] == 1
        assert manifest["actions"][0]["issue"] == 2

    def test_appends_to_github_step_summary(self, tmp_path: Path):
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        _write_result(results_dir, "r.json", {"number": 1, "title": "t"})
        manifest_path = tmp_path / "manifest.json"
        report_path = tmp_path / "report.md"
        step_summary = tmp_path / "step.md"
        rc = main([
            "--results-dir", str(results_dir),
            "--manifest", str(manifest_path),
            "--report", str(report_path),
            "--github-step-summary", str(step_summary),
        ])
        assert rc == 0
        assert "Backlog Triage Recommendations" in step_summary.read_text()

    def test_expected_count_mismatch_returns_logic_error(self, tmp_path: Path, capsys):
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        _write_result(results_dir, "r.json", {"number": 1, "title": "t"})
        manifest_path = tmp_path / "manifest.json"
        report_path = tmp_path / "report.md"
        rc = main([
            "--results-dir", str(results_dir),
            "--manifest", str(manifest_path),
            "--report", str(report_path),
            "--expected-count", "2",
        ])
        assert rc == 1
        assert json.loads(manifest_path.read_text())["issues_triaged"] == 1
        assert "Backlog Triage Recommendations" in report_path.read_text()
        assert "expected 2" in capsys.readouterr().err
