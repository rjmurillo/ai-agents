#!/usr/bin/env python3
"""Tests for backlog_provenance (issue #5702). All GitHub I/O is mocked."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script

mod = import_skill_script(".claude/skills/metrics/backlog_provenance.py")

NOW = datetime(2026, 9, 29, 12, 0, 0, tzinfo=timezone.utc)
START = NOW - timedelta(days=7)
ENDPOINT = "repos/o/r/issues?state=all&since=x&per_page=100"


def record(number, minutes_ago=60.0, title="A feature", login="owner", labels=(), pr=False):
    created = NOW - timedelta(minutes=minutes_ago)
    data = {
        "number": number,
        "title": title,
        "user": {"login": login},
        "created_at": created.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "labels": [{"name": name} for name in labels],
    }
    if pr:
        data["pull_request"] = {"url": "x"}
    return data


def issue(number, at, login="owner", title="t", labels=()):
    return mod.Issue(number, title, login, at, frozenset(labels))


def pages(*page_lists):
    """A fetcher that returns each list in turn and [] afterwards."""
    queue = list(page_lists)

    def fetcher(_endpoint, _page):
        return queue.pop(0) if queue else []

    return fetcher


def collect(*page_lists, start=START, end=NOW):
    return mod.collect_backlog(
        ENDPOINT, start, end, fetcher=pages(*page_lists), pacer=lambda _s: None
    )


class TestParseTimestamp:
    def test_parses_z_suffix(self):
        assert mod.parse_timestamp("2026-09-29T12:00:00Z") == NOW

    @pytest.mark.parametrize("value", [None, "", 5, "not-a-date", "2026-09-29T12:00:00"])
    def test_rejects_bad_values(self, value):
        with pytest.raises(mod.ReportError) as err:
            mod.parse_timestamp(value)
        assert err.value.exit_code == 3


class TestParseRecord:
    def test_reads_fields_and_lowercases_labels(self):
        parsed = mod.parse_record(record(7, labels=("Source:Agent", "bug")))
        assert parsed.number == 7
        assert parsed.login == "owner"
        assert parsed.labels == frozenset({"source:agent", "bug"})

    def test_missing_user_and_labels(self):
        parsed = mod.parse_record(
            {"number": 1, "title": None, "created_at": "2026-09-29T11:00:00Z", "labels": None}
        )
        assert parsed.login == ""
        assert parsed.title == ""
        assert parsed.labels == frozenset()

    @pytest.mark.parametrize("bad", ["text", None, {"number": "1"}, {"number": True}, {}])
    def test_rejects_malformed_records(self, bad):
        with pytest.raises(mod.ReportError) as err:
            mod.parse_record(bad)
        assert err.value.exit_code == 3

    def test_ignores_non_dict_labels(self):
        raw = record(1)
        raw["labels"] = ["plain", {"name": "source:human"}]
        assert mod.parse_record(raw).labels == frozenset({"source:human"})


class TestClassifyProvenance:
    @pytest.mark.parametrize(
        ("labels", "bucket"),
        [
            (("source:human",), "human-only"),
            (("source:agent",), "agent-only"),
            (("source:human", "source:agent"), "conflict"),
            ((), "unknown"),
            (("bug",), "unknown"),
        ],
    )
    def test_buckets(self, labels, bucket):
        assert mod.classify_provenance(issue(1, NOW, labels=labels)) == bucket

    def test_author_does_not_change_bucket(self):
        assert mod.classify_provenance(issue(1, NOW, login="rjmurillo")) == "unknown"


class TestIsMachinery:
    @pytest.mark.parametrize(
        "title",
        [
            "Ratchet drifts",
            "LEFTHOOK config",
            "fix hooks",
            "pre_pr gate",
            "ADR review",
            "pr-autofix",
        ],
    )
    def test_matches_terms_case_insensitively(self, title):
        assert mod.is_machinery(issue(1, NOW, title=title))

    @pytest.mark.parametrize("title", ["Address feedback", "Add dark mode", "gateway timeout", ""])
    def test_whole_word_only(self, title):
        assert not mod.is_machinery(issue(1, NOW, title=title))

    def test_area_validation_label(self):
        assert mod.is_machinery(issue(1, NOW, title="Add dark mode", labels=("area-validation",)))


class TestFindBursts:
    def test_three_within_ten_minutes_is_a_burst(self):
        items = [issue(n, NOW + timedelta(minutes=n * 4)) for n in (1, 2, 3)]
        assert mod.find_bursts(items) == [[1, 2, 3]]

    def test_two_issues_are_not_a_burst(self):
        items = [issue(n, NOW + timedelta(minutes=n)) for n in (1, 2)]
        assert mod.find_bursts(items) == []

    def test_exactly_ten_minutes_from_first_is_inside(self):
        items = [
            issue(1, NOW),
            issue(2, NOW + timedelta(minutes=5)),
            issue(3, NOW + timedelta(minutes=10)),
        ]
        assert mod.find_bursts(items) == [[1, 2, 3]]

    def test_one_second_past_ten_minutes_is_outside(self):
        items = [
            issue(1, NOW),
            issue(2, NOW + timedelta(minutes=5)),
            issue(3, NOW + timedelta(minutes=10, seconds=1)),
        ]
        assert mod.find_bursts(items) == []

    def test_different_logins_do_not_combine(self):
        items = [issue(1, NOW, "a"), issue(2, NOW, "b"), issue(3, NOW, "a")]
        assert mod.find_bursts(items) == []

    def test_overlapping_windows_assign_each_issue_once(self):
        # 0,5,10 form one burst; 15 and 20 start a new group of two, not a burst.
        items = [issue(n, NOW + timedelta(minutes=m)) for n, m in enumerate((0, 5, 10, 15, 20), 1)]
        assert mod.find_bursts(items) == [[1, 2, 3]]

    def test_two_bursts_from_one_login(self):
        first = [issue(n, NOW + timedelta(minutes=n)) for n in (1, 2, 3)]
        later = [issue(n, NOW + timedelta(hours=2, minutes=n)) for n in (4, 5, 6)]
        assert mod.find_bursts(first + later) == [[1, 2, 3], [4, 5, 6]]

    def test_empty_input(self):
        assert mod.find_bursts([]) == []


class TestShare:
    def test_ratio(self):
        assert mod.share(1, 3) == 0.3333

    def test_zero_total_is_none_not_zero(self):
        assert mod.share(0, 0) is None


class TestCollectBacklog:
    def test_keeps_only_window_issues_and_counts_exclusions(self):
        backlog = collect(
            [
                record(1, minutes_ago=60),
                record(2, pr=True),
                record(3, minutes_ago=60 * 24 * 8),
                record(4, minutes_ago=-5),
            ]
        )
        assert [item.number for item in backlog.issues] == [1]
        assert backlog.stats.pull_requests_excluded == 1
        assert backlog.stats.out_of_window_excluded == 2
        assert backlog.stats.records_fetched == 4
        assert backlog.stats.pages == 1

    def test_deduplicates_by_number_across_pages(self):
        backlog = collect([record(1), record(2)], [record(2), record(3)])
        assert [item.number for item in backlog.issues] == [1, 2, 3]
        assert backlog.stats.duplicates_dropped == 1
        assert backlog.stats.pages == 2

    def test_start_boundary_is_inclusive_and_end_exclusive(self):
        at_start = record(1, minutes_ago=7 * 24 * 60)
        at_end = record(2, minutes_ago=0)
        backlog = collect([at_start, at_end])
        assert [item.number for item in backlog.issues] == [1]

    def test_closed_issues_are_counted(self):
        raw = record(1)
        raw["state"] = "closed"
        assert len(collect([raw]).issues) == 1

    def test_empty_first_page_yields_empty_backlog(self):
        backlog = collect()
        assert backlog.issues == []
        assert backlog.stats.pages == 0

    def test_page_with_only_repeats_stops_with_error(self):
        with pytest.raises(mod.ReportError, match="did not advance"):
            collect([record(1)], [record(1)])

    def test_malformed_later_page_aborts(self):
        def fetcher(_endpoint, page):
            if page == 1:
                return [record(1)]
            raise mod.ReportError("Malformed JSON on page 2", 3, "ApiError")

        with pytest.raises(mod.ReportError) as err:
            mod.collect_backlog(ENDPOINT, START, NOW, fetcher=fetcher, pacer=lambda _s: None)
        assert err.value.exit_code == 3

    def test_malformed_record_aborts(self):
        with pytest.raises(mod.ReportError):
            collect([record(1), "oops"])

    def test_paces_between_pages(self):
        paced = []
        mod.collect_backlog(ENDPOINT, START, NOW, fetcher=pages([record(1)]), pacer=paced.append)
        assert paced == [mod.REST_PAGE_PACE_SECONDS]


def completed(stdout="", stderr="", code=0):
    return subprocess.CompletedProcess(args=[], returncode=code, stdout=stdout, stderr=stderr)


class TestFetchPage:
    def test_passes_page_number_and_returns_list(self):
        with patch.object(mod.subprocess, "run", return_value=completed("[]")) as run:
            assert mod.fetch_page(ENDPOINT, 3) == []
        assert run.call_args.args[0] == ["gh", "api", f"{ENDPOINT}&page=3"]

    def test_endpoint_without_query_uses_question_mark(self):
        with patch.object(mod.subprocess, "run", return_value=completed("[]")) as run:
            mod.fetch_page("repos/o/r/issues", 1)
        assert run.call_args.args[0][2] == "repos/o/r/issues?page=1"

    def test_nonzero_exit_is_api_error(self):
        with patch.object(mod.subprocess, "run", return_value=completed(stderr="boom", code=1)):
            with pytest.raises(mod.ReportError) as err:
                mod.fetch_page(ENDPOINT, 2)
        assert err.value.exit_code == 3
        assert "page 2" in str(err.value)

    def test_auth_failure_maps_to_exit_4(self):
        failed = completed(stderr="HTTP 401: Bad credentials", code=1)
        with patch.object(mod.subprocess, "run", return_value=failed):
            with pytest.raises(mod.ReportError) as err:
                mod.fetch_page(ENDPOINT, 1)
        assert err.value.exit_code == 4

    def test_rate_limit_maps_to_exit_3(self):
        failed = completed(stderr="HTTP 403: API rate limit exceeded", code=1)
        with patch.object(mod.subprocess, "run", return_value=failed):
            with pytest.raises(mod.ReportError, match="Rate limit") as err:
                mod.fetch_page(ENDPOINT, 1)
        assert err.value.exit_code == 3

    def test_invalid_json_is_api_error(self):
        with patch.object(mod.subprocess, "run", return_value=completed("{not json")):
            with pytest.raises(mod.ReportError, match="Malformed JSON") as err:
                mod.fetch_page(ENDPOINT, 1)
        assert err.value.exit_code == 3

    def test_non_list_json_is_api_error(self):
        with patch.object(mod.subprocess, "run", return_value=completed('{"message": "x"}')):
            with pytest.raises(mod.ReportError, match="expected a list"):
                mod.fetch_page(ENDPOINT, 1)

    def test_timeout_is_exit_3(self):
        boom = subprocess.TimeoutExpired(cmd="gh", timeout=30)
        with patch.object(mod.subprocess, "run", side_effect=boom):
            with pytest.raises(mod.ReportError) as err:
                mod.fetch_page(ENDPOINT, 1)
        assert err.value.exit_code == 3

    def test_missing_gh_is_exit_4(self):
        with patch.object(mod.subprocess, "run", side_effect=FileNotFoundError):
            with pytest.raises(mod.ReportError) as err:
                mod.fetch_page(ENDPOINT, 1)
        assert err.value.exit_code == 4


def make_report(records, days=7):
    backlog = collect(records)
    return mod.build_report(backlog, "o", "r", ENDPOINT, NOW - timedelta(days=days), NOW, NOW)


class TestBuildReport:
    def test_mixed_batch_with_burst(self):
        report = make_report(
            [
                record(1, 100, "Add feature", labels=("source:human",)),
                record(2, 50, "Ratchet drift", labels=("source:agent",)),
                record(3, 48, "Validator gap", labels=("source:agent",)),
                record(4, 46, "Hook fails", labels=("source:agent",)),
                record(5, 30, "Both labels", labels=("source:human", "source:agent")),
                record(6, 20, "No label"),
            ]
        )
        assert report["total"] == 6
        counts = {name: report["provenance"][name]["count"] for name in mod.BUCKETS}
        assert counts == {"human-only": 1, "agent-only": 3, "conflict": 1, "unknown": 1}
        assert sum(counts.values()) == report["total"]
        assert report["provenance"]["agent-only"]["issues"] == [2, 3, 4]
        assert report["machinery_heuristic"]["issues"] == [2, 3, 4]
        assert report["bursts"]["groups"] == [[2, 3, 4]]
        assert report["completeness"]["complete"] is True

    def test_empty_window_reports_zero_counts_and_null_shares(self):
        report = make_report([])
        assert report["total"] == 0
        assert all(report["provenance"][name]["count"] == 0 for name in mod.BUCKETS)
        assert all(report["provenance"][name]["share"] is None for name in mod.BUCKETS)
        assert report["machinery_heuristic"]["share"] is None
        assert report["bursts"]["count"] == 0

    def test_json_serializable(self):
        json.dumps(make_report([record(1)]))


class TestRenderMarkdown:
    def test_contains_table_and_completeness(self):
        text = mod.render_markdown(make_report([record(1, labels=("source:agent",))]))
        assert "| agent-only | 1 | 100.0% |" in text
        assert "Read complete: 1 page(s)" in text
        assert "Limitations:" in text

    def test_empty_prints_na_not_zero_percent(self):
        text = mod.render_markdown(make_report([]))
        assert "| unknown | 0 | N/A |" in text
        assert "Machinery share (heuristic): 0 (N/A)" in text
        assert "0.0%" not in text


class TestResolveWindow:
    def test_defaults_to_now(self):
        start, end = mod.resolve_window(7, "", NOW)
        assert end == NOW
        assert start == NOW - timedelta(days=7)

    def test_until_is_converted_to_utc(self):
        _start, end = mod.resolve_window(1, "2026-09-29T14:00:00+02:00", NOW)
        assert end == NOW

    @pytest.mark.parametrize("days", [0, -1])
    def test_rejects_non_positive_days(self, days):
        with pytest.raises(mod.ReportError) as err:
            mod.resolve_window(days, "", NOW)
        assert err.value.exit_code == 2

    @pytest.mark.parametrize("until", ["yesterday", "2026-09-29T12:00:00"])
    def test_rejects_bad_until(self, until):
        with pytest.raises(mod.ReportError) as err:
            mod.resolve_window(7, until, NOW)
        assert err.value.exit_code == 2


class TestRequireAuth:
    def test_authenticated_passes(self):
        result = SimpleNamespace(status=mod.GhAuthStatus.AUTHENTICATED)
        with patch.object(mod, "check_gh_auth", return_value=result):
            mod._require_auth()

    def test_invalid_credentials_raise_exit_4(self):
        result = SimpleNamespace(status=mod.GhAuthStatus.INVALID_CREDENTIALS, detail="")
        with patch.object(mod, "check_gh_auth", return_value=result):
            with pytest.raises(mod.ReportError) as err:
                mod._require_auth()
        assert err.value.exit_code == 4


def run_main(argv, page_lists=(), auth=True):
    status = mod.GhAuthStatus.AUTHENTICATED if auth else mod.GhAuthStatus.INVALID_CREDENTIALS
    result = SimpleNamespace(status=status, detail="")
    fetcher = pages(*page_lists)
    with (
        patch.object(mod, "check_gh_auth", return_value=result),
        patch.object(mod, "fetch_page", side_effect=fetcher),
        patch.object(mod.time, "sleep"),
    ):
        return mod.main(["--owner", "o", "--repo", "r", *argv])


class TestMain:
    def test_zero_issue_window_prints_all_zero_table(self, capsys):
        assert run_main(["--days", "7"]) == 0
        out = capsys.readouterr().out
        assert "New issues in window: 0" in out
        assert "| human-only | 0 | N/A |" in out

    def test_json_mode_is_valid_json(self, capsys):
        page = [record(1, minutes_ago=1, labels=("source:human",))]
        with patch.object(mod, "datetime", wraps=datetime) as fake:
            fake.now.return_value = NOW + timedelta(minutes=2)
            assert run_main(["--days", "7", "--output-format", "json"], [page]) == 0
        envelope = json.loads(capsys.readouterr().out)
        assert envelope["Success"] is True
        assert envelope["Data"]["total"] == 1
        assert envelope["Data"]["provenance"]["human-only"]["issues"] == [1]

    def test_default_is_markdown_even_when_stdout_is_redirected(self, capsys):
        assert run_main([]) == 0
        assert capsys.readouterr().out.startswith("# Backlog Provenance")

    def test_invalid_days_exits_2(self, capsys):
        assert run_main(["--days", "-1"]) == 2
        assert "--days must be at least 1" in capsys.readouterr().out

    def test_invalid_days_exits_2_json_envelope(self, capsys):
        assert run_main(["--days", "0", "--output-format", "json"]) == 2
        assert json.loads(capsys.readouterr().out)["Success"] is False

    def test_auth_failure_exits_4(self):
        assert run_main([], auth=False) == 4

    def test_api_failure_exits_3_and_prints_no_report(self, capsys):
        boom = mod.ReportError("Failed to read page 2", 3, "ApiError")
        result = SimpleNamespace(status=mod.GhAuthStatus.AUTHENTICATED, detail="")
        with (
            patch.object(mod, "check_gh_auth", return_value=result),
            patch.object(mod, "fetch_page", side_effect=[[record(1, minutes_ago=1)], boom]),
            patch.object(mod.time, "sleep"),
        ):
            code = mod.main(["--owner", "o", "--repo", "r"])
        assert code == 3
        assert "Backlog Provenance" not in capsys.readouterr().out


class TestBuildEndpoint:
    def test_formats_since_in_utc(self):
        assert mod.build_endpoint("o", "r", START) == (
            "repos/o/r/issues?state=all&since=2026-09-22T12:00:00Z&per_page=100"
        )


SCRIPT_PATH = ".claude/skills/metrics/backlog_provenance.py"
REPO_LIB = Path(__file__).resolve().parents[3] / ".claude" / "lib"


class TestLibResolution:
    """The module locates github_core from a plugin root, a workspace, or its own tree."""

    def _load(self, monkeypatch, plugin_root="", workspace=""):
        monkeypatch.delenv("COPILOT_PLUGIN_ROOT", raising=False)
        monkeypatch.delenv("GITHUB_WORKSPACE", raising=False)
        if plugin_root:
            monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", plugin_root)
        else:
            monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
        if workspace:
            monkeypatch.setenv("GITHUB_WORKSPACE", workspace)
        return import_skill_script(SCRIPT_PATH, "backlog_provenance_probe")

    def test_plugin_root_with_lib_is_used(self, monkeypatch, tmp_path):
        (tmp_path / "lib").symlink_to(REPO_LIB, target_is_directory=True)
        loaded = self._load(monkeypatch, plugin_root=str(tmp_path))
        assert loaded._lib_dir == str(tmp_path / "lib")

    def test_workspace_lib_is_used(self, monkeypatch):
        workspace = REPO_LIB.parents[1]
        loaded = self._load(monkeypatch, workspace=str(workspace))
        assert loaded._lib_dir == str(REPO_LIB)

    def test_missing_lib_exits_2(self, monkeypatch, tmp_path, capsys):
        with pytest.raises(SystemExit) as err:
            self._load(monkeypatch, workspace=str(tmp_path))
        assert err.value.code == 2
        assert "Plugin lib directory not found" in capsys.readouterr().err


def test_module_entrypoint_exits_with_main_code(monkeypatch):
    import runpy

    monkeypatch.setattr(sys, "argv", ["backlog_provenance.py", "--days", "0"])
    with pytest.raises(SystemExit) as err:
        runpy.run_path(str(REPO_LIB.parents[1] / SCRIPT_PATH), run_name="__main__")
    assert err.value.code == 2
