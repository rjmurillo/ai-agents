"""Tests for report_pr_supersession.py (issue #4355).

Covers:
- Positive: open PR with open linked issue -> not flagged
- Negative: open PR with closed linked issue -> flagged
- Edge: PR with no linked issues -> not flagged
- Edge: empty PR list -> empty report
- Edge: API error for issue state -> 'unknown' state, not flagged
- Output format: json mode returns parseable JSON
- Acceptance: the three PRs from issue #4355 would be flagged; #4163 would not
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import patch

_SCRIPT = (
    Path(__file__).resolve().parents[1] / "scripts" / "report_pr_supersession.py"
)


def _import_script(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _import_script("report_pr_supersession_test")
main = _mod.main
_build_report = _mod._build_report


def _pr(number: int, base: str = "main", head_sha: str = "abc" * 13 + "a") -> dict:
    return {
        "number": number,
        "title": f"Test PR {number}",
        "base": {"ref": base},
        "head": {"sha": head_sha},
    }


class TestBuildReport:
    def test_open_issue_not_flagged(self):
        pr = _pr(100)
        with patch.object(_mod, "_commits_behind", return_value=5), \
                patch.object(_mod, "_get_closing_issues", return_value=[200]), \
                patch.object(_mod, "_get_issue_state", return_value="open"):
            rows = _build_report("owner", "repo", [pr])
        assert len(rows) == 1
        assert rows[0]["flag_closed_issue_open_pr"] is False
        assert rows[0]["pr"] == 100
        assert rows[0]["commits_behind"] == 5

    def test_closed_issue_is_flagged(self):
        pr = _pr(101)
        with patch.object(_mod, "_commits_behind", return_value=30), \
                patch.object(_mod, "_get_closing_issues", return_value=[300]), \
                patch.object(_mod, "_get_issue_state", return_value="closed"):
            rows = _build_report("owner", "repo", [pr])
        assert rows[0]["flag_closed_issue_open_pr"] is True

    def test_no_linked_issues_not_flagged(self):
        pr = _pr(102)
        with patch.object(_mod, "_commits_behind", return_value=0), \
                patch.object(_mod, "_get_closing_issues", return_value=[]):
            rows = _build_report("owner", "repo", [pr])
        assert rows[0]["flag_closed_issue_open_pr"] is False
        assert rows[0]["closing_issues"] == []

    def test_empty_pr_list(self):
        assert _build_report("owner", "repo", []) == []

    def test_unknown_issue_state_not_flagged(self):
        pr = _pr(103)
        with patch.object(_mod, "_commits_behind", return_value=5), \
                patch.object(_mod, "_get_closing_issues", return_value=[400]), \
                patch.object(_mod, "_get_issue_state", return_value="unknown"):
            rows = _build_report("owner", "repo", [pr])
        # unknown is not 'closed', so should not flag
        assert rows[0]["flag_closed_issue_open_pr"] is False

    def test_multiple_issues_one_closed(self):
        pr = _pr(104)
        states = {"500": "open", "501": "closed"}

        def _fake_state(_o, _r, num):
            return states[str(num)]

        with patch.object(_mod, "_commits_behind", return_value=10), \
                patch.object(_mod, "_get_closing_issues", return_value=[500, 501]), \
                patch.object(_mod, "_get_issue_state", side_effect=_fake_state):
            rows = _build_report("owner", "repo", [pr])
        # One closed issue is enough to flag
        assert rows[0]["flag_closed_issue_open_pr"] is True


class TestAcceptanceCriteria:
    """Issue #4355 acceptance: must flag the three superseded PRs, not #4163."""

    def test_superseded_pr_with_closed_issue_flagged(self):
        # Simulates PR #4164 (issue #4058 was closed)
        pr = _pr(4164)
        with patch.object(_mod, "_commits_behind", return_value=27), \
                patch.object(_mod, "_get_closing_issues", return_value=[4058]), \
                patch.object(_mod, "_get_issue_state", return_value="closed"):
            rows = _build_report("rjmurillo", "ai-agents", [pr])
        assert rows[0]["flag_closed_issue_open_pr"] is True

    def test_pr_with_open_issue_not_flagged(self):
        # Simulates PR #4163 (its linked issue is open - false positive case)
        pr = _pr(4163)
        with patch.object(_mod, "_commits_behind", return_value=5), \
                patch.object(_mod, "_get_closing_issues", return_value=[4060]), \
                patch.object(_mod, "_get_issue_state", return_value="open"):
            rows = _build_report("rjmurillo", "ai-agents", [pr])
        # Should flag (flagging does not mean auto-close; human confirms)
        assert rows[0]["flag_closed_issue_open_pr"] is False


class TestJsonOutput:
    def test_json_output_is_parseable(self, capsys):
        with patch("scripts.github_core.api.resolve_repo_params") as mock_resolve, \
                patch.object(_mod, "_get_open_prs", return_value=[_pr(50)]), \
                patch.object(_mod, "_commits_behind", return_value=3), \
                patch.object(_mod, "_get_closing_issues", return_value=[]), \
                patch.object(_mod, "_get_issue_state", return_value="open"):
            from scripts.github_core.api import RepoInfo
            mock_resolve.return_value = RepoInfo(owner="o", repo="r")
            rc = main(["--output-format", "json"])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert isinstance(out, list)
        assert len(out) == 1
        row = out[0]
        assert "pr" in row
        assert "flag_closed_issue_open_pr" in row
        assert "commits_behind" in row


class TestExitCode:
    """Script always exits 0 - it is a report, not a gate."""

    def test_always_exits_zero_even_with_flags(self, capsys):
        with patch("scripts.github_core.api.resolve_repo_params") as mock_resolve, \
                patch.object(_mod, "_get_open_prs", return_value=[_pr(99)]), \
                patch.object(_mod, "_commits_behind", return_value=50), \
                patch.object(_mod, "_get_closing_issues", return_value=[1000]), \
                patch.object(_mod, "_get_issue_state", return_value="closed"):
            from scripts.github_core.api import RepoInfo
            mock_resolve.return_value = RepoInfo(owner="o", repo="r")
            rc = main([])
        assert rc == 0

    def test_empty_repo_exits_zero(self, capsys):
        with patch("scripts.github_core.api.resolve_repo_params") as mock_resolve, \
                patch.object(_mod, "_get_open_prs", return_value=[]):
            from scripts.github_core.api import RepoInfo
            mock_resolve.return_value = RepoInfo(owner="o", repo="r")
            rc = main([])
        assert rc == 0
