"""Tests for get_actionable_items.py notifications paging (issue #7222).

Every gh call is mocked. No test reaches GitHub.
"""

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if _TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script

mod = import_skill_script(".claude/skills/github/scripts/notifications/get_actionable_items.py")

REPO = "owner/repo"


def _proc(stdout="", stderr="", returncode=0):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def _ndjson(count: int) -> str:
    rows = [
        {
            "reason": "subscribed",
            "title": f"n{i}",
            "type": "PullRequest",
            "url": f"https://api.github.com/repos/owner/repo/pulls/{i}",
            "updated_at": "2026-11-10T00:00:00Z",
        }
        for i in range(count)
    ]
    return "\n".join(json.dumps(r) for r in rows)


class TestTryNotifications:
    def test_pages_to_the_end_with_paginate_and_no_slice_in_jq(self):
        with patch.object(mod.subprocess, "run", return_value=_proc(_ndjson(3))) as run:
            items = mod._try_notifications(REPO)

        cmd = run.call_args.args[0]
        assert "--paginate" in cmd
        assert cmd[2] == "notifications?per_page=100"
        # A -f/-F field makes gh api send a POST; this read must stay a GET.
        assert not {"-f", "-F", "--field", "--raw-field", "--method", "-X"} & set(cmd)
        assert len(items) == 3
        jq = cmd[cmd.index("--jq") + 1]
        assert f'"{REPO}"' in jq
        assert ".[:" not in jq

    def test_zero_rows_returns_empty_list_not_none(self):
        with patch.object(mod.subprocess, "run", return_value=_proc("")):
            assert mod._try_notifications(REPO) == []

    def test_returns_every_row_past_one_page(self):
        with patch.object(mod.subprocess, "run", return_value=_proc(_ndjson(250))):
            assert len(mod._try_notifications(REPO)) == 250

    @pytest.mark.parametrize(
        "stderr",
        [
            "gh: Resource not accessible by personal access token (HTTP 403)",
            "HTTP 403: Forbidden",
            'This API operation needs the "notifications" scope.',
        ],
    )
    def test_403_or_missing_scope_means_unavailable(self, stderr):
        with patch.object(mod.subprocess, "run", return_value=_proc(stderr=stderr, returncode=1)):
            assert mod._try_notifications(REPO) is None

    @pytest.mark.parametrize(
        "stderr",
        [
            "HTTP 403: API rate limit exceeded for user ID 1",
            "gh: You have exceeded a secondary rate limit (HTTP 403)",
            "HTTP 429: Too Many Requests",
        ],
    )
    def test_rate_limit_is_an_error_even_when_it_answers_403(self, stderr):
        with patch.object(mod.subprocess, "run", return_value=_proc(stderr=stderr, returncode=1)):
            with pytest.raises(mod.NotificationsError, match="rate limited") as exc:
                mod._try_notifications(REPO)
        assert exc.value.exit_code == 3

    @pytest.mark.parametrize("stderr", ["HTTP 502: Bad Gateway", "HTTP 500: Server Error", "boom"])
    def test_5xx_and_unknown_failures_are_errors(self, stderr):
        with patch.object(mod.subprocess, "run", return_value=_proc(stderr=stderr, returncode=1)):
            with pytest.raises(mod.NotificationsError) as exc:
                mod._try_notifications(REPO)
        assert exc.value.exit_code == 3

    def test_401_is_an_auth_error(self):
        with patch.object(
            mod.subprocess,
            "run",
            return_value=_proc(stderr="HTTP 401: Bad credentials", returncode=1),
        ):
            with pytest.raises(mod.NotificationsError) as exc:
                mod._try_notifications(REPO)
        assert exc.value.exit_code == 4

    def test_timeout_is_an_error(self):
        with patch.object(
            mod.subprocess, "run", side_effect=subprocess.TimeoutExpired(cmd="gh", timeout=180)
        ):
            with pytest.raises(mod.NotificationsError, match="timed out") as exc:
                mod._try_notifications(REPO)
        assert exc.value.exit_code == 3

    def test_invalid_json_is_an_error_not_unavailable(self):
        with patch.object(mod.subprocess, "run", return_value=_proc("not json")):
            with pytest.raises(mod.NotificationsError, match="invalid JSON"):
                mod._try_notifications(REPO)


@pytest.fixture
def main_env():
    """Stub auth, repo resolution, the user lookup, and the three fallback reads."""
    info = type("Info", (), {"owner": "owner", "repo": "repo"})()
    with (
        patch.object(mod, "assert_gh_authenticated"),
        patch.object(mod, "resolve_repo_params", return_value=info),
        patch.object(mod, "_get_current_user", return_value="octocat"),
        patch.object(mod, "_get_review_requests", return_value=[]),
        patch.object(mod, "_get_authored_prs", return_value=[]),
        patch.object(mod, "_get_assigned_issues", return_value=[]),
    ):
        yield


def _data(capsys) -> dict:
    return json.loads(capsys.readouterr().out)


class TestMainNotifications:
    def test_limit_applies_after_paging_and_reports_truncation(self, main_env, capsys):
        rows = [{"title": f"n{i}"} for i in range(75)]
        with patch.object(mod, "_try_notifications", return_value=rows):
            rc = mod.main(["--limit", "20", "--output-format", "json"])

        data = _data(capsys)["Data"]
        assert rc == 0
        assert len(data["notifications"]) == 20
        assert data["notifications_matched"] == 75
        assert data["notifications_truncated"] is True
        assert data["summary"]["notifications"] == 20

    def test_not_truncated_when_matched_equals_limit(self, main_env, capsys):
        rows = [{"title": f"n{i}"} for i in range(20)]
        with patch.object(mod, "_try_notifications", return_value=rows):
            mod.main(["--limit", "20", "--output-format", "json"])

        data = _data(capsys)["Data"]
        assert data["notifications_matched"] == 20
        assert data["notifications_truncated"] is False

    def test_unavailable_api_reports_flag_and_zero_matched(self, main_env, capsys):
        with patch.object(mod, "_try_notifications", return_value=None):
            rc = mod.main(["--output-format", "json"])

        data = _data(capsys)["Data"]
        assert rc == 0
        assert data["notifications_api_available"] is False
        assert data["notifications"] == []
        assert data["notifications_matched"] == 0
        assert data["notifications_truncated"] is False

    def test_rate_limit_exits_3_and_is_not_reported_as_unavailable(self, main_env, capsys):
        err = mod.NotificationsError("Notifications read rate limited: HTTP 429", 3)
        with patch.object(mod, "_try_notifications", side_effect=err):
            rc = mod.main(["--output-format", "json"])

        payload = _data(capsys)
        assert rc == 3
        assert payload["Success"] is False
        assert payload["Error"]["Code"] == 3
        assert "rate limited" in payload["Error"]["Message"]
        assert payload["Data"].get("notifications_api_available") is None

    def test_auth_failure_exits_4(self, main_env, capsys):
        err = mod.NotificationsError("Notifications read failed: HTTP 401", 4)
        with patch.object(mod, "_try_notifications", side_effect=err):
            rc = mod.main(["--output-format", "json"])

        assert rc == 4
        assert _data(capsys)["Error"]["Code"] == 4
