"""Tests for get_latest_semantic_milestone.py."""

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
for _p in (str(_lib_dir), str(_scripts_dir / "milestone")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from github_core.api import RepoInfo  # noqa: E402


def _mock_repo():
    return RepoInfo(owner="o", repo="r")


@pytest.fixture
def _import_module():
    import importlib
    mod_name = "get_latest_semantic_milestone"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    return importlib.import_module(mod_name)


class TestParseSemverTuple:
    def test_simple_version(self, _import_module):
        mod = _import_module
        assert mod._parse_semver_tuple("1.2.3") == (1, 2, 3)

    def test_zero_version(self, _import_module):
        mod = _import_module
        assert mod._parse_semver_tuple("0.0.0") == (0, 0, 0)

    def test_multi_digit(self, _import_module):
        mod = _import_module
        assert mod._parse_semver_tuple("10.20.30") == (10, 20, 30)


class TestGetLatestSemanticMilestone:
    """Tests for main() via mocked gh_api_paginated."""

    def test_finds_latest(self, _import_module, capsys):
        mod = _import_module
        milestones = [
            {"title": "0.1.0", "number": 1},
            {"title": "0.3.0", "number": 3},
            {"title": "0.2.0", "number": 2},
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
        assert result["title"] == "0.3.0"
        assert result["number"] == 3

    def test_ignores_non_semantic(self, _import_module, capsys):
        mod = _import_module
        milestones = [
            {"title": "Future", "number": 1},
            {"title": "Backlog", "number": 2},
            {"title": "0.2.0", "number": 3},
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
        assert result["title"] == "0.2.0"

    def test_no_milestones(self, _import_module, capsys):
        mod = _import_module
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

    def test_no_semantic_milestones(self, _import_module, capsys):
        mod = _import_module
        milestones = [
            {"title": "Future", "number": 1},
            {"title": "Beta", "number": 2},
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

    def test_version_comparison_10_vs_2(self, _import_module, capsys):
        """Ensure 0.10.0 > 0.2.0 (not string comparison)."""
        mod = _import_module
        milestones = [
            {"title": "0.2.0", "number": 1},
            {"title": "0.10.0", "number": 2},
        ]
        with (
            patch("get_latest_semantic_milestone.assert_gh_authenticated"),
            patch("get_latest_semantic_milestone.resolve_repo_params", return_value=_mock_repo()),
            patch("get_latest_semantic_milestone.gh_api_paginated", return_value=milestones),
        ):
            rc = mod.main([])
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert result["title"] == "0.10.0"

    def test_single_milestone(self, _import_module, capsys):
        mod = _import_module
        milestones = [{"title": "1.0.0", "number": 5}]
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
