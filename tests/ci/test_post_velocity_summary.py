"""Tests for scripts/ci/post_velocity_summary.py."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import scripts.ci.post_velocity_summary as pvs

# ---------------------------------------------------------------------------
# build_summary
# ---------------------------------------------------------------------------


def test_build_summary_empty():
    assert pvs.build_summary([]) == ""


def test_build_summary_single_opportunity():
    opp = {
        "title": "Fix flaky tests",
        "opportunity_type": "quality",
        "priority": "high",
        "description": "Tests fail intermittently.",
        "suggested_agent": "qa-agent",
    }
    result = pvs.build_summary([opp])
    assert "## Velocity Accelerator: 1 Opportunities Detected" in result
    assert "### Fix flaky tests" in result
    assert "**Type**: `quality`" in result
    assert "**Priority**: high" in result
    assert "**Suggested Agent**: qa-agent" in result
    assert "Tests fail intermittently." in result
    assert pvs._MARKER in result


def test_build_summary_no_suggested_agent():
    opp = {
        "title": "T",
        "opportunity_type": "perf",
        "priority": "low",
        "description": "D",
    }
    result = pvs.build_summary([opp])
    assert "Suggested Agent" not in result


def test_build_summary_multiple():
    opps = [
        {"title": "A", "opportunity_type": "t1", "priority": "p1", "description": "d1"},
        {"title": "B", "opportunity_type": "t2", "priority": "p2", "description": "d2"},
    ]
    result = pvs.build_summary(opps)
    assert "2 Opportunities Detected" in result
    assert "### A" in result
    assert "### B" in result


def test_build_summary_marker_present():
    opp = {"title": "X", "opportunity_type": "y", "priority": "z", "description": "d"}
    result = pvs.build_summary([opp])
    assert result.endswith(pvs._MARKER)


# ---------------------------------------------------------------------------
# find_existing_comment - found on first page
# ---------------------------------------------------------------------------


def test_find_existing_comment_found():
    page1 = json.dumps([{"id": 99, "body": f"text {pvs._MARKER}"}])
    mock_result = MagicMock(returncode=0, stdout=page1)
    with patch("scripts.ci.post_velocity_summary.subprocess.run", return_value=mock_result):
        cid = pvs.find_existing_comment("owner/repo", "5")
    assert cid == 99


def test_find_existing_comment_not_found():
    page1 = json.dumps([{"id": 1, "body": "no marker here"}])
    empty = json.dumps([])
    results = [
        MagicMock(returncode=0, stdout=page1),
        MagicMock(returncode=0, stdout=empty),
    ]
    with patch("scripts.ci.post_velocity_summary.subprocess.run", side_effect=results):
        cid = pvs.find_existing_comment("owner/repo", "5")
    assert cid is None


def test_find_existing_comment_api_error():
    mock_result = MagicMock(returncode=1, stdout="")
    with patch("scripts.ci.post_velocity_summary.subprocess.run", return_value=mock_result):
        cid = pvs.find_existing_comment("owner/repo", "5")
    assert cid is None


def test_find_existing_comment_bad_json():
    mock_result = MagicMock(returncode=0, stdout="not-json")
    with patch("scripts.ci.post_velocity_summary.subprocess.run", return_value=mock_result):
        cid = pvs.find_existing_comment("owner/repo", "5")
    assert cid is None


# ---------------------------------------------------------------------------
# post_comment - create new
# ---------------------------------------------------------------------------


def test_post_comment_create_new():
    mock_result = MagicMock(returncode=0)
    _patch = "scripts.ci.post_velocity_summary.subprocess.run"
    with patch(_patch, return_value=mock_result) as mock_run:
        rc = pvs.post_comment("owner/repo", "10", "body text", None)
    assert rc == 0
    cmd = mock_run.call_args[0][0]
    assert "issues/10/comments" in " ".join(cmd)


def test_post_comment_update_existing():
    mock_result = MagicMock(returncode=0)
    _patch = "scripts.ci.post_velocity_summary.subprocess.run"
    with patch(_patch, return_value=mock_result) as mock_run:
        rc = pvs.post_comment("owner/repo", "10", "body text", 77)
    assert rc == 0
    cmd = mock_run.call_args[0][0]
    assert "comments/77" in " ".join(cmd)
    assert "-X" in cmd
    assert "PATCH" in cmd


def test_post_comment_failure_propagated():
    mock_result = MagicMock(returncode=1)
    with patch("scripts.ci.post_velocity_summary.subprocess.run", return_value=mock_result):
        rc = pvs.post_comment("owner/repo", "10", "body", None)
    assert rc == 1


# ---------------------------------------------------------------------------
# main - config error (GITHUB_REPOSITORY missing)
# ---------------------------------------------------------------------------


def test_main_missing_repo(monkeypatch):
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    assert pvs.main() == pvs.EXIT_CONFIG


# ---------------------------------------------------------------------------
# main - no opportunities (empty JSON)
# ---------------------------------------------------------------------------


def test_main_no_opportunities(monkeypatch):
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("OPPORTUNITIES_JSON", "[]")
    assert pvs.main() == pvs.EXIT_SUCCESS


# ---------------------------------------------------------------------------
# main - no number available
# ---------------------------------------------------------------------------


def test_main_no_number(monkeypatch):
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("EVENT_NAME", "push")
    monkeypatch.setenv("PR_NUMBER", "")
    monkeypatch.setenv("ISSUE_NUMBER", "")
    opp = {"title": "T", "opportunity_type": "x", "priority": "p", "description": "d"}
    monkeypatch.setenv("OPPORTUNITIES_JSON", json.dumps([opp]))
    assert pvs.main() == pvs.EXIT_SUCCESS


# ---------------------------------------------------------------------------
# main - gh API failure
# ---------------------------------------------------------------------------


def test_main_gh_api_failure(monkeypatch):
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("EVENT_NAME", "pull_request")
    monkeypatch.setenv("PR_NUMBER", "3")
    monkeypatch.setenv("ISSUE_NUMBER", "")
    opps = [{"title": "T", "opportunity_type": "x", "priority": "p", "description": "d"}]
    monkeypatch.setenv("OPPORTUNITIES_JSON", json.dumps(opps))

    # find returns None, post fails
    find_result = MagicMock(returncode=0, stdout=json.dumps([]))
    post_result = MagicMock(returncode=1)
    _patch = "scripts.ci.post_velocity_summary.subprocess.run"
    with patch(_patch, side_effect=[find_result, post_result]):
        rc = pvs.main()
    assert rc == pvs.EXIT_EXTERNAL


# ---------------------------------------------------------------------------
# main - success: creates new comment on PR
# ---------------------------------------------------------------------------


def test_main_success_pr(monkeypatch):
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("EVENT_NAME", "pull_request")
    monkeypatch.setenv("PR_NUMBER", "7")
    monkeypatch.setenv("ISSUE_NUMBER", "")
    opps = [{"title": "T", "opportunity_type": "x", "priority": "p", "description": "d"}]
    monkeypatch.setenv("OPPORTUNITIES_JSON", json.dumps(opps))

    empty_page = MagicMock(returncode=0, stdout=json.dumps([]))
    post_ok = MagicMock(returncode=0)
    _patch = "scripts.ci.post_velocity_summary.subprocess.run"
    with patch(_patch, side_effect=[empty_page, post_ok]):
        rc = pvs.main()
    assert rc == pvs.EXIT_SUCCESS


# ---------------------------------------------------------------------------
# main - success: updates existing comment on issue
# ---------------------------------------------------------------------------


def test_main_success_issue_update(monkeypatch):
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("EVENT_NAME", "issues")
    monkeypatch.setenv("PR_NUMBER", "")
    monkeypatch.setenv("ISSUE_NUMBER", "12")
    opps = [{"title": "T", "opportunity_type": "x", "priority": "p", "description": "d"}]
    monkeypatch.setenv("OPPORTUNITIES_JSON", json.dumps(opps))

    existing_page = MagicMock(returncode=0, stdout=json.dumps([{"id": 55, "body": pvs._MARKER}]))
    patch_ok = MagicMock(returncode=0)
    _patch = "scripts.ci.post_velocity_summary.subprocess.run"
    with patch(_patch, side_effect=[existing_page, patch_ok]) as mock_run:
        rc = pvs.main()
    assert rc == pvs.EXIT_SUCCESS
    # Verify PATCH call references the existing comment id
    patch_call_cmd = mock_run.call_args_list[-1][0][0]
    assert "comments/55" in " ".join(patch_call_cmd)
    assert "-X" in patch_call_cmd
    assert "PATCH" in patch_call_cmd


# ---------------------------------------------------------------------------
# main - invalid/non-list JSON falls back to empty
# ---------------------------------------------------------------------------


def test_main_invalid_json_opportunities(monkeypatch):
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("OPPORTUNITIES_JSON", "not-valid-json")
    assert pvs.main() == pvs.EXIT_SUCCESS
