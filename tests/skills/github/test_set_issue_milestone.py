"""Tests for set_issue_milestone.py."""

import json
from unittest.mock import patch

import pytest

from test_helpers import make_completed_process


@pytest.fixture
def _import_module():
    import importlib
    import sys
    mod_name = "set_issue_milestone"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    return importlib.import_module(mod_name)


class TestSetIssueMilestone:
    def test_assign_milestone(self, _import_module):
        mod = _import_module
        with (
            patch.object(mod, "_get_current_milestone", return_value=None),
            patch.object(mod, "_list_milestone_titles", return_value=["v1.0.0"]),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = make_completed_process()

            result = mod.set_issue_milestone("o", "r", 1, milestone="v1.0.0")

        assert result["Success"] is True
        assert result["Action"] == "assigned"
        assert result["Milestone"] == "v1.0.0"

    def test_already_has_same_milestone(self, _import_module):
        mod = _import_module
        with (
            patch.object(mod, "_get_current_milestone", return_value="v1.0.0"),
            patch.object(mod, "_list_milestone_titles", return_value=["v1.0.0"]),
        ):
            result = mod.set_issue_milestone("o", "r", 1, milestone="v1.0.0")

        assert result["Success"] is True
        assert result["Action"] == "no_change"

    def test_force_replace_milestone(self, _import_module):
        mod = _import_module
        with (
            patch.object(mod, "_get_current_milestone", return_value="v0.9.0"),
            patch.object(mod, "_list_milestone_titles", return_value=["v1.0.0"]),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = make_completed_process()

            result = mod.set_issue_milestone(
                "o", "r", 1, milestone="v1.0.0", force=True,
            )

        assert result["Action"] == "replaced"
        assert result["PreviousMilestone"] == "v0.9.0"

    def test_has_milestone_without_force_exits_5(self, _import_module):
        mod = _import_module
        with (
            patch.object(mod, "_get_current_milestone", return_value="v0.9.0"),
            patch.object(mod, "_list_milestone_titles", return_value=["v1.0.0"]),
        ):
            with pytest.raises(SystemExit) as exc:
                mod.set_issue_milestone("o", "r", 1, milestone="v1.0.0")

        assert exc.value.code == 5

    def test_milestone_not_found_exits_2(self, _import_module):
        mod = _import_module
        with (
            patch.object(mod, "_get_current_milestone", return_value=None),
            patch.object(mod, "_list_milestone_titles", return_value=["v2.0.0"]),
        ):
            with pytest.raises(SystemExit) as exc:
                mod.set_issue_milestone("o", "r", 1, milestone="v1.0.0")

        assert exc.value.code == 2

    def test_clear_milestone(self, _import_module):
        mod = _import_module
        with (
            patch.object(mod, "_get_current_milestone", return_value="v1.0.0"),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = make_completed_process()

            result = mod.set_issue_milestone("o", "r", 1, clear=True)

        assert result["Success"] is True
        assert result["Action"] == "cleared"

    def test_clear_no_milestone(self, _import_module):
        mod = _import_module
        with patch.object(mod, "_get_current_milestone", return_value=None):
            result = mod.set_issue_milestone("o", "r", 1, clear=True)

        assert result["Action"] == "no_change"

    def test_api_error_on_assign_exits_3(self, _import_module):
        mod = _import_module
        with (
            patch.object(mod, "_get_current_milestone", return_value=None),
            patch.object(mod, "_list_milestone_titles", return_value=["v1.0.0"]),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = make_completed_process(
                returncode=1, stderr="err"
            )
            with pytest.raises(SystemExit) as exc:
                mod.set_issue_milestone("o", "r", 1, milestone="v1.0.0")

        assert exc.value.code == 3
