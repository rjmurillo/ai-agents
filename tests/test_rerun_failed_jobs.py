"""Tests for rerun_failed_jobs.py: classify, page, dedupe, and rerun failed runs.

HTTP is mocked at the GitHubClient boundary: a fake client answers rest_get and
rest_post from tables and raises a named AssertionError for any endpoint it has
no response for. Each test drives main(argv) and reads the JSON envelope.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from scripts.github_core.api import RepoInfo

_PR_DIR = Path(__file__).resolve().parents[1] / ".claude" / "skills" / "github" / "scripts" / "pr"
SKILL_MD = Path(__file__).resolve().parents[1] / ".claude" / "skills" / "github" / "SKILL.md"


def _import_script():
    spec = importlib.util.spec_from_file_location(
        "rerun_failed_jobs", _PR_DIR / "rerun_failed_jobs.py"
    )
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["rerun_failed_jobs"] = mod
    spec.loader.exec_module(mod)
    return mod


script = _import_script()
_api = sys.modules["github_core.api"]
GhAuthResult = _api.GhAuthResult
GhAuthStatus = _api.GhAuthStatus

HEAD = "a" * 40
CANNOT_RETRY = (
    "gh api POST repos/o/r/actions/runs/{id}/rerun-failed-jobs failed: "
    "Workflow run cannot be retried. (HTTP 403)"
)


def run_obj(run_id: int, status: str = "completed", conclusion: str | None = "failure") -> dict:
    return {
        "id": run_id,
        "name": f"wf-{run_id}",
        "status": status,
        "conclusion": conclusion,
        "html_url": f"https://github.com/o/r/actions/runs/{run_id}",
        "head_sha": HEAD,
    }


def runs_page(runs: list[dict], total: int | None = None) -> dict:
    return {"total_count": len(runs) if total is None else total, "workflow_runs": runs}


class FakeClient:
    """GitHubClient fake. Values that are Exceptions are raised."""

    def __init__(self, gets: dict[str, Any], posts: dict[str, Any] | None = None) -> None:
        self.gets = gets
        self.posts = posts or {}
        self.get_calls: list[str] = []
        self.post_calls: list[tuple[str, dict]] = []

    def rest_get(self, endpoint: str):
        self.get_calls.append(endpoint)
        if endpoint not in self.gets:
            raise AssertionError(f"unexpected GET {endpoint}")
        value = self.gets[endpoint]
        if isinstance(value, Exception):
            raise value
        return value

    def rest_post(self, endpoint: str, payload: dict):
        self.post_calls.append((endpoint, payload))
        if endpoint not in self.posts:
            raise AssertionError(f"unexpected POST {endpoint}")
        value = self.posts[endpoint]
        if isinstance(value, Exception):
            raise value
        return value


PR_ENDPOINT = "repos/o/r/pulls/7"
RUNS_ENDPOINT = f"repos/o/r/actions/runs?head_sha={HEAD}&per_page=100&page="


def pr_fake(
    pages: list[Any],
    posts: dict[str, Any] | None = None,
    state: str = "open",
) -> FakeClient:
    gets: dict[str, Any] = {PR_ENDPOINT: {"state": state, "head": {"sha": HEAD}}}
    for index, page in enumerate(pages, start=1):
        gets[f"{RUNS_ENDPOINT}{index}"] = page
    return FakeClient(gets, posts)


def rerun_ok(run_id: int) -> dict:
    return {f"repos/o/r/actions/runs/{run_id}/rerun-failed-jobs": {}}


def run_main(argv: list[str], client: FakeClient, *, auth: Any = None) -> int:
    auth = auth or GhAuthResult(GhAuthStatus.AUTHENTICATED)
    with (
        patch.object(script, "check_gh_auth", return_value=auth),
        patch.object(script, "resolve_repo_params", return_value=RepoInfo(owner="o", repo="r")),
    ):
        try:
            return script.main([*argv, "--output-format", "json"], client=client)
        except SystemExit as exc:
            assert isinstance(exc.code, int)
            return exc.code


def envelope(capsys) -> dict:
    out = capsys.readouterr().out.strip().splitlines()
    return json.loads(out[-1])


class TestPullRequestRerun:
    def test_reruns_each_failed_run_for_head_sha(self, capsys):
        """Positive: two failed runs and one success; only the failed two rerun."""
        runs = [run_obj(1), run_obj(2, conclusion="success"), run_obj(3, conclusion="timed_out")]
        client = pr_fake([runs_page(runs)], {**rerun_ok(1), **rerun_ok(3)})
        rc = run_main(["--pull-request", "7"], client)
        env = envelope(capsys)
        assert rc == 0
        assert env["Success"] is True
        assert [r["run_id"] for r in env["Data"]["reruns"]] == [1, 3]
        assert env["Data"]["reason"] == "rerun_requested"
        assert env["Data"]["head_sha"] == HEAD
        assert [call[0] for call in client.post_calls] == [
            "repos/o/r/actions/runs/1/rerun-failed-jobs",
            "repos/o/r/actions/runs/3/rerun-failed-jobs",
        ]

    def test_no_failed_runs_exits_zero_without_post(self, capsys):
        client = pr_fake([runs_page([run_obj(1, conclusion="success")])])
        rc = run_main(["--pull-request", "7"], client)
        env = envelope(capsys)
        assert rc == 0
        assert env["Data"]["reason"] == "no_failed_runs"
        assert env["Data"]["reruns"] == []
        assert client.post_calls == []

    def test_empty_run_list_is_no_failed_runs(self, capsys):
        client = pr_fake([runs_page([])])
        assert run_main(["--pull-request", "7"], client) == 0
        assert envelope(capsys)["Data"]["reason"] == "no_failed_runs"

    def test_only_in_progress_runs_exit_one(self, capsys):
        runs = [run_obj(5, status="in_progress", conclusion=None)]
        client = pr_fake([runs_page(runs)])
        rc = run_main(["--pull-request", "7"], client)
        env = envelope(capsys)
        assert rc == 1
        assert env["Data"]["reason"] == "run_in_progress"
        assert env["Data"]["in_progress_runs"][0]["run_id"] == 5
        assert client.post_calls == []

    def test_mixed_failed_and_in_progress_reports_skipped(self, capsys):
        runs = [run_obj(1), run_obj(5, status="queued", conclusion=None)]
        client = pr_fake([runs_page(runs)], rerun_ok(1))
        rc = run_main(["--pull-request", "7"], client)
        env = envelope(capsys)
        assert rc == 0
        assert [r["run_id"] for r in env["Data"]["reruns"]] == [1]
        assert [r["run_id"] for r in env["Data"]["skipped_in_progress"]] == [5]
        assert [r["status"] for r in env["Data"]["skipped_in_progress"]] == ["queued"]

    def test_duplicate_run_ids_across_pages_post_once(self, capsys):
        full = [run_obj(100 + i, conclusion="success") for i in range(99)] + [run_obj(1)]
        page2 = [run_obj(1), run_obj(2)]
        client = pr_fake([runs_page(full, total=101), runs_page(page2, total=101)])
        client.posts.update(rerun_ok(1))
        client.posts.update(rerun_ok(2))
        rc = run_main(["--pull-request", "7"], client)
        env = envelope(capsys)
        assert rc == 0
        assert [r["run_id"] for r in env["Data"]["reruns"]] == [1, 2]
        assert len(client.post_calls) == 2

    def test_unknown_pr_exits_two(self, capsys):
        client = FakeClient({PR_ENDPOINT: RuntimeError("gh api GET failed: Not Found (HTTP 404)")})
        assert run_main(["--pull-request", "7"], client) == 2
        assert envelope(capsys)["Error"]["Type"] == "NotFound"

    def test_pr_without_head_sha_exits_three(self, capsys):
        client = FakeClient({PR_ENDPOINT: {"state": "open", "head": {}}})
        assert run_main(["--pull-request", "7"], client) == 3


class TestPagination:
    def test_second_page_runs_are_included(self, capsys):
        page1 = [run_obj(100 + i, conclusion="success") for i in range(100)]
        page2 = [run_obj(1)]
        client = pr_fake([runs_page(page1, total=101), runs_page(page2, total=101)], rerun_ok(1))
        rc = run_main(["--pull-request", "7"], client)
        assert rc == 0
        assert [r["run_id"] for r in envelope(capsys)["Data"]["reruns"]] == [1]
        assert client.get_calls[-1].endswith("page=2")

    def test_short_final_page_with_missing_runs_fails_loud(self, capsys):
        """total_count says 150 but the walk ends with 100: a gap, never a partial."""
        page1 = [run_obj(100 + i, conclusion="success") for i in range(100)]
        client = pr_fake([runs_page(page1, total=150), runs_page([], total=150)])
        rc = run_main(["--pull-request", "7"], client)
        env = envelope(capsys)
        assert rc == 3
        assert env["Data"]["reason"] == "pagination_incomplete"
        assert client.post_calls == []

    def test_page_cap_fails_loud(self, capsys):
        pages = []
        for n in range(script._MAX_PAGES):
            pages.append(
                runs_page(
                    [run_obj(n * 100 + i + 1, conclusion="success") for i in range(100)],
                    total=10**6,
                )
            )
        client = pr_fake(pages)
        rc = run_main(["--pull-request", "7"], client)
        assert rc == 3
        assert envelope(capsys)["Data"]["reason"] == "pagination_incomplete"

    def test_non_object_page_fails_loud(self, capsys):
        client = pr_fake([[run_obj(1)]])
        assert run_main(["--pull-request", "7"], client) == 3
        assert envelope(capsys)["Data"]["reason"] == "pagination_incomplete"

    def test_missing_total_count_fails_loud(self, capsys):
        client = pr_fake([{"workflow_runs": [run_obj(1)]}])
        assert run_main(["--pull-request", "7"], client) == 3
        assert envelope(capsys)["Data"]["reason"] == "pagination_incomplete"

    def test_list_fetch_error_exits_three(self, capsys):
        client = pr_fake([RuntimeError("gh api GET failed: HTTP 502")])
        assert run_main(["--pull-request", "7"], client) == 3
        assert envelope(capsys)["Error"]["Type"] == "ApiError"


class TestRefusal:
    def test_cannot_be_retried_exits_100_with_fallbacks_and_no_retry(self, capsys):
        client = pr_fake(
            [runs_page([run_obj(9)])],
            {"repos/o/r/actions/runs/9/rerun-failed-jobs": RuntimeError(CANNOT_RETRY.format(id=9))},
        )
        rc = run_main(["--pull-request", "7"], client)
        captured = capsys.readouterr()
        env = json.loads(captured.out.strip().splitlines()[-1])
        assert rc == 100
        assert env["Error"]["Code"] == 100
        assert env["Data"]["reason"] == "cannot_be_retried"
        assert env["Data"]["refused"][0]["run_id"] == 9
        assert len(client.post_calls) == 1, "authoritative refusal must not be retried"
        fallbacks = " ".join(env["Data"]["fallbacks"])
        assert "origin/main" in fallbacks
        assert "empty commit" in fallbacks
        assert "human" in fallbacks
        assert "[FALLBACK]" in captured.err

    @pytest.mark.parametrize(
        "text",
        [
            "run 40713397099 cannot be rerun; This workflow run cannot be retried",
            "gh: Cannot be RETRIED (HTTP 403)",
            "This workflow run cannot be re-run",
        ],
    )
    def test_refusal_markers(self, text):
        assert script.is_cannot_retry_refusal(text) is True

    @pytest.mark.parametrize(
        "text",
        [
            "",
            "HTTP 502 Bad Gateway",
            "Resource not accessible by integration",
            "Not Found (HTTP 404)",
        ],
    )
    def test_non_refusal_text_is_not_classified(self, text):
        assert script.is_cannot_retry_refusal(text) is False

    def test_refusal_on_one_run_still_reruns_the_others(self, capsys):
        client = pr_fake(
            [runs_page([run_obj(1), run_obj(2)])],
            {
                "repos/o/r/actions/runs/1/rerun-failed-jobs": RuntimeError(
                    CANNOT_RETRY.format(id=1)
                ),
                **rerun_ok(2),
            },
        )
        rc = run_main(["--pull-request", "7"], client)
        env = envelope(capsys)
        assert rc == 100
        assert [r["run_id"] for r in env["Data"]["reruns"]] == [2]
        assert [r["run_id"] for r in env["Data"]["refused"]] == [1]

    def test_other_api_error_exits_three(self, capsys):
        client = pr_fake(
            [runs_page([run_obj(1)])],
            {"repos/o/r/actions/runs/1/rerun-failed-jobs": RuntimeError("failed: HTTP 500")},
        )
        assert run_main(["--pull-request", "7"], client) == 3
        assert envelope(capsys)["Error"]["Type"] == "ApiError"

    def test_post_timeout_exits_three_outcome_unknown(self, capsys):
        client = pr_fake(
            [runs_page([run_obj(1)])],
            {"repos/o/r/actions/runs/1/rerun-failed-jobs": subprocess.TimeoutExpired("gh", 30)},
        )
        rc = run_main(["--pull-request", "7"], client)
        env = envelope(capsys)
        assert rc == 3
        assert env["Error"]["Type"] == "Timeout"
        assert "unknown" in env["Error"]["Message"]


class TestAuth:
    def test_preflight_auth_failure_exits_four_without_api_calls(self, capsys):
        client = pr_fake([])
        auth = GhAuthResult(GhAuthStatus.INVALID_CREDENTIALS, "bad token")
        assert run_main(["--pull-request", "7"], client, auth=auth) == 4
        assert client.get_calls == []

    def test_post_auth_error_exits_four(self, capsys):
        client = pr_fake(
            [runs_page([run_obj(1)])],
            {
                "repos/o/r/actions/runs/1/rerun-failed-jobs": RuntimeError(
                    "Resource not accessible by integration (HTTP 403)"
                )
            },
        )
        assert run_main(["--pull-request", "7"], client) == 4
        assert envelope(capsys)["Error"]["Type"] == "AuthError"

    def test_pr_lookup_auth_error_exits_four(self, capsys):
        client = FakeClient({PR_ENDPOINT: RuntimeError("Bad credentials (HTTP 401)")})
        assert run_main(["--pull-request", "7"], client) == 4


class TestRunId:
    def test_reruns_completed_failed_run(self, capsys):
        client = FakeClient({"repos/o/r/actions/runs/42": run_obj(42)}, rerun_ok(42))
        rc = run_main(["--run-id", "42"], client)
        env = envelope(capsys)
        assert rc == 0
        assert env["Data"]["reruns"][0]["run_id"] == 42
        assert env["Data"]["reruns"][0]["action"] == "rerun_failed_jobs"

    def test_in_progress_run_exits_one_and_reports_status(self, capsys):
        client = FakeClient({"repos/o/r/actions/runs/42": run_obj(42, "in_progress", None)})
        rc = run_main(["--run-id", "42"], client)
        env = envelope(capsys)
        assert rc == 1
        assert env["Data"]["reason"] == "run_in_progress"
        assert env["Data"]["run_status"] == "in_progress"
        assert client.post_calls == []

    def test_successful_run_is_no_failed_runs(self, capsys):
        client = FakeClient({"repos/o/r/actions/runs/42": run_obj(42, conclusion="success")})
        assert run_main(["--run-id", "42"], client) == 0
        assert envelope(capsys)["Data"]["reason"] == "no_failed_runs"
        assert client.post_calls == []

    def test_missing_run_exits_two(self, capsys):
        client = FakeClient({"repos/o/r/actions/runs/42": RuntimeError("Not Found (HTTP 404)")})
        assert run_main(["--run-id", "42"], client) == 2

    def test_run_refusal_exits_100(self, capsys):
        client = FakeClient(
            {"repos/o/r/actions/runs/42": run_obj(42)},
            {
                "repos/o/r/actions/runs/42/rerun-failed-jobs": RuntimeError(
                    CANNOT_RETRY.format(id=42)
                )
            },
        )
        assert run_main(["--run-id", "42"], client) == 100

    def test_job_id_reruns_one_job(self, capsys):
        client = FakeClient(
            {"repos/o/r/actions/runs/42": run_obj(42)},
            {"repos/o/r/actions/jobs/77/rerun": {}},
        )
        rc = run_main(["--run-id", "42", "--job-id", "77"], client)
        env = envelope(capsys)
        assert rc == 0
        assert env["Data"]["reruns"][0]["job_id"] == 77
        assert env["Data"]["reruns"][0]["action"] == "rerun_job"
        assert [c[0] for c in client.post_calls] == ["repos/o/r/actions/jobs/77/rerun"]

    def test_job_rerun_on_in_progress_run_exits_one(self, capsys):
        client = FakeClient({"repos/o/r/actions/runs/42": run_obj(42, "queued", None)})
        assert run_main(["--run-id", "42", "--job-id", "77"], client) == 1
        assert client.post_calls == []


class TestArguments:
    def test_requires_pull_request_or_run_id(self, capsys):
        assert run_main([], FakeClient({})) == 1

    def test_rejects_both_pull_request_and_run_id(self, capsys):
        assert run_main(["--pull-request", "7", "--run-id", "42"], FakeClient({})) == 1

    def test_job_id_requires_run_id(self, capsys):
        assert run_main(["--pull-request", "7", "--job-id", "77"], FakeClient({})) == 1
        assert envelope(capsys)["Error"]["Type"] == "InvalidParams"

    @pytest.mark.parametrize("flag", ["--pull-request", "--run-id"])
    def test_rejects_non_positive_ids(self, flag, capsys):
        assert run_main([flag, "0"], FakeClient({})) == 1


class TestDocumentation:
    def test_script_is_listed_in_skill_md(self):
        assert "rerun_failed_jobs.py" in SKILL_MD.read_text(encoding="utf-8")
