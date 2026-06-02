"""Tests for scripts.issue_triage module.

Covers Phase 1 mechanical triage rules described in issue #1799:
stale detection, missing priority label, and missing area label.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.issue_triage import (
    AREA_LABEL_PREFIX,
    DEFAULT_STALE_DAYS,
    PRIORITY_LABEL_PREFIX,
    IssueFinding,
    IssueRecord,
    TriageReport,
    build_ai_matrix,
    build_report,
    classify,
    fetch_open_issues,
    format_human,
    has_area_label,
    has_priority_label,
    is_stale,
    load_issues_from_input,
    main,
    parse_args,
    parse_iso_timestamp,
    parse_issue_record,
    split_github_repository,
    write_ai_github_outputs,
)


@pytest.fixture
def now() -> datetime:
    """Anchor 'now' so tests are deterministic."""
    return datetime(2026, 4, 27, 12, 0, 0, tzinfo=UTC)


def make_issue(
    *,
    number: int = 1,
    title: str = "issue",
    days_old: int = 0,
    labels: tuple[str, ...] = (),
    base: datetime | None = None,
) -> IssueRecord:
    """Build an IssueRecord whose updated_at is days_old days before base."""
    base = base or datetime(2026, 4, 27, 12, 0, 0, tzinfo=UTC)
    updated = (base - timedelta(days=days_old)).isoformat().replace("+00:00", "Z")
    return IssueRecord(number=number, title=title, updated_at=updated, labels=labels)


class TestParseIsoTimestamp:
    def test_accepts_z_suffix(self):
        result = parse_iso_timestamp("2026-04-27T12:00:00Z")
        assert result == datetime(2026, 4, 27, 12, 0, 0, tzinfo=UTC)

    def test_accepts_offset(self):
        result = parse_iso_timestamp("2026-04-27T12:00:00+00:00")
        assert result == datetime(2026, 4, 27, 12, 0, 0, tzinfo=UTC)

    def test_accepts_fractional_seconds(self):
        result = parse_iso_timestamp("2026-04-27T12:00:00.123Z")
        assert result.microsecond == 123000

    def test_rejects_invalid(self):
        with pytest.raises(ValueError):
            parse_iso_timestamp("not-a-date")

    def test_rejects_naive(self):
        with pytest.raises(ValueError):
            parse_iso_timestamp("2026-04-27T12:00:00")


class TestParseIssueRecord:
    def test_extracts_label_names(self):
        record = parse_issue_record(
            {
                "number": 42,
                "title": "Fix it",
                "updatedAt": "2026-04-27T12:00:00Z",
                "labels": [
                    {"name": "priority:P1"},
                    {"name": "area-infrastructure"},
                ],
            }
        )
        assert record.number == 42
        assert record.labels == ("priority:P1", "area-infrastructure")

    def test_handles_string_labels(self):
        record = parse_issue_record(
            {
                "number": 1,
                "title": "t",
                "updatedAt": "2026-04-27T12:00:00Z",
                "labels": ["bug"],
            }
        )
        assert record.labels == ("bug",)

    def test_handles_missing_labels_field(self):
        record = parse_issue_record(
            {
                "number": 1,
                "title": "t",
                "updatedAt": "2026-04-27T12:00:00Z",
            }
        )
        assert record.labels == ()

    def test_rejects_missing_number(self):
        with pytest.raises(ValueError):
            parse_issue_record({"title": "t", "updatedAt": "2026-04-27T12:00:00Z"})

    def test_rejects_non_int_number(self):
        with pytest.raises(ValueError):
            parse_issue_record(
                {"number": "abc", "title": "t", "updatedAt": "2026-04-27T12:00:00Z"}
            )


class TestIsStale:
    def test_fresh_issue_not_stale(self, now):
        issue = make_issue(days_old=5, base=now)
        assert is_stale(issue, now=now, stale_days=60) is False

    def test_old_issue_stale(self, now):
        issue = make_issue(days_old=120, base=now)
        assert is_stale(issue, now=now, stale_days=60) is True

    def test_at_threshold_is_stale(self, now):
        issue = make_issue(days_old=60, base=now)
        assert is_stale(issue, now=now, stale_days=60) is True

    def test_just_under_threshold_not_stale(self, now):
        # 59 days, 23 hours, 59 minutes < 60 days threshold.
        updated = (now - timedelta(days=59, hours=23, minutes=59)).isoformat().replace(
            "+00:00", "Z"
        )
        issue = IssueRecord(number=1, title="t", updated_at=updated, labels=())
        assert is_stale(issue, now=now, stale_days=60) is False

    def test_zero_threshold_disables_rule(self, now):
        issue = make_issue(days_old=365, base=now)
        assert is_stale(issue, now=now, stale_days=0) is False

    def test_invalid_timestamp_returns_false(self, now):
        issue = IssueRecord(number=1, title="t", updated_at="garbage", labels=())
        assert is_stale(issue, now=now, stale_days=60) is False


class TestLabelPredicates:
    def test_priority_label_detected(self):
        issue = IssueRecord(
            number=1, title="t", updated_at="2026-04-27T00:00:00Z",
            labels=("priority:P0", "bug"),
        )
        assert has_priority_label(issue) is True

    def test_priority_label_missing(self):
        issue = IssueRecord(
            number=1, title="t", updated_at="2026-04-27T00:00:00Z",
            labels=("bug",),
        )
        assert has_priority_label(issue) is False

    def test_area_label_detected(self):
        issue = IssueRecord(
            number=1, title="t", updated_at="2026-04-27T00:00:00Z",
            labels=("area-infrastructure",),
        )
        assert has_area_label(issue) is True

    def test_area_label_missing(self):
        issue = IssueRecord(
            number=1, title="t", updated_at="2026-04-27T00:00:00Z",
            labels=("priority:P1", "bug"),
        )
        assert has_area_label(issue) is False

    def test_label_prefix_constants(self):
        assert PRIORITY_LABEL_PREFIX == "priority:"
        assert AREA_LABEL_PREFIX == "area-"


class TestClassify:
    def test_empty_input_yields_no_findings(self, now):
        stale, missing_priority, missing_area = classify([], now=now, stale_days=60)
        assert stale == []
        assert missing_priority == []
        assert missing_area == []

    def test_each_rule_independent(self, now):
        fresh_well_labeled = make_issue(
            number=1, title="ok", days_old=1, base=now,
            labels=("priority:P0", "area-infrastructure"),
        )
        stale_unlabeled = make_issue(
            number=2, title="rotten", days_old=120, base=now, labels=(),
        )
        stale, missing_priority, missing_area = classify(
            [fresh_well_labeled, stale_unlabeled], now=now, stale_days=60,
        )
        assert [f.number for f in stale] == [2]
        assert [f.number for f in missing_priority] == [2]
        assert [f.number for f in missing_area] == [2]

    def test_finding_carries_reason(self, now):
        issue = make_issue(number=7, title="t", days_old=200, base=now, labels=())
        stale, _, _ = classify([issue], now=now, stale_days=60)
        assert stale[0].reasons == ["no activity in 60+ days"]


class TestBuildReport:
    def test_report_aggregates_findings(self, now):
        issues = [
            make_issue(number=1, title="fresh", days_old=1, base=now,
                       labels=("priority:P1", "area-x")),
            make_issue(number=2, title="stale-no-labels", days_old=120, base=now),
        ]
        report = build_report(issues, repo="o/r", now=now, stale_days=60)
        assert report.repo == "o/r"
        assert report.issues_scanned == 2
        assert report.stale_days == 60
        assert [f.number for f in report.stale] == [2]
        assert [f.number for f in report.missing_priority] == [2]
        assert [f.number for f in report.missing_area] == [2]
        assert report.has_findings is True

    def test_clean_backlog_has_no_findings(self, now):
        issues = [
            make_issue(number=1, title="ok", days_old=1, base=now,
                       labels=("priority:P1", "area-x")),
        ]
        report = build_report(issues, repo="o/r", now=now, stale_days=60)
        assert report.has_findings is False

    def test_report_round_trips_to_json(self, now):
        report = build_report(
            [make_issue(number=1, days_old=1, base=now,
                        labels=("priority:P0", "area-x"))],
            repo="o/r", now=now, stale_days=60,
        )
        payload = json.loads(json.dumps(asdict(report)))
        assert payload["repo"] == "o/r"
        assert payload["timestamp"].endswith("Z")
        assert payload["issues_scanned"] == 1


class TestFormatHuman:
    def test_renders_each_section(self, now):
        report = build_report(
            [make_issue(number=42, title="bad", days_old=200, base=now)],
            repo="o/r", now=now, stale_days=60,
        )
        text = format_human(report)
        assert "Stale (1):" in text
        assert "Missing priority label (1):" in text
        assert "Missing area label (1):" in text
        assert "#42: bad" in text

    def test_renders_none_when_empty(self, now):
        report = build_report([], repo="o/r", now=now, stale_days=60)
        text = format_human(report)
        assert text.count("(none)") == 3


class TestBuildAiMatrix:
    def test_empty_input_yields_empty_matrix(self):
        matrix = build_ai_matrix([])
        assert matrix == {"include": [], "count": 0}

    def test_rows_carry_number_and_title(self, now):
        issues = [
            make_issue(number=10, title="add backlog triage", base=now),
            make_issue(number=11, title="route by area", base=now),
        ]
        matrix = build_ai_matrix(issues)
        assert matrix["count"] == 2
        assert matrix["include"] == [
            {"number": 10, "title": "add backlog triage"},
            {"number": 11, "title": "route by area"},
        ]

    def test_matrix_round_trips_to_json(self, now):
        matrix = build_ai_matrix([make_issue(number=7, title="t", base=now)])
        payload = json.loads(json.dumps(matrix))
        assert payload["count"] == 1
        assert payload["include"][0]["number"] == 7

    def test_matrix_omits_labels_and_timestamps(self, now):
        issue = make_issue(
            number=5, title="t", base=now, labels=("priority:P0", "area-x"),
        )
        matrix = build_ai_matrix([issue])
        row = matrix["include"][0]
        assert set(row.keys()) == {"number", "title"}

    def test_github_outputs_strip_non_matrix_count(self, tmp_path: Path, now):
        output_path = tmp_path / "github-output.txt"
        matrix = build_ai_matrix([make_issue(number=7, title="t", base=now)])
        write_ai_github_outputs(matrix, str(output_path))
        lines = output_path.read_text().splitlines()
        assert json.loads(lines[0].removeprefix("matrix=")) == {
            "include": [{"number": 7, "title": "t"}],
        }
        assert "has-issues=true" in lines
        assert "count=1" in lines


class TestGitHubRepositoryDefaults:
    def test_split_github_repository_accepts_owner_repo(self):
        assert split_github_repository("octo/repo") == ("octo", "repo")

    @pytest.mark.parametrize("value", ["not-a-slug", "owner/", "/repo", "owner/repo/extra"])
    def test_split_github_repository_rejects_invalid_slug(self, value):
        assert split_github_repository(value) == ("", "")


class TestFetchOpenIssues:
    def test_rejects_invalid_limit(self):
        with pytest.raises(ValueError):
            fetch_open_issues("o", "r", limit=0)
        with pytest.raises(ValueError):
            fetch_open_issues("o", "r", limit=10_000)

    def test_returns_parsed_payload(self):
        completed = type(
            "Completed", (), {"returncode": 0, "stdout": '[{"number": 1}]', "stderr": ""},
        )
        with patch("scripts.issue_triage.subprocess.run", return_value=completed) as run:
            payload = fetch_open_issues("o", "r", limit=10)
        assert payload == [{"number": 1}]
        assert run.called

    def test_raises_on_nonzero_exit(self):
        err = subprocess.CalledProcessError(1, ["gh"], output="", stderr="boom")
        with patch("scripts.issue_triage.subprocess.run", side_effect=err):
            with pytest.raises(RuntimeError, match="boom"):
                fetch_open_issues("o", "r", limit=10)

    def test_raises_on_timeout(self):
        err = subprocess.TimeoutExpired(cmd=["gh"], timeout=30)
        with patch("scripts.issue_triage.subprocess.run", side_effect=err):
            with pytest.raises(RuntimeError, match="timed out"):
                fetch_open_issues("o", "r", limit=10)

    def test_raises_on_missing_gh_binary(self):
        err = FileNotFoundError(2, "No such file or directory", "gh")
        with patch("scripts.issue_triage.subprocess.run", side_effect=err):
            with pytest.raises(RuntimeError, match="failed to execute"):
                fetch_open_issues("o", "r", limit=10)

    def test_raises_on_invalid_json(self):
        completed = type(
            "Completed", (), {"returncode": 0, "stdout": "not json", "stderr": ""},
        )
        with patch("scripts.issue_triage.subprocess.run", return_value=completed):
            with pytest.raises(RuntimeError, match="parse gh output"):
                fetch_open_issues("o", "r", limit=10)

    def test_raises_on_non_list_payload(self):
        completed = type(
            "Completed", (), {"returncode": 0, "stdout": '{"x": 1}', "stderr": ""},
        )
        with patch("scripts.issue_triage.subprocess.run", return_value=completed):
            with pytest.raises(RuntimeError, match="non-list"):
                fetch_open_issues("o", "r", limit=10)


class TestLoadIssuesFromInput:
    def test_reads_array(self, tmp_path: Path):
        path = tmp_path / "issues.json"
        path.write_text(json.dumps([{"number": 1}]))
        assert load_issues_from_input(str(path)) == [{"number": 1}]

    def test_rejects_non_array(self, tmp_path: Path):
        path = tmp_path / "issues.json"
        path.write_text(json.dumps({"number": 1}))
        with pytest.raises(ValueError, match="JSON array"):
            load_issues_from_input(str(path))


class TestMain:
    def test_input_path_runs_without_gh(self, tmp_path: Path, capsys):
        path = tmp_path / "issues.json"
        path.write_text(
            json.dumps(
                [
                    {
                        "number": 1,
                        "title": "stale",
                        "updatedAt": "2024-01-01T00:00:00Z",
                        "labels": [],
                    },
                ]
            )
        )
        rc = main(["--input", str(path), "--format", "json", "--stale-days", "30"])
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["issues_scanned"] == 1
        assert [f["number"] for f in payload["stale"]] == [1]
        assert [f["number"] for f in payload["missing_priority"]] == [1]
        assert [f["number"] for f in payload["missing_area"]] == [1]

    def test_negative_stale_days_returns_config_error(self, capsys):
        rc = main(["--owner", "o", "--repo", "r", "--stale-days", "-1"])
        assert rc == 2
        err = capsys.readouterr().err
        assert ">= 0" in err

    def test_missing_owner_returns_config_error(self, capsys):
        rc = main([])
        assert rc == 2
        assert "--owner" in capsys.readouterr().err

    def test_skips_malformed_issue_records(self, tmp_path: Path, capsys):
        path = tmp_path / "issues.json"
        path.write_text(
            json.dumps(
                [
                    {"number": 1, "title": "ok", "updatedAt": "2026-04-27T00:00:00Z"},
                    {"title": "missing-number", "updatedAt": "2026-04-27T00:00:00Z"},
                ]
            )
        )
        rc = main(["--input", str(path), "--format", "json"])
        assert rc == 0
        captured = capsys.readouterr()
        payload = json.loads(captured.out)
        assert payload["issues_scanned"] == 1
        assert "skipping malformed issue" in captured.err

    def test_external_failure_returns_exit_three(self, capsys):
        with patch(
            "scripts.issue_triage.fetch_open_issues",
            side_effect=RuntimeError("api down"),
        ):
            rc = main(["--owner", "o", "--repo", "r"])
        assert rc == 3
        assert "api down" in capsys.readouterr().err

    def test_default_stale_days_constant(self):
        args = parse_args(["--owner", "o", "--repo", "r"])
        assert args.stale_days == DEFAULT_STALE_DAYS

    def test_ai_flag_emits_matrix(self, tmp_path: Path, capsys):
        path = tmp_path / "issues.json"
        path.write_text(
            json.dumps(
                [
                    {
                        "number": 42,
                        "title": "needs triage",
                        "updatedAt": "2026-04-27T00:00:00Z",
                        "labels": [],
                    },
                ]
            )
        )
        rc = main(["--input", str(path), "--ai"])
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["count"] == 1
        assert payload["include"] == [{"number": 42, "title": "needs triage"}]

    def test_ai_flag_overrides_format(self, tmp_path: Path, capsys):
        path = tmp_path / "issues.json"
        path.write_text(json.dumps([]))
        rc = main(["--input", str(path), "--ai", "--format", "human"])
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload == {"include": [], "count": 0}

    def test_ai_flag_uses_github_repository_default(self, monkeypatch, capsys):
        monkeypatch.setenv("GITHUB_REPOSITORY", "octo/repo")
        with patch("scripts.issue_triage.fetch_open_issues", return_value=[]):
            rc = main(["--ai"])
        assert rc == 0
        assert json.loads(capsys.readouterr().out) == {"include": [], "count": 0}

    def test_ai_github_output_still_prints_json(self, tmp_path: Path, capsys):
        issues_path = tmp_path / "issues.json"
        output_path = tmp_path / "github-output.txt"
        issues_path.write_text(json.dumps([{
            "number": 1,
            "title": "needs triage",
            "updatedAt": "2026-04-27T00:00:00Z",
        }]))
        rc = main(["--input", str(issues_path), "--ai", "--github-output", str(output_path)])
        assert rc == 0
        assert json.loads(capsys.readouterr().out)["count"] == 1
        assert "has-issues=true" in output_path.read_text()


class TestTriageReportDataclass:
    def test_default_has_findings_false(self):
        report = TriageReport(timestamp="t", repo="o/r", stale_days=60)
        assert report.has_findings is False

    def test_finding_dataclass_defaults(self):
        finding = IssueFinding(number=1, title="t")
        assert finding.reasons == []
