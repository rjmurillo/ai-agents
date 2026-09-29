#!/usr/bin/env python3
"""Tests for backlog_provenance (issue #5702). All GitHub I/O is mocked."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)
TESTS_METRICS_DIR = str(Path(__file__).resolve().parent)
if TESTS_METRICS_DIR not in sys.path:
    sys.path.insert(0, TESTS_METRICS_DIR)

from backlog_test_helpers import ENDPOINT, NOW, START, record
from claude_skills_import import import_skill_script

rep = import_skill_script(".claude/skills/metrics/backlog_provenance_report.py")
mod = import_skill_script(".claude/skills/metrics/backlog_provenance.py")


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

    def test_reads_until_the_empty_page_across_three_pages(self):
        backlog = collect([record(1)], [record(2)], [record(3)])
        assert [item.number for item in backlog.issues] == [1, 2, 3]
        assert backlog.stats.pages == 3

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

    @pytest.mark.parametrize(
        ("days", "until"),
        [
            (10**9, ""),
            (10**12, ""),
            (1, "0001-01-01T00:00:00+00:00"),
            (10**6, "2026-09-29T00:00:00Z"),
        ],
    )
    def test_overflow_is_a_config_error_not_a_traceback(self, days, until):
        with pytest.raises(mod.ReportError, match="out of range") as err:
            mod.resolve_window(days, until, NOW)
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

    def test_json_mode_failure_prints_error_envelope_and_no_data(self, capsys):
        boom = mod.ReportError("Failed to read page 2", 3, "ApiError")
        result = SimpleNamespace(status=mod.GhAuthStatus.AUTHENTICATED, detail="")
        with (
            patch.object(mod, "check_gh_auth", return_value=result),
            patch.object(mod, "fetch_page", side_effect=[[record(1, minutes_ago=1)], boom]),
            patch.object(mod.time, "sleep"),
        ):
            code = mod.main(["--owner", "o", "--repo", "r", "--output-format", "json"])
        assert code == 3
        envelope = json.loads(capsys.readouterr().out)
        assert envelope["Success"] is False
        assert envelope["Data"] is None

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
    """The module locates github_core from a plugin root or its own tree."""

    def _load(self, monkeypatch, plugin_root=""):
        monkeypatch.delenv("COPILOT_PLUGIN_ROOT", raising=False)
        if plugin_root:
            monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", plugin_root)
        else:
            monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
        return import_skill_script(SCRIPT_PATH, "backlog_provenance_probe")

    def test_plugin_root_with_lib_is_used(self, monkeypatch, tmp_path):
        (tmp_path / "lib").symlink_to(REPO_LIB, target_is_directory=True)
        loaded = self._load(monkeypatch, plugin_root=str(tmp_path))
        assert loaded._lib_dir == str(tmp_path / "lib")

    def test_own_tree_lib_is_the_fallback(self, monkeypatch):
        loaded = self._load(monkeypatch)
        assert loaded._lib_dir == str(REPO_LIB)

    def test_plugin_root_without_lib_falls_through_to_own_tree(self, monkeypatch, tmp_path):
        loaded = self._load(monkeypatch, plugin_root=str(tmp_path))
        assert loaded._lib_dir == str(REPO_LIB)

    def test_missing_lib_exits_2(self, monkeypatch, tmp_path, capsys):
        real_isdir = os.path.isdir
        monkeypatch.setattr(
            os.path, "isdir", lambda p: False if str(p).endswith("lib") else real_isdir(p)
        )
        with pytest.raises(SystemExit) as err:
            self._load(monkeypatch)
        assert err.value.code == 2
        assert "Plugin lib directory not found" in capsys.readouterr().err


def test_module_entrypoint_exits_with_main_code(monkeypatch):
    import runpy

    monkeypatch.setattr(sys, "argv", ["backlog_provenance.py", "--days", "0"])
    with pytest.raises(SystemExit) as err:
        runpy.run_path(str(REPO_LIB.parents[1] / SCRIPT_PATH), run_name="__main__")
    assert err.value.code == 2
