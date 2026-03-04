"""Tests for set_item_milestone.py."""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from test_helpers import import_skill_script
from github_core.api import RepoInfo
from test_helpers import make_completed_process


def _mock_repo():
    return RepoInfo(owner="o", repo="r")


def _extract_json(text: str) -> dict:
    """Extract the last JSON object from multi-line output."""
    idx = text.rfind("{")
    if idx == -1:
        raise ValueError(f"No JSON found in output: {text!r}")
    return json.loads(text[idx:])


@pytest.fixture
def _import_module():
    return import_skill_script("set_item_milestone", "milestone")


class TestGetItemMilestone:
    """Tests for _get_item_milestone helper."""

    def test_has_milestone(self, _import_module):
        mod = _import_module
        item_data = {"milestone": {"title": "v1.0.0"}}
        with patch("subprocess.run", return_value=make_completed_process(
            stdout=json.dumps(item_data)
        )):
            result = mod._get_item_milestone("o", "r", 1)
        assert result == "v1.0.0"

    def test_no_milestone(self, _import_module):
        mod = _import_module
        item_data = {"milestone": None}
        with patch("subprocess.run", return_value=make_completed_process(
            stdout=json.dumps(item_data)
        )):
            result = mod._get_item_milestone("o", "r", 1)
        assert result is None


class TestSetItemMilestone:
    """Tests for set_item_milestone.main."""

    def test_skip_when_has_milestone(self, _import_module, capsys):
        mod = _import_module
        item_data = {"milestone": {"title": "v0.9.0"}}
        with (
            patch("set_item_milestone.assert_gh_authenticated"),
            patch("set_item_milestone.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", return_value=make_completed_process(
                stdout=json.dumps(item_data)
            )),
        ):
            rc = mod.main(["--item-type", "pr", "--item-number", "1"])
        assert rc == 0
        result = _extract_json(capsys.readouterr().out)
        assert result["action"] == "skipped"
        assert result["milestone"] == "v0.9.0"

    def test_assign_with_explicit_title(self, _import_module, capsys):
        mod = _import_module
        item_data = {"milestone": None}
        with (
            patch("set_item_milestone.assert_gh_authenticated"),
            patch("set_item_milestone.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", side_effect=[
                make_completed_process(stdout=json.dumps(item_data)),  # _get_item_milestone
                make_completed_process(),                               # _assign_milestone
            ]),
        ):
            rc = mod.main(["--item-type", "issue", "--item-number", "42", "--milestone-title", "v1.0.0"])
        assert rc == 0
        result = _extract_json(capsys.readouterr().out)
        assert result["success"] is True
        assert result["action"] == "assigned"
        assert result["milestone"] == "v1.0.0"

    def test_api_error_exits_3(self, _import_module):
        mod = _import_module
        with (
            patch("set_item_milestone.assert_gh_authenticated"),
            patch("set_item_milestone.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", return_value=make_completed_process(
                returncode=1, stderr="api error"
            )),
        ):
            with pytest.raises(SystemExit) as exc:
                mod.main(["--item-type", "pr", "--item-number", "1", "--milestone-title", "v1.0.0"])
        assert exc.value.code == 3

    def test_query_failure_exits_3(self, _import_module):
        mod = _import_module
        with patch("subprocess.run", return_value=make_completed_process(
            returncode=1, stderr="fail"
        )):
            with pytest.raises(SystemExit) as exc:
                mod._get_item_milestone("o", "r", 999)
        assert exc.value.code == 3
