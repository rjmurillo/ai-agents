"""Tests for get_latest_semantic_milestone.py."""

import json
from unittest.mock import patch

import pytest

from test_helpers import make_completed_process


@pytest.fixture
def _import_module():
    import importlib
    import sys
    mod_name = "get_latest_semantic_milestone"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    return importlib.import_module(mod_name)


class TestParseVersion:
    def test_simple_version(self, _import_module):
        mod = _import_module
        assert mod._parse_version("1.2.3") == (1, 2, 3)

    def test_zero_version(self, _import_module):
        mod = _import_module
        assert mod._parse_version("0.0.0") == (0, 0, 0)

    def test_multi_digit(self, _import_module):
        mod = _import_module
        assert mod._parse_version("10.20.30") == (10, 20, 30)


class TestGetLatestSemanticMilestone:
    def test_finds_latest(self, _import_module):
        mod = _import_module
        milestones = [
            {"title": "0.1.0", "number": 1},
            {"title": "0.3.0", "number": 3},
            {"title": "0.2.0", "number": 2},
        ]
        with patch.object(
            mod, "gh_api_paginated", return_value=milestones,
        ):
            result = mod.get_latest_semantic_milestone("o", "r")

        assert result["Found"] is True
        assert result["Title"] == "0.3.0"
        assert result["Number"] == 3

    def test_ignores_non_semantic(self, _import_module):
        mod = _import_module
        milestones = [
            {"title": "Future", "number": 1},
            {"title": "Backlog", "number": 2},
            {"title": "0.2.0", "number": 3},
        ]
        with patch.object(
            mod, "gh_api_paginated", return_value=milestones,
        ):
            result = mod.get_latest_semantic_milestone("o", "r")

        assert result["Found"] is True
        assert result["Title"] == "0.2.0"

    def test_no_milestones(self, _import_module):
        mod = _import_module
        with patch.object(mod, "gh_api_paginated", return_value=[]):
            result = mod.get_latest_semantic_milestone("o", "r")

        assert result["Found"] is False
        assert result["Title"] == ""

    def test_no_semantic_milestones(self, _import_module):
        mod = _import_module
        milestones = [
            {"title": "Future", "number": 1},
            {"title": "Beta", "number": 2},
        ]
        with patch.object(
            mod, "gh_api_paginated", return_value=milestones,
        ):
            result = mod.get_latest_semantic_milestone("o", "r")

        assert result["Found"] is False

    def test_version_comparison_10_vs_2(self, _import_module):
        """Ensure 0.10.0 > 0.2.0 (not string comparison)."""
        mod = _import_module
        milestones = [
            {"title": "0.2.0", "number": 1},
            {"title": "0.10.0", "number": 2},
        ]
        with patch.object(
            mod, "gh_api_paginated", return_value=milestones,
        ):
            result = mod.get_latest_semantic_milestone("o", "r")

        assert result["Title"] == "0.10.0"

    def test_single_milestone(self, _import_module):
        mod = _import_module
        milestones = [{"title": "1.0.0", "number": 5}]
        with patch.object(
            mod, "gh_api_paginated", return_value=milestones,
        ):
            result = mod.get_latest_semantic_milestone("o", "r")

        assert result["Found"] is True
        assert result["Title"] == "1.0.0"
