"""Tests for add_comment_reaction.py --dry-run."""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from test_helpers import make_completed_process

# Ensure importability
_project_root = Path(__file__).resolve().parents[3]
_lib_dir = _project_root / ".claude" / "lib"
_scripts_dir = _project_root / ".claude" / "skills" / "github" / "scripts"
for _p in (str(_lib_dir), str(_scripts_dir / "reactions")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from github_core.api import RepoInfo


def _mock_repo():
    return RepoInfo(owner="o", repo="r")


_UNRESOLVED_STATE = {
    "pull_request": 42,
    "thread_id": "PRRT_abc",
    "is_resolved": False,
}


@pytest.fixture
def _import_module():
    import importlib

    mod_name = "add_comment_reaction"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    return importlib.import_module(mod_name)


class TestDryRun:
    """Tests for add_comment_reaction.main --dry-run."""

    def test_dry_run_posts_no_reaction_and_reports_would_add(self, _import_module, capsys):
        mod = _import_module
        with (
            patch("add_comment_reaction.assert_gh_authenticated"),
            patch("add_comment_reaction.resolve_repo_params", return_value=_mock_repo()),
            patch(
                "add_comment_reaction.query_review_comment_thread_state",
                return_value=_UNRESOLVED_STATE,
            ),
            patch("subprocess.run") as run,
        ):
            rc = mod.main(["--comment-id", "1", "2", "--reaction", "eyes", "--dry-run"])
        result = json.loads(capsys.readouterr().out)
        assert rc == 0
        assert run.call_count == 0
        assert result["Data"]["dry_run"] is True
        assert result["Data"]["would_add"] == 2
        assert result["Data"]["succeeded"] == 0
        assert {r["reason"] for r in result["Data"]["results"]} == {"dry_run"}

    def test_dry_run_still_skips_a_resolved_thread(self, _import_module, capsys):
        mod = _import_module
        resolved = {**_UNRESOLVED_STATE, "is_resolved": True}
        with (
            patch("add_comment_reaction.assert_gh_authenticated"),
            patch("add_comment_reaction.resolve_repo_params", return_value=_mock_repo()),
            patch(
                "add_comment_reaction.query_review_comment_thread_state",
                return_value=resolved,
            ),
            patch("subprocess.run") as run,
        ):
            rc = mod.main(["--comment-id", "1", "--reaction", "eyes", "--dry-run"])
        result = json.loads(capsys.readouterr().out)
        assert rc == 0
        assert run.call_count == 0
        assert result["Data"]["would_add"] == 0
        assert result["Data"]["skipped"] == 1

    def test_dry_run_issue_comment_makes_no_calls_and_says_so_in_human_output(
        self, _import_module, capsys
    ):
        mod = _import_module
        with (
            patch("add_comment_reaction.assert_gh_authenticated"),
            patch("add_comment_reaction.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run") as run,
        ):
            rc = mod.main(
                [
                    "--comment-id",
                    "9",
                    "--comment-type",
                    "issue",
                    "--reaction",
                    "+1",
                    "--dry-run",
                    "--output-format",
                    "human",
                ]
            )
        assert rc == 0
        assert run.call_count == 0
        out = capsys.readouterr().out
        assert "Dry run: would apply '+1' to 1 comment(s)" in out
        assert "Applied" not in out

    def test_default_run_has_no_dry_run_key(self, _import_module, capsys):
        mod = _import_module
        with (
            patch("add_comment_reaction.assert_gh_authenticated"),
            patch("add_comment_reaction.resolve_repo_params", return_value=_mock_repo()),
            patch(
                "subprocess.run", return_value=make_completed_process(stdout=json.dumps({"id": 1}))
            ),
        ):
            rc = mod.main(["--comment-id", "9", "--comment-type", "issue", "--reaction", "eyes"])
        assert rc == 0
        assert "dry_run" not in json.loads(capsys.readouterr().out)["Data"]
