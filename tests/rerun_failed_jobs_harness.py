"""Shared loader and fakes for the rerun_failed_jobs.py tests.

HTTP is mocked at the GitHubClient boundary: a fake client answers rest_get and
rest_post from tables and raises a named AssertionError for any endpoint it has
no response for. Each test drives main(argv) and reads the JSON envelope.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

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
        "workflow_id": run_id,
        "event": "pull_request",
        "run_number": run_id,
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


JOB_77 = "repos/o/r/actions/jobs/77"
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
