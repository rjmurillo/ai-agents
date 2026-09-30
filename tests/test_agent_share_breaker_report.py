"""Tests for .github/scripts/agent_share_breaker_report.py (epic #5698, AC-8, report only)."""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS = ROOT / ".github" / "scripts"
_WORKFLOW = ROOT / ".github" / "workflows" / "label-issue-source.yml"

sys.path.insert(0, str(_SCRIPTS))
_spec = importlib.util.spec_from_file_location(
    "agent_share_breaker_report_under_test", _SCRIPTS / "agent_share_breaker_report.py"
)
assert _spec is not None and _spec.loader is not None
mod = importlib.util.module_from_spec(_spec)
sys.modules["agent_share_breaker_report_under_test"] = mod
_spec.loader.exec_module(mod)

OWNER = "rjmurillo"
NOW = datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc)


def _iso(days_ago: float) -> str:
    return (NOW - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _issue(number: int, source: str | None, days_ago: float = 1, **extra):
    labels = [{"name": source}] if source else []
    return {"number": number, "created_at": _iso(days_ago), "labels": labels, **extra}


def _agents(count: int, start: int = 100) -> list[dict]:
    return [_issue(start + i, mod.LABEL_AGENT) for i in range(count)]


def _humans(count: int, start: int = 200) -> list[dict]:
    return [_issue(start + i, mod.LABEL_HUMAN) for i in range(count)]


def _comment(login: str, body: str, utype: str = "User", when: str = "2026-09-29T00:00:00Z"):
    return {
        "user": {"login": login, "type": utype},
        "body": body,
        "created_at": when,
        "html_url": f"https://example.invalid/{login}",
    }


class TestShare:
    def test_above_fifty_percent_is_tripped(self):
        share = mod.compute_share(_agents(3) + _humans(2), NOW)
        assert (share.agent, share.human, share.tripped) == (3, 2, True)

    def test_exactly_fifty_percent_is_not_tripped(self):
        share = mod.compute_share(_agents(2) + _humans(2), NOW)
        assert share.percent == 50.0
        assert share.tripped is False

    def test_just_below_fifty_percent_is_not_tripped(self):
        assert mod.compute_share(_agents(49) + _humans(51), NOW).tripped is False

    def test_just_above_fifty_percent_is_tripped(self):
        assert mod.compute_share(_agents(51) + _humans(49), NOW).tripped is True

    def test_empty_window_has_no_share_and_is_not_tripped(self):
        share = mod.compute_share([], NOW)
        assert share.percent is None
        assert share.tripped is False

    def test_only_unlabeled_issues_is_an_empty_share(self):
        share = mod.compute_share([_issue(1, None), _issue(2, None)], NOW)
        assert (share.total, share.tripped) == (0, False)

    def test_unlabeled_issues_are_excluded_from_both_sides(self):
        issues = _agents(1) + _humans(1) + [_issue(n, None) for n in range(300, 310)]
        share = mod.compute_share(issues, NOW)
        assert (share.agent, share.human, share.percent) == (1, 1, 50.0)

    def test_pull_requests_are_excluded(self):
        issues = [_issue(1, mod.LABEL_AGENT, pull_request={"url": "x"}), *_humans(1)]
        assert mod.compute_share(issues, NOW).agent == 0

    def test_issue_older_than_seven_days_is_outside_the_window(self):
        issues = [_issue(1, mod.LABEL_AGENT, days_ago=7.0), *_humans(1)]
        assert mod.compute_share(issues, NOW).agent == 0

    def test_issue_just_inside_seven_days_counts(self):
        issues = [_issue(1, mod.LABEL_AGENT, days_ago=6.99), *_humans(1)]
        assert mod.compute_share(issues, NOW).agent == 1

    def test_issue_created_after_the_anchor_is_excluded(self):
        issues = [_issue(1, mod.LABEL_AGENT, days_ago=-0.5), *_humans(1)]
        assert mod.compute_share(issues, NOW).agent == 0

    def test_both_labels_count_once_as_agent(self):
        both = {
            "number": 5,
            "created_at": _iso(1),
            "labels": [{"name": mod.LABEL_HUMAN}, {"name": mod.LABEL_AGENT}],
        }
        share = mod.compute_share([both], NOW)
        assert (share.agent, share.human) == (1, 0)

    def test_duplicate_numbers_count_once(self):
        issue = _issue(9, mod.LABEL_AGENT)
        assert mod.compute_share([issue, dict(issue)], NOW).agent == 1

    def test_agent_numbers_are_sorted(self):
        share = mod.compute_share([_issue(9, mod.LABEL_AGENT), _issue(3, mod.LABEL_AGENT)], NOW)
        assert share.agent_numbers == (3, 9)

    def test_labels_key_null_is_unlabeled(self):
        assert mod.source_of({"labels": None}) is None


class TestResets:
    def test_owner_token_is_a_valid_reset(self):
        scan = mod.find_resets([_comment(OWNER, mod.RESET_TOKEN)], OWNER)
        assert (len(scan.valid), scan.ignored) == (1, 0)

    def test_no_token_means_no_reset(self):
        scan = mod.find_resets([_comment(OWNER, "reset please")], OWNER)
        assert (len(scan.valid), scan.ignored) == (0, 0)

    def test_empty_comment_list(self):
        scan = mod.find_resets([], OWNER)
        assert (len(scan.valid), scan.ignored) == (0, 0)

    def test_forged_reset_from_non_owner_is_ignored(self):
        scan = mod.find_resets([_comment("mallory", mod.RESET_TOKEN)], OWNER)
        assert (len(scan.valid), scan.ignored, scan.ignored_logins) == (0, 1, ("mallory",))

    def test_bot_with_owner_login_is_ignored(self):
        scan = mod.find_resets([_comment(OWNER, mod.RESET_TOKEN, utype="Bot")], OWNER)
        assert (len(scan.valid), scan.ignored) == (0, 1)

    def test_owner_login_match_ignores_case(self):
        assert len(mod.find_resets([_comment("RJMurillo", mod.RESET_TOKEN)], OWNER).valid) == 1

    def test_token_inside_a_longer_line_does_not_count(self):
        body = f"do not post {mod.RESET_TOKEN} yet"
        assert mod.find_resets([_comment(OWNER, body)], OWNER).valid == ()

    def test_quoted_token_does_not_count(self):
        body = f"> {mod.RESET_TOKEN}"
        assert mod.find_resets([_comment(OWNER, body)], OWNER).valid == ()

    def test_token_is_case_sensitive(self):
        assert mod.find_resets([_comment(OWNER, mod.RESET_TOKEN.lower())], OWNER).valid == ()

    def test_token_on_its_own_line_among_prose_counts(self):
        body = f"Resetting.\n  {mod.RESET_TOKEN}  \nThanks"
        assert len(mod.find_resets([_comment(OWNER, body)], OWNER).valid) == 1

    def test_missing_user_is_ignored_not_crashing(self):
        forged = {"user": None, "body": mod.RESET_TOKEN, "created_at": _iso(1)}
        assert mod.find_resets([forged], OWNER).ignored == 1

    def test_ignored_login_is_sanitized(self):
        scan = mod.find_resets([_comment("a\n::error::x", mod.RESET_TOKEN)], OWNER)
        assert "\n" not in scan.ignored_logins[0]
        assert ":" not in scan.ignored_logins[0]


class TestWouldClose:
    def test_tripped_agent_trigger_would_close(self):
        share = mod.compute_share(_agents(3) + _humans(1), NOW)
        assert mod.would_close(share, _issue(100, mod.LABEL_AGENT)) == (100,)

    def test_tripped_human_trigger_would_not_close(self):
        share = mod.compute_share(_agents(3) + _humans(1), NOW)
        assert mod.would_close(share, _issue(200, mod.LABEL_HUMAN)) == ()

    def test_tripped_unlabeled_trigger_would_not_close(self):
        share = mod.compute_share(_agents(3) + _humans(1), NOW)
        assert mod.would_close(share, _issue(300, None)) == ()

    def test_not_tripped_agent_trigger_would_not_close(self):
        share = mod.compute_share(_agents(1) + _humans(3), NOW)
        assert mod.would_close(share, _issue(100, mod.LABEL_AGENT)) == ()


class TestBuildReport:
    def _report(self, agents, humans, trigger, resets=None):
        share = mod.compute_share(agents + humans, NOW)
        closes = mod.would_close(share, trigger)
        scan = resets or mod.find_resets([], OWNER)
        return mod.build_report(share, trigger, closes, scan, 5698)

    def test_tripped_report_names_would_close_and_issue_number(self):
        text = self._report(_agents(3), _humans(1), _issue(100, mod.LABEL_AGENT))
        assert "TRIPPED" in text
        assert "would close 1: #100" in text

    def test_untripped_report_says_would_close_zero(self):
        text = self._report(_agents(1), _humans(3), _issue(100, mod.LABEL_AGENT))
        assert "not tripped" in text
        assert "would close 0: none" in text

    def test_empty_window_report(self):
        text = self._report([], [], _issue(1, None))
        assert "n/a" in text
        assert "unlabeled" in text

    def test_report_states_no_enforcement(self):
        text = self._report(_agents(3), _humans(1), _issue(100, mod.LABEL_AGENT))
        assert "No issue was closed, labeled, or commented on" in text

    def test_reset_is_reported_and_not_applied(self):
        scan = mod.find_resets([_comment(OWNER, mod.RESET_TOKEN)], OWNER)
        text = self._report(_agents(3), _humans(1), _issue(100, mod.LABEL_AGENT), scan)
        assert "reset: detected" in text
        assert "not applied" in text
        assert "would close 1: #100" in text

    def test_no_reset_is_reported(self):
        text = self._report(_agents(3), _humans(1), _issue(100, mod.LABEL_AGENT))
        assert "reset: none from the owner on #5698" in text

    def test_forged_reset_is_reported_as_ignored(self):
        scan = mod.find_resets([_comment("mallory", mod.RESET_TOKEN)], OWNER)
        text = self._report(_agents(3), _humans(1), _issue(100, mod.LABEL_AGENT), scan)
        assert "reset: none from the owner" in text
        assert "ignored reset tokens: 1" in text
        assert "mallory" in text

    def test_latest_owner_reset_is_the_one_reported(self):
        old = _comment(OWNER, mod.RESET_TOKEN, when="2026-09-01T00:00:00Z")
        new = _comment(OWNER, mod.RESET_TOKEN, when="2026-09-20T00:00:00Z")
        text = self._report(
            _agents(3), _humans(1), _issue(100, mod.LABEL_AGENT), mod.find_resets([old, new], OWNER)
        )
        assert "2026-09-20T00:00:00Z" in text
        assert "2026-09-01T00:00:00Z" not in text

    def test_report_has_no_dash_characters(self):
        text = self._report(_agents(3), _humans(1), _issue(100, mod.LABEL_AGENT))
        assert chr(0x2014) not in text and chr(0x2013) not in text


def _fake_gh(issue: dict, window: list[dict], comments: list[dict]):
    def fake(args: list[str]) -> str:
        endpoint = args[-1]
        if endpoint.endswith(f"/issues/{issue['number']}"):
            return json.dumps(issue)
        if "/comments" in endpoint:
            return json.dumps([comments])
        return json.dumps([window])

    return fake


class TestRunReportAndMain:
    def test_run_report_is_read_only_and_reports_would_close(self):
        trigger = _issue(100, mod.LABEL_AGENT)
        calls: list[list[str]] = []
        fake = _fake_gh(trigger, _agents(3) + _humans(1), [])

        def recording(args: list[str]) -> str:
            calls.append(args)
            return fake(args)

        with patch.object(mod, "_gh", recording):
            text = mod.run_report("o", "r", 100, 5698)
        assert "would close 1: #100" in text
        flat = " ".join(" ".join(call) for call in calls)
        assert (
            "-X" not in flat and "POST" not in flat and "DELETE" not in flat and "PATCH" not in flat
        )

    def test_trigger_is_counted_even_when_the_list_lags(self):
        trigger = _issue(100, mod.LABEL_AGENT)
        with patch.object(mod, "_gh", _fake_gh(trigger, _humans(1), [])):
            text = mod.run_report("o", "r", 100, 5698)
        assert "1 agent of 2 labeled" in text
        assert "not tripped" in text

    def test_main_prints_report_and_exits_zero_even_when_tripped(self, capsys):
        trigger = _issue(100, mod.LABEL_AGENT)
        argv = ["--issue", "100", "--owner", OWNER, "--repo", "r"]
        with patch.object(mod, "_gh", _fake_gh(trigger, _agents(3), [])):
            code = mod.main(argv)
        assert code == mod.EXIT_OK
        assert "TRIPPED" in capsys.readouterr().out

    def test_main_writes_job_summary_when_provided(self, tmp_path, monkeypatch):
        summary = tmp_path / "summary.md"
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
        trigger = _issue(100, mod.LABEL_AGENT)
        with patch.object(mod, "_gh", _fake_gh(trigger, _agents(3), [])):
            mod.main(["--issue", "100", "--owner", OWNER, "--repo", "r"])
        assert "would close 1: #100" in summary.read_text(encoding="utf-8")

    def test_main_skips_summary_when_env_absent(self, monkeypatch):
        monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
        mod.write_summary("x")

    def test_main_returns_external_when_gh_fails(self):
        with patch.object(mod, "_gh", side_effect=mod.GhError("boom")):
            assert mod.main(["--issue", "1", "--owner", OWNER, "--repo", "r"]) == mod.EXIT_EXTERNAL

    def test_main_returns_external_on_malformed_json(self):
        with patch.object(mod, "_gh", return_value="not json"):
            assert mod.main(["--issue", "1", "--owner", OWNER, "--repo", "r"]) == mod.EXIT_EXTERNAL

    def test_main_returns_external_on_unwritable_summary(self, tmp_path, monkeypatch):
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "missing" / "s.md"))
        trigger = _issue(100, mod.LABEL_AGENT)
        with patch.object(mod, "_gh", _fake_gh(trigger, [], [])):
            code = mod.main(["--issue", "100", "--owner", OWNER, "--repo", "r"])
        assert code == mod.EXIT_EXTERNAL

    def test_main_returns_external_on_unexpected_payload_shape(self):
        with patch.object(mod, "_gh", return_value=json.dumps({"message": "x"})):
            assert mod.main(["--issue", "1", "--owner", OWNER, "--repo", "r"]) == mod.EXIT_EXTERNAL

    @pytest.mark.parametrize(
        "argv",
        [
            ["--issue", "0", "--owner", OWNER, "--repo", "r"],
            ["--issue", "1", "--owner", "bad owner", "--repo", "r"],
            ["--issue", "1", "--owner", OWNER, "--repo", ".."],
            ["--issue", "1", "--owner", OWNER, "--repo", "r", "--epic", "0"],
        ],
    )
    def test_main_returns_config_error_on_invalid_args(self, argv):
        assert mod.main(argv) == mod.EXIT_CONFIG


class TestGhWrapper:
    def test_timeout_raises_gherror(self):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("gh", 60)):
            with pytest.raises(mod.GhError):
                mod._gh(["api", "x"])

    def test_nonzero_exit_raises_sanitized_gherror(self):
        done = subprocess.CompletedProcess(["gh"], 1, stdout="a::b", stderr="line\nbreak")
        with patch("subprocess.run", return_value=done):
            with pytest.raises(mod.GhError) as info:
                mod._gh(["api", "x"])
        assert "::" not in str(info.value) and "\n" not in str(info.value)

    def test_success_returns_stdout_and_sets_encoding(self):
        done = subprocess.CompletedProcess(["gh"], 0, stdout="ok", stderr="")
        with patch("subprocess.run", return_value=done) as run:
            assert mod._gh(["api", "x"]) == "ok"
        assert run.call_args.kwargs["encoding"] == "utf-8"

    def test_flatten_accepts_a_flat_list(self):
        assert mod._flatten([{"number": 1}]) == [{"number": 1}]

    def test_flatten_accepts_an_empty_list(self):
        assert mod._flatten([]) == []


class TestWorkflowWiring:
    def _wf(self):
        return yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))

    def test_report_job_is_read_only(self):
        assert self._wf()["jobs"]["report"]["permissions"] == {"contents": "read", "issues": "read"}

    def test_label_job_permissions_are_unchanged(self):
        assert self._wf()["jobs"]["label"]["permissions"] == {"contents": "read", "issues": "write"}

    def test_report_job_runs_after_label_job(self):
        assert self._wf()["jobs"]["report"]["needs"] == "label"

    def test_report_run_step_is_a_single_script_call(self):
        steps = self._wf()["jobs"]["report"]["steps"]
        runs = [s["run"] for s in steps if "run" in s]
        assert len(runs) == 1
        assert runs[0].startswith("python3 .github/scripts/agent_share_breaker_report.py")
        assert "\n" not in runs[0].strip()

    def test_every_action_is_pinned_to_a_40_hex_sha(self):
        uses = re.findall(r"^\s*uses:\s*(\S+)", _WORKFLOW.read_text(encoding="utf-8"), re.MULTILINE)
        assert len(uses) == 2
        assert all(re.fullmatch(r"[\w./-]+@[0-9a-f]{40}", ref) for ref in uses)

    def test_script_never_issues_a_write_call(self):
        source = (_SCRIPTS / "agent_share_breaker_report.py").read_text(encoding="utf-8")
        assert not re.search(r"""["'](-X|--method)["']""", source)
        assert "gh issue" not in source
