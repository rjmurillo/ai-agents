"""Tests for GitHub milestone skill scripts.

Covers:
- get_latest_semantic_milestone.py
- set_item_milestone.py
"""

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure importability of lib and script directories.
_project_root = Path(__file__).resolve().parents[3]
_lib_dir = _project_root / ".claude" / "skills" / "github" / "lib"
_scripts_dir = _project_root / ".claude" / "skills" / "github" / "scripts"
for _p in (
    str(_lib_dir),
    str(_scripts_dir / "milestone"),
    str(_scripts_dir / "issue"),
    str(_scripts_dir),
):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def make_proc(stdout="", stderr="", returncode=0):
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr,
    )


# ---------------------------------------------------------------------------
# get_latest_semantic_milestone
# ---------------------------------------------------------------------------

class TestGetLatestSemanticMilestone:
    """Tests for get_latest_semantic_milestone.get_latest_semantic_milestone."""

    def _import(self):
        import importlib
        import get_latest_semantic_milestone as mod
        importlib.reload(mod)
        return mod

    def test_happy_path(self):
        mod = self._import()
        milestones = [
            {"title": "0.1.0", "number": 1},
            {"title": "0.2.0", "number": 2},
            {"title": "0.2.1", "number": 3},
        ]
        with patch("get_latest_semantic_milestone.gh_api_paginated", return_value=milestones):
            result = mod.get_latest_semantic_milestone("o", "r")
        assert result["Found"] is True
        assert result["Title"] == "0.2.1"
        assert result["Number"] == 3

    def test_no_milestones(self):
        mod = self._import()
        with patch("get_latest_semantic_milestone.gh_api_paginated", return_value=[]):
            result = mod.get_latest_semantic_milestone("o", "r")
        assert result["Found"] is False
        assert result["Title"] == ""

    def test_no_semantic_milestones(self):
        mod = self._import()
        milestones = [
            {"title": "sprint-1", "number": 1},
            {"title": "release-x", "number": 2},
        ]
        with patch("get_latest_semantic_milestone.gh_api_paginated", return_value=milestones):
            result = mod.get_latest_semantic_milestone("o", "r")
        assert result["Found"] is False

    def test_version_comparison(self):
        mod = self._import()
        milestones = [
            {"title": "1.0.0", "number": 10},
            {"title": "2.0.0", "number": 20},
            {"title": "1.10.0", "number": 15},
        ]
        with patch("get_latest_semantic_milestone.gh_api_paginated", return_value=milestones):
            result = mod.get_latest_semantic_milestone("o", "r")
        assert result["Title"] == "2.0.0"

    def test_mixed_milestones_filters_correctly(self):
        mod = self._import()
        milestones = [
            {"title": "v1.0", "number": 1},  # not semver
            {"title": "1.0.0", "number": 2},  # semver
            {"title": "backlog", "number": 3},  # not semver
        ]
        with patch("get_latest_semantic_milestone.gh_api_paginated", return_value=milestones):
            result = mod.get_latest_semantic_milestone("o", "r")
        assert result["Found"] is True
        assert result["Title"] == "1.0.0"

    def test_main_exits_2_when_not_found(self):
        import importlib
        import get_latest_semantic_milestone as mod
        importlib.reload(mod)
        with (
            patch("get_latest_semantic_milestone.assert_gh_authenticated"),
            patch(
                "get_latest_semantic_milestone.resolve_repo_params",
                return_value={"owner": "o", "repo": "r"},
            ),
            patch("get_latest_semantic_milestone.gh_api_paginated", return_value=[]),
        ):
            sys.argv = ["get_latest_semantic_milestone.py"]
            with pytest.raises(SystemExit) as exc:
                mod.main()
        assert exc.value.code == 2

    def test_main_success(self, capsys):
        import importlib
        import get_latest_semantic_milestone as mod
        importlib.reload(mod)
        milestones = [{"title": "1.2.3", "number": 5}]
        with (
            patch("get_latest_semantic_milestone.assert_gh_authenticated"),
            patch(
                "get_latest_semantic_milestone.resolve_repo_params",
                return_value={"owner": "o", "repo": "r"},
            ),
            patch("get_latest_semantic_milestone.gh_api_paginated", return_value=milestones),
        ):
            sys.argv = ["get_latest_semantic_milestone.py", "--owner", "o", "--repo", "r"]
            mod.main()
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed["Found"] is True
        assert parsed["Title"] == "1.2.3"

    def test_help_does_not_crash(self):
        with pytest.raises(SystemExit) as exc:
            sys.argv = ["get_latest_semantic_milestone.py", "--help"]
            import get_latest_semantic_milestone as mod
            mod.main()
        assert exc.value.code == 0

    def test_parse_version(self):
        import importlib
        import get_latest_semantic_milestone as mod
        importlib.reload(mod)
        assert mod._parse_version("1.2.3") == (1, 2, 3)
        assert mod._parse_version("0.10.0") == (0, 10, 0)


# ---------------------------------------------------------------------------
# set_item_milestone
# ---------------------------------------------------------------------------

class TestSetItemMilestone:
    """Tests for set_item_milestone.set_item_milestone."""

    def _import(self):
        import importlib
        import set_item_milestone as mod
        importlib.reload(mod)
        return mod

    def _gh(self, milestone_title=None):
        """Build a fake issue/PR API response."""
        milestone = {"title": milestone_title} if milestone_title else None
        data = {"milestone": milestone}
        return make_proc(stdout=json.dumps(data))

    def test_already_has_milestone_skips(self):
        mod = self._import()
        with patch("set_item_milestone._run_gh", return_value=self._gh("existing-ms")):
            result = mod.set_item_milestone("o", "r", "pr", 10, "existing-ms")
        assert result["Action"] == "skipped"
        assert result["Milestone"] == "existing-ms"

    def test_assigns_provided_milestone(self):
        mod = self._import()
        with (
            patch("set_item_milestone._run_gh", return_value=self._gh(None)),
            patch("subprocess.run", return_value=make_proc(returncode=0)),
        ):
            result = mod.set_item_milestone("o", "r", "pr", 10, "v1.0")
        assert result["Action"] == "assigned"
        assert result["Milestone"] == "v1.0"

    def test_auto_detects_milestone(self):
        mod = self._import()
        detection = {"Found": True, "Title": "0.3.0", "Number": 7}
        with (
            patch("set_item_milestone._run_gh", return_value=self._gh(None)),
            patch("subprocess.run", return_value=make_proc(returncode=0)),
            patch(
                "milestone.get_latest_semantic_milestone.get_latest_semantic_milestone",
                return_value=detection,
            ),
        ):
            result = mod.set_item_milestone("o", "r", "issue", 5)
        assert result["Milestone"] == "0.3.0"

    def test_auto_detect_not_found_exits_2(self):
        mod = self._import()
        detection = {"Found": False, "Title": "", "Number": 0}
        with (
            patch("set_item_milestone._run_gh", return_value=self._gh(None)),
            patch(
                "milestone.get_latest_semantic_milestone.get_latest_semantic_milestone",
                return_value=detection,
            ),
        ):
            with pytest.raises(SystemExit) as exc:
                mod.set_item_milestone("o", "r", "pr", 10)
        assert exc.value.code == 2

    def test_assign_fails_exits_3(self):
        mod = self._import()
        with (
            patch("set_item_milestone._run_gh", return_value=self._gh(None)),
            patch("subprocess.run", return_value=make_proc(returncode=1, stderr="error")),
        ):
            with pytest.raises(SystemExit) as exc:
                mod.set_item_milestone("o", "r", "pr", 10, "v1.0")
        assert exc.value.code == 3

    def test_get_item_milestone_api_failure_exits_3(self):
        mod = self._import()
        err_proc = make_proc(stderr="server error", returncode=1)
        with patch("set_item_milestone._run_gh", return_value=err_proc):
            with pytest.raises(SystemExit) as exc:
                mod.set_item_milestone("o", "r", "pr", 10, "v1.0")
        assert exc.value.code == 3

    def test_main_success(self, capsys):
        import importlib
        import set_item_milestone as mod
        importlib.reload(mod)
        with (
            patch("set_item_milestone.assert_gh_authenticated"),
            patch(
                "set_item_milestone.resolve_repo_params",
                return_value={"owner": "o", "repo": "r"},
            ),
            patch("set_item_milestone._run_gh", return_value=self._gh(None)),
            patch("subprocess.run", return_value=make_proc(returncode=0)),
        ):
            sys.argv = [
                "set_item_milestone.py",
                "--item-type", "pr",
                "--item-number", "42",
                "--milestone-title", "1.0.0",
            ]
            mod.main()
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed["Success"] is True
        assert parsed["Milestone"] == "1.0.0"

    def test_help_does_not_crash(self):
        with pytest.raises(SystemExit) as exc:
            sys.argv = ["set_item_milestone.py", "--help"]
            import set_item_milestone as mod
            mod.main()
        assert exc.value.code == 0
