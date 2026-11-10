"""new_issue.py reports an issue a timed-out create may have made (issue #7230).

Every gh call is mocked. The create is never retried.
"""

import json
import subprocess
from datetime import datetime, timedelta, timezone

import pytest

from .new_issue_harness import (
    FakeGh,
    _make_proc,
    _run,
    resolve_repo_fixture,  # noqa: F401  (autouse fixture)
)

BASE = ["--title", "Exact title", "--source", "human"]
TIMEOUT = subprocess.TimeoutExpired(cmd="gh", timeout=30)


def _iso(delta_seconds: float) -> str:
    when = datetime.now(timezone.utc) - timedelta(seconds=delta_seconds)
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


def _row(number=77, title="Exact title", age=20.0):
    return {
        "number": number,
        "title": title,
        "url": f"https://github.com/owner/repo/issues/{number}",
        "createdAt": _iso(age),
    }


def _gh(list_route) -> FakeGh:
    return FakeGh(extra_routes={("issue", "create"): TIMEOUT, ("issue", "list"): list_route})


def _payload(capsys) -> dict:
    return json.loads(capsys.readouterr().out)


class TestCreateTimeoutLookup:
    def test_found_issue_is_named_in_the_error(self, capsys):
        gh = _gh(_make_proc(stdout=json.dumps([_row()])))

        rc, _ = _run(BASE, gh)

        payload = _payload(capsys)
        assert rc == 3
        assert payload["Error"]["Type"] == "Timeout"
        assert payload["Data"]["existing_issue"] == {
            "number": 77,
            "url": "https://github.com/owner/repo/issues/77",
        }
        assert "#77" in payload["Error"]["Message"]
        assert "Do not retry" in payload["Error"]["Message"]

    def test_lookup_is_read_only_scoped_to_current_user_and_run_once(self):
        gh = _gh(_make_proc(stdout="[]"))

        _run(BASE, gh)

        lookups = [c for c in gh.calls if c[1:3] == ["issue", "list"]]
        assert len(lookups) == 1
        assert lookups[0][lookups[0].index("--author") + 1] == "@me"
        assert "--state" in lookups[0]

    def test_create_is_never_retried(self):
        gh = _gh(_make_proc(stdout=json.dumps([_row()])))

        _run(BASE, gh)

        assert len([c for c in gh.calls if c[1:3] == ["issue", "create"]]) == 1
        assert ("issue", "edit") not in gh.verbs()

    def test_no_match_reports_plain_timeout(self, capsys):
        gh = _gh(_make_proc(stdout="[]"))

        rc, _ = _run(BASE, gh)

        payload = _payload(capsys)
        assert rc == 3
        assert payload["Error"]["Type"] == "Timeout"
        assert "existing_issue" not in (payload["Data"] or {})
        assert payload["Error"]["Message"] == "gh issue create timed out after 30s"

    @pytest.mark.parametrize(
        "rows",
        [
            [_row(title="Exact title with more words")],
            [_row(title="exact title")],
            [_row(age=7200)],
        ],
        ids=["different-title", "different-case", "too-old"],
    )
    def test_non_matching_rows_are_ignored(self, rows, capsys):
        gh = _gh(_make_proc(stdout=json.dumps(rows)))

        rc, _ = _run(BASE, gh)

        assert rc == 3
        assert "existing_issue" not in (_payload(capsys)["Data"] or {})

    def test_newest_match_wins(self, capsys):
        rows = [_row(number=10, age=300), _row(number=11, age=15)]
        gh = _gh(_make_proc(stdout=json.dumps(rows)))

        _run(BASE, gh)

        assert _payload(capsys)["Data"]["existing_issue"]["number"] == 11

    @pytest.mark.parametrize(
        "route",
        [
            _make_proc(returncode=1, stderr="HTTP 502"),
            _make_proc(stdout="not json"),
            _make_proc(stdout='{"not": "a list"}'),
            TIMEOUT,
            OSError("gh vanished"),
        ],
        ids=["gh-fails", "bad-json", "not-a-list", "lookup-times-out", "os-error"],
    )
    def test_lookup_failure_keeps_the_timeout_error(self, route, capsys):
        gh = _gh(route)

        rc, _ = _run(BASE, gh)

        payload = _payload(capsys)
        assert rc == 3
        assert payload["Error"]["Type"] == "Timeout"
        assert "existing_issue" not in (payload["Data"] or {})

    def test_title_quotes_do_not_break_the_search_argument(self):
        row = _row(title='Say "hi"')
        gh = _gh(_make_proc(stdout=json.dumps([row])))

        _run(["--title", 'Say "hi"', "--source", "human"], gh)

        lookup = next(c for c in gh.calls if c[1:3] == ["issue", "list"])
        search = lookup[lookup.index("--search") + 1]
        assert search == '"Say  hi " in:title'
