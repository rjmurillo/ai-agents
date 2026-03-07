"""Tests for GitHub milestone skill scripts.

Covers:
- get_latest_semantic_milestone.py
- set_item_milestone.py (in scripts/milestone/)
"""

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from test_helpers import import_skill_script
from github_core.api import RepoInfo


def make_proc(stdout="", stderr="", returncode=0):
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr,
    )


def _mock_repo():
    return RepoInfo(owner="o", repo="r")


def _extract_json(text: str) -> dict:
    """Extract the last JSON object from multi-line output."""
    idx = text.rfind("{")
    if idx == -1:
        raise ValueError(f"No JSON found in output: {text!r}")
    return json.loads(text[idx:])


# ---------------------------------------------------------------------------
# get_latest_semantic_milestone
# ---------------------------------------------------------------------------

class TestGetLatestSemanticMilestone:
    """Tests for get_latest_semantic_milestone.main."""

    def _import(self):
        return import_skill_script("get_latest_semantic_milestone", "milestone")

    def test_happy_path(self, capsys):
        mod = self._import()
        milestones = [
            {"title": "0.1.0", "number": 1},
            {"title": "0.2.0", "number": 2},
            {"title": "0.2.1", "number": 3},
        ]
        with (
            patch("get_latest_semantic_milestone.assert_gh_authenticated"),
            patch("get_latest_semantic_milestone.resolve_repo_params", return_value=_mock_repo()),
            patch("get_latest_semantic_milestone.gh_api_paginated", return_value=milestones),
        ):
            rc = mod.main([])
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert result["found"] is True
        assert result["title"] == "0.2.1"
        assert result["number"] == 3

    def test_no_milestones(self, capsys):
        mod = self._import()
        with (
            patch("get_latest_semantic_milestone.assert_gh_authenticated"),
            patch("get_latest_semantic_milestone.resolve_repo_params", return_value=_mock_repo()),
            patch("get_latest_semantic_milestone.gh_api_paginated", return_value=[]),
        ):
            rc = mod.main([])
        assert rc == 2
        result = json.loads(capsys.readouterr().out)
        assert result["found"] is False
        assert result["title"] == ""

    def test_no_semantic_milestones(self, capsys):
        mod = self._import()
        milestones = [
            {"title": "sprint-1", "number": 1},
            {"title": "release-x", "number": 2},
        ]
        with (
            patch("get_latest_semantic_milestone.assert_gh_authenticated"),
            patch("get_latest_semantic_milestone.resolve_repo_params", return_value=_mock_repo()),
            patch("get_latest_semantic_milestone.gh_api_paginated", return_value=milestones),
        ):
            rc = mod.main([])
        assert rc == 2
        result = json.loads(capsys.readouterr().out)
        assert result["found"] is False

    def test_version_comparison(self, capsys):
        mod = self._import()
        milestones = [
            {"title": "1.0.0", "number": 10},
            {"title": "2.0.0", "number": 20},
            {"title": "1.10.0", "number": 15},
        ]
        with (
            patch("get_latest_semantic_milestone.assert_gh_authenticated"),
            patch("get_latest_semantic_milestone.resolve_repo_params", return_value=_mock_repo()),
            patch("get_latest_semantic_milestone.gh_api_paginated", return_value=milestones),
        ):
            rc = mod.main([])
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert result["title"] == "2.0.0"

    def test_mixed_milestones_filters_correctly(self, capsys):
        mod = self._import()
        milestones = [
            {"title": "v1.0", "number": 1},  # not semver
            {"title": "1.0.0", "number": 2},  # semver
            {"title": "backlog", "number": 3},  # not semver
        ]
        with (
            patch("get_latest_semantic_milestone.assert_gh_authenticated"),
            patch("get_latest_semantic_milestone.resolve_repo_params", return_value=_mock_repo()),
            patch("get_latest_semantic_milestone.gh_api_paginated", return_value=milestones),
        ):
            rc = mod.main([])
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert result["found"] is True
        assert result["title"] == "1.0.0"

    def test_main_exits_2_when_not_found(self):
        mod = self._import()
        with (
            patch("get_latest_semantic_milestone.assert_gh_authenticated"),
            patch("get_latest_semantic_milestone.resolve_repo_params", return_value=_mock_repo()),
            patch("get_latest_semantic_milestone.gh_api_paginated", return_value=[]),
        ):
            rc = mod.main([])
        assert rc == 2

    def test_main_success(self, capsys):
        mod = self._import()
        milestones = [{"title": "1.2.3", "number": 5}]
        with (
            patch("get_latest_semantic_milestone.assert_gh_authenticated"),
            patch("get_latest_semantic_milestone.resolve_repo_params", return_value=_mock_repo()),
            patch("get_latest_semantic_milestone.gh_api_paginated", return_value=milestones),
        ):
            rc = mod.main(["--owner", "o", "--repo", "r"])
        assert rc == 0
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed["found"] is True
        assert parsed["title"] == "1.2.3"

    def test_help_does_not_crash(self):
        mod = import_skill_script("get_latest_semantic_milestone", "milestone")
        with pytest.raises(SystemExit) as exc:
            mod.main(["--help"])
        assert exc.value.code == 0

    def test_parse_semver_tuple(self):
        mod = import_skill_script("get_latest_semantic_milestone", "milestone")
        assert mod._parse_semver_tuple("1.2.3") == (1, 2, 3)
        assert mod._parse_semver_tuple("0.10.0") == (0, 10, 0)


# ---------------------------------------------------------------------------
# set_item_milestone (scripts/milestone/)
# ---------------------------------------------------------------------------

class TestSetItemMilestone:
    """Tests for set_item_milestone.main."""

    def _import(self):
        return import_skill_script("set_item_milestone", "milestone")

    def test_already_has_milestone_skips(self, capsys):
        mod = self._import()
        item_data = {"milestone": {"title": "existing-ms"}}
        with (
            patch("set_item_milestone.assert_gh_authenticated"),
            patch("set_item_milestone.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", return_value=make_proc(stdout=json.dumps(item_data))),
        ):
            rc = mod.main(["--item-type", "pr", "--item-number", "10", "--milestone-title", "existing-ms"])
        assert rc == 0
        result = _extract_json(capsys.readouterr().out)
        assert result["action"] == "skipped"
        assert result["milestone"] == "existing-ms"

    def test_assigns_provided_milestone(self, capsys):
        mod = self._import()
        item_data = {"milestone": None}
        with (
            patch("set_item_milestone.assert_gh_authenticated"),
            patch("set_item_milestone.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", side_effect=[
                make_proc(stdout=json.dumps(item_data)),  # _get_item_milestone
                make_proc(returncode=0),                   # _assign_milestone
            ]),
        ):
            rc = mod.main(["--item-type", "pr", "--item-number", "10", "--milestone-title", "v1.0"])
        assert rc == 0
        result = _extract_json(capsys.readouterr().out)
        assert result["action"] == "assigned"
        assert result["milestone"] == "v1.0"

    def test_auto_detects_milestone_and_assigns(self, capsys):
        mod = self._import()
        item_data = {"milestone": None}
        milestones = [{"title": "0.3.0", "number": 7}]
        with (
            patch("set_item_milestone.assert_gh_authenticated"),
            patch("set_item_milestone.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", side_effect=[
                make_proc(stdout=json.dumps(item_data)),  # _get_item_milestone
                make_proc(returncode=0),                   # _assign_milestone
            ]),
            patch("set_item_milestone.gh_api_paginated", return_value=milestones),
        ):
            rc = mod.main(["--item-type", "issue", "--item-number", "5"])
        assert rc == 0
        result = _extract_json(capsys.readouterr().out)
        assert result["milestone"] == "0.3.0"

    def test_auto_detect_not_found_exits_2(self):
        mod = self._import()
        item_data = {"milestone": None}
        with (
            patch("set_item_milestone.assert_gh_authenticated"),
            patch("set_item_milestone.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", return_value=make_proc(stdout=json.dumps(item_data))),
            patch("set_item_milestone.gh_api_paginated", return_value=[]),
        ):
            rc = mod.main(["--item-type", "pr", "--item-number", "10"])
        assert rc == 2

    def test_api_error_exits_3(self):
        mod = self._import()
        with (
            patch("set_item_milestone.assert_gh_authenticated"),
            patch("set_item_milestone.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", return_value=make_proc(stderr="server error", returncode=1)),
        ):
            with pytest.raises(SystemExit) as exc:
                mod.main(["--item-type", "pr", "--item-number", "10", "--milestone-title", "v1.0"])
        assert exc.value.code == 3

    def test_query_failure_exits_3(self):
        mod = self._import()
        with (
            patch("set_item_milestone.assert_gh_authenticated"),
            patch("set_item_milestone.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", return_value=make_proc(stderr="connection error", returncode=1)),
        ):
            with pytest.raises(SystemExit) as exc:
                mod.main(["--item-type", "pr", "--item-number", "10", "--milestone-title", "v1.0"])
        assert exc.value.code == 3

    def test_help_does_not_crash(self):
        mod = import_skill_script("set_item_milestone", "milestone")
        with pytest.raises(SystemExit) as exc:
            mod.main(["--help"])
        assert exc.value.code == 0
