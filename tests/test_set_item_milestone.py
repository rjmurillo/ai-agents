"""Tests for set_item_milestone.py consumer script."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Import the consumer script via importlib (not a package)
# ---------------------------------------------------------------------------
_SCRIPTS_DIR = Path(__file__).resolve().parents[1] / ".github" / "scripts"


def _import_script(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS_DIR / f"{name}.py")
    assert spec is not None, f"Could not load spec for {name}"
    assert spec.loader is not None, f"Spec for {name} has no loader"
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _import_script("set_item_milestone")
main = _mod.main
build_parser = _mod.build_parser
get_latest_semantic_milestone = _mod.get_latest_semantic_milestone
get_item_milestone = _mod.get_item_milestone
assign_milestone = _mod.assign_milestone
_parse_semver_tuple = _mod._parse_semver_tuple


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _completed(stdout: str = "", stderr: str = "", rc: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


def _setup_output(tmp_path: Path, monkeypatch) -> Path:
    output_file = tmp_path / "output"
    output_file.touch()
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))
    return output_file


def _setup_summary(tmp_path: Path, monkeypatch) -> Path:
    summary_file = tmp_path / "summary.md"
    summary_file.touch()
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))
    return summary_file


def _read_outputs(output_file: Path) -> dict[str, str]:
    lines = output_file.read_text().strip().splitlines()
    result = {}
    for line in lines:
        if "=" in line:
            k, v = line.split("=", 1)
            result[k] = v
    return result


# ---------------------------------------------------------------------------
# Tests: _parse_semver_tuple
# ---------------------------------------------------------------------------


class TestParseSemverTuple:
    def test_basic(self):
        assert _parse_semver_tuple("1.2.3") == (1, 2, 3)

    def test_zero(self):
        assert _parse_semver_tuple("0.0.0") == (0, 0, 0)

    def test_large_numbers(self):
        assert _parse_semver_tuple("10.20.30") == (10, 20, 30)


# ---------------------------------------------------------------------------
# Tests: get_latest_semantic_milestone
# ---------------------------------------------------------------------------


class TestGetLatestSemanticMilestone:
    def test_finds_latest(self):
        milestones = [
            {"title": "0.2.0", "number": 1},
            {"title": "0.3.0", "number": 2},
            {"title": "0.1.0", "number": 3},
        ]
        with patch("subprocess.run", return_value=_completed(
            stdout=json.dumps(milestones),
        )):
            result = get_latest_semantic_milestone("o", "r")
        assert result["found"] is True
        assert result["title"] == "0.3.0"
        assert result["number"] == 2

    def test_no_milestones(self):
        with patch("subprocess.run", return_value=_completed(stdout="[]")):
            result = get_latest_semantic_milestone("o", "r")
        assert result["found"] is False

    def test_no_semantic_milestones(self):
        milestones = [{"title": "Backlog", "number": 1}]
        with patch("subprocess.run", return_value=_completed(
            stdout=json.dumps(milestones),
        )):
            result = get_latest_semantic_milestone("o", "r")
        assert result["found"] is False

    def test_mixed_milestones(self):
        milestones = [
            {"title": "Backlog", "number": 1},
            {"title": "1.0.0", "number": 2},
            {"title": "Sprint 5", "number": 3},
        ]
        with patch("subprocess.run", return_value=_completed(
            stdout=json.dumps(milestones),
        )):
            result = get_latest_semantic_milestone("o", "r")
        assert result["found"] is True
        assert result["title"] == "1.0.0"


# ---------------------------------------------------------------------------
# Tests: get_item_milestone
# ---------------------------------------------------------------------------


class TestGetItemMilestone:
    def test_has_milestone(self):
        data = {"milestone": {"title": "0.3.0"}}
        with patch("subprocess.run", return_value=_completed(stdout=json.dumps(data))):
            result = get_item_milestone("o", "r", 1)
        assert result == "0.3.0"

    def test_no_milestone(self):
        data = {"milestone": None}
        with patch("subprocess.run", return_value=_completed(stdout=json.dumps(data))):
            result = get_item_milestone("o", "r", 1)
        assert result is None

    def test_api_failure_exits_3(self):
        with patch("subprocess.run", return_value=_completed(rc=1, stderr="err")):
            with pytest.raises(SystemExit) as exc:
                get_item_milestone("o", "r", 1)
            assert exc.value.code == 3

    def test_invalid_json_exits_3(self):
        with patch("subprocess.run", return_value=_completed(stdout="not json")):
            with pytest.raises(SystemExit) as exc:
                get_item_milestone("o", "r", 1)
            assert exc.value.code == 3


# ---------------------------------------------------------------------------
# Tests: assign_milestone
# ---------------------------------------------------------------------------


class TestAssignMilestone:
    def test_success(self):
        with patch("subprocess.run", return_value=_completed(rc=0)):
            assign_milestone("o", "r", 1, "0.3.0")

    def test_failure_exits_3(self):
        with patch("subprocess.run", return_value=_completed(rc=1, stderr="err")):
            with pytest.raises(SystemExit) as exc:
                assign_milestone("o", "r", 1, "0.3.0")
            assert exc.value.code == 3


# ---------------------------------------------------------------------------
# Tests: build_parser
# ---------------------------------------------------------------------------


class TestBuildParser:
    def test_required_args(self):
        args = build_parser().parse_args([
            "--item-type", "pr",
            "--item-number", "42",
        ])
        assert args.item_type == "pr"
        assert args.item_number == 42

    def test_item_type_choices(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args(["--item-type", "invalid", "--item-number", "1"])

    def test_optional_args(self):
        args = build_parser().parse_args([
            "--item-type", "issue",
            "--item-number", "1",
            "--owner", "myowner",
            "--repo", "myrepo",
            "--milestone-title", "v1.0.0",
        ])
        assert args.owner == "myowner"
        assert args.milestone_title == "v1.0.0"


# ---------------------------------------------------------------------------
# Tests: main
# ---------------------------------------------------------------------------


class TestMain:
    def test_auth_failure_exits_4(self):
        with patch("subprocess.run", return_value=_completed(rc=1)):
            with pytest.raises(SystemExit) as exc:
                main(["--item-type", "pr", "--item-number", "1"])
            assert exc.value.code == 4

    def test_already_has_milestone_skips(self, tmp_path, monkeypatch):
        output_file = _setup_output(tmp_path, monkeypatch)
        _setup_summary(tmp_path, monkeypatch)
        with patch("subprocess.run", return_value=_completed(rc=0)), patch(
            "set_item_milestone.resolve_repo_params",
            return_value={"Owner": "o", "Repo": "r"},
        ), patch(
            "set_item_milestone.get_item_milestone",
            return_value="0.2.0",
        ):
            rc = main(["--item-type", "pr", "--item-number", "1"])
        assert rc == 0
        outputs = _read_outputs(output_file)
        assert outputs["action"] == "skipped"
        assert outputs["milestone"] == "0.2.0"

    def test_auto_detects_milestone_and_assigns(self, tmp_path, monkeypatch):
        output_file = _setup_output(tmp_path, monkeypatch)
        _setup_summary(tmp_path, monkeypatch)
        with patch("subprocess.run", return_value=_completed(rc=0)), patch(
            "set_item_milestone.resolve_repo_params",
            return_value={"Owner": "o", "Repo": "r"},
        ), patch(
            "set_item_milestone.get_item_milestone",
            return_value=None,
        ), patch(
            "set_item_milestone.get_latest_semantic_milestone",
            return_value={"title": "0.3.0", "number": 5, "found": True},
        ), patch(
            "set_item_milestone.assign_milestone",
        ) as mock_assign:
            rc = main(["--item-type", "pr", "--item-number", "42"])
        assert rc == 0
        mock_assign.assert_called_once_with("o", "r", 42, "0.3.0")
        outputs = _read_outputs(output_file)
        assert outputs["action"] == "assigned"
        assert outputs["milestone"] == "0.3.0"

    def test_no_milestone_found_exits_2(self, tmp_path, monkeypatch):
        output_file = _setup_output(tmp_path, monkeypatch)
        _setup_summary(tmp_path, monkeypatch)
        with patch("subprocess.run", return_value=_completed(rc=0)), patch(
            "set_item_milestone.resolve_repo_params",
            return_value={"Owner": "o", "Repo": "r"},
        ), patch(
            "set_item_milestone.get_item_milestone",
            return_value=None,
        ), patch(
            "set_item_milestone.get_latest_semantic_milestone",
            return_value={"title": "", "number": 0, "found": False},
        ):
            rc = main(["--item-type", "issue", "--item-number", "1"])
        assert rc == 2
        outputs = _read_outputs(output_file)
        assert outputs["action"] == "failed"

    def test_explicit_milestone_title(self, tmp_path, monkeypatch):
        _setup_output(tmp_path, monkeypatch)
        _setup_summary(tmp_path, monkeypatch)
        with patch("subprocess.run", return_value=_completed(rc=0)), patch(
            "set_item_milestone.resolve_repo_params",
            return_value={"Owner": "o", "Repo": "r"},
        ), patch(
            "set_item_milestone.get_item_milestone",
            return_value=None,
        ), patch(
            "set_item_milestone.assign_milestone",
        ) as mock_assign:
            rc = main([
                "--item-type", "pr",
                "--item-number", "1",
                "--milestone-title", "1.0.0",
            ])
        assert rc == 0
        mock_assign.assert_called_once_with("o", "r", 1, "1.0.0")
