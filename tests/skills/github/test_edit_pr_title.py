"""Tests for edit_pr_title.py."""

import json
import sys
from unittest.mock import patch

import pytest
from github_core.api import RepoInfo


def _mock_repo():
    return RepoInfo(owner="o", repo="r")


@pytest.fixture
def mod():
    import importlib

    mod_name = "edit_pr_title"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    return importlib.import_module(mod_name)


def _make_run(current_title, record=None):
    def fake_run(cmd, **kwargs):
        joined = " ".join(cmd)
        if "-X" in cmd or "PATCH" in joined:
            if record is not None:
                record.append(cmd)
            return type("R", (), {"returncode": 0, "stdout": "{}", "stderr": ""})()
        return type("R", (), {"returncode": 0, "stdout": current_title + "\n", "stderr": ""})()

    return fake_run


def _run(mod, argv, current_title="old title", record=None):
    with (
        patch.object(mod, "assert_gh_authenticated"),
        patch.object(mod, "resolve_repo_params", return_value=_mock_repo()),
        patch("subprocess.run", side_effect=_make_run(current_title, record)),
    ):
        return mod.main(argv)


class TestValidateTitle:
    def test_conventional_passes_clean(self, mod):
        assert mod.validate_title("feat(scope): a real description") == []

    def test_non_conventional_warns(self, mod):
        warnings = mod.validate_title("just some words")
        assert warnings

    def test_em_dash_warns(self, mod):
        warnings = mod.validate_title("fix: use it \u2014 carefully")
        assert any("dash" in w.lower() for w in warnings)

    def test_overlong_warns(self, mod):
        warnings = mod.validate_title("feat: " + "x" * 300)
        assert any("256" in w or "length" in w.lower() or "long" in w.lower() for w in warnings)


class TestMain:
    def test_happy_path_updates(self, mod, capsys):
        record = []
        rc = _run(mod, ["--pull-request", "7", "--title", "fix: correct the thing"], record=record)
        assert rc == 0
        assert len(record) == 1
        result = json.loads(capsys.readouterr().out)
        assert result["Data"]["Success"] is True

    def test_expected_title_mismatch_refuses(self, mod, capsys):
        rc = _run(
            mod,
            ["--pull-request", "7", "--title", "fix: x", "--expected-title", "something else"],
        )
        assert rc == 1
        result = json.loads(capsys.readouterr().out)
        assert result["Success"] is False

    def test_expected_title_match_proceeds(self, mod):
        rc = _run(
            mod,
            ["--pull-request", "7", "--title", "fix: x", "--expected-title", "old title"],
        )
        assert rc == 0

    def test_noop_same_title(self, mod, capsys):
        record = []
        rc = _run(mod, ["--pull-request", "7", "--title", "old title"], record=record)
        assert rc == 0
        assert record == []

    def test_dry_run_no_write(self, mod):
        record = []
        rc = _run(mod, ["--pull-request", "7", "--title", "fix: x", "--dry-run"], record=record)
        assert rc == 0
        assert record == []

    def test_blank_title_exit_2(self, mod):
        rc = _run(mod, ["--pull-request", "7", "--title", "   "])
        assert rc == 2


class TestPrNotFound:
    @staticmethod
    def _run_with_stderr(mod, stderr):
        def fake_run(cmd, **kwargs):
            return type("R", (), {"returncode": 1, "stdout": "", "stderr": stderr})()

        with (
            patch.object(mod, "assert_gh_authenticated"),
            patch.object(mod, "resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", side_effect=fake_run),
        ):
            return mod.main(["--pull-request", "7", "--title", "fix: x"])

    def test_missing_pr_exits_3_with_not_found_type(self, mod, capsys):
        rc = self._run_with_stderr(mod, "gh: Not Found (HTTP 404)")
        assert rc == 3
        envelope = json.loads(capsys.readouterr().out)
        assert envelope["Error"]["Type"] == "NotFound"
        assert envelope["Error"]["Code"] == 3

    def test_server_error_exits_3_with_api_error_type(self, mod, capsys):
        rc = self._run_with_stderr(mod, "HTTP 502: Bad Gateway")
        assert rc == 3
        assert json.loads(capsys.readouterr().out)["Error"]["Type"] == "ApiError"
