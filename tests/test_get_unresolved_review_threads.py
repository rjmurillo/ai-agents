"""Tests for get_unresolved_review_threads.py skill script."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Import the script via importlib (not a package)
# ---------------------------------------------------------------------------
_SCRIPTS_DIR = (
    Path(__file__).resolve().parents[1]
    / ".claude" / "skills" / "github" / "scripts" / "pr"
)


def _import_script(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS_DIR / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _import_script("get_unresolved_review_threads")
main = _mod.main
build_parser = _mod.build_parser


# ---------------------------------------------------------------------------
# Tests: build_parser
# ---------------------------------------------------------------------------


class TestBuildParser:
    def test_pull_request_required(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args([])

    def test_valid_args(self):
        args = build_parser().parse_args(["--pull-request", "42"])
        assert args.pull_request == 42

    def test_owner_repo_optional(self):
        args = build_parser().parse_args([
            "--owner", "myorg", "--repo", "myrepo", "--pull-request", "1",
        ])
        assert args.owner == "myorg"
        assert args.repo == "myrepo"


# ---------------------------------------------------------------------------
# Tests: main
# ---------------------------------------------------------------------------


class TestMain:
    def test_not_authenticated_exits_4(self):
        with patch(
            "get_unresolved_review_threads.assert_gh_authenticated",
            side_effect=SystemExit(4),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "1"])
            assert exc.value.code == 4

    def test_negative_pr_exits_1(self):
        with patch(
            "get_unresolved_review_threads.assert_gh_authenticated",
        ), patch(
            "get_unresolved_review_threads.resolve_repo_params",
            return_value={"Owner": "o", "Repo": "r"},
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "-1"])
            assert exc.value.code == 1

    def test_success_outputs_json(self, capsys):
        threads = [{"id": "t1", "isResolved": False}]
        with patch(
            "get_unresolved_review_threads.assert_gh_authenticated",
        ), patch(
            "get_unresolved_review_threads.resolve_repo_params",
            return_value={"Owner": "o", "Repo": "r"},
        ), patch(
            "get_unresolved_review_threads.get_unresolved_review_threads",
            return_value=threads,
        ):
            rc = main(["--pull-request", "42"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert len(output) == 1
        assert output[0]["id"] == "t1"

    def test_empty_threads(self, capsys):
        with patch(
            "get_unresolved_review_threads.assert_gh_authenticated",
        ), patch(
            "get_unresolved_review_threads.resolve_repo_params",
            return_value={"Owner": "o", "Repo": "r"},
        ), patch(
            "get_unresolved_review_threads.get_unresolved_review_threads",
            return_value=[],
        ):
            rc = main(["--pull-request", "1"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output == []
