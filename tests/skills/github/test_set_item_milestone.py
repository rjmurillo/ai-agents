"""Tests for set_item_milestone.py."""

import json
from unittest.mock import patch

import pytest

from test_helpers import make_completed_process


@pytest.fixture
def _import_module():
    import importlib
    import sys
    mod_name = "set_item_milestone"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    return importlib.import_module(mod_name)


class TestGetItemMilestone:
    def test_has_milestone(self, _import_module):
        mod = _import_module
        item_data = {"milestone": {"title": "v1.0.0"}}
        with patch.object(mod, "_run_gh") as mock_gh:
            mock_gh.return_value = make_completed_process(
                stdout=json.dumps(item_data)
            )
            result = mod._get_item_milestone("o", "r", 1)

        assert result == "v1.0.0"

    def test_no_milestone(self, _import_module):
        mod = _import_module
        item_data = {"milestone": None}
        with patch.object(mod, "_run_gh") as mock_gh:
            mock_gh.return_value = make_completed_process(
                stdout=json.dumps(item_data)
            )
            result = mod._get_item_milestone("o", "r", 1)

        assert result is None


class TestSetItemMilestone:
    def test_skip_when_has_milestone(self, _import_module):
        mod = _import_module
        with patch.object(mod, "_get_item_milestone", return_value="v0.9.0"):
            result = mod.set_item_milestone("o", "r", "pr", 1)

        assert result["Action"] == "skipped"
        assert result["Milestone"] == "v0.9.0"

    def test_assign_with_explicit_title(self, _import_module):
        mod = _import_module
        with (
            patch.object(mod, "_get_item_milestone", return_value=None),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = make_completed_process()

            result = mod.set_item_milestone(
                "o", "r", "issue", 42,
                milestone_title="v1.0.0",
            )

        assert result["Success"] is True
        assert result["Action"] == "assigned"
        assert result["Milestone"] == "v1.0.0"

    def test_api_error_exits_3(self, _import_module):
        mod = _import_module
        with (
            patch.object(mod, "_get_item_milestone", return_value=None),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = make_completed_process(
                returncode=1, stderr="api error"
            )
            with pytest.raises(SystemExit) as exc:
                mod.set_item_milestone(
                    "o", "r", "pr", 1, milestone_title="v1.0.0",
                )

        assert exc.value.code == 3

    def test_query_failure_exits_3(self, _import_module):
        mod = _import_module
        with patch.object(mod, "_run_gh") as mock_gh:
            mock_gh.return_value = make_completed_process(
                returncode=1, stderr="fail"
            )
            with pytest.raises(SystemExit) as exc:
                mod._get_item_milestone("o", "r", 999)

        assert exc.value.code == 3
