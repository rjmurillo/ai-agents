"""Tests for get_branch_protection.py."""

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

    mod_name = "get_branch_protection"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    return importlib.import_module(mod_name)


def _classic():
    return {
        "required_status_checks": {"strict": True, "contexts": ["ci/tests"], "checks": []},
        "required_pull_request_reviews": {
            "required_approving_review_count": 1,
            "dismiss_stale_reviews": True,
            "require_code_owner_reviews": False,
        },
        "enforce_admins": {"enabled": True},
        "allow_force_pushes": {"enabled": False},
    }


def _rules():
    return [
        {
            "type": "required_status_checks",
            "ruleset_source": "org/ruleset-1",
            "parameters": {"required_status_checks": [{"context": "ruleset-check"}]},
        },
        {"type": "pull_request", "parameters": {"required_approving_review_count": 2}},
    ]


def _fake_run(protection, rules, protection_err="", rules_err=""):
    def fake_run(cmd, **kwargs):
        endpoint = cmd[-1]
        if "protection" in endpoint:
            if protection_err:
                return type("R", (), {"returncode": 1, "stdout": "", "stderr": protection_err})()
            return type(
                "R", (), {"returncode": 0, "stdout": json.dumps(protection), "stderr": ""}
            )()
        if "/rules/" not in endpoint:
            return type(
                "R", (), {"returncode": 0, "stdout": json.dumps({"name": "main"}), "stderr": ""}
            )()
        if rules_err:
            return type("R", (), {"returncode": 1, "stdout": "", "stderr": rules_err})()
        return type("R", (), {"returncode": 0, "stdout": json.dumps(rules), "stderr": ""})()

    return fake_run


def _run(mod, argv, protection, rules, protection_err="", rules_err=""):
    with (
        patch.object(mod, "assert_gh_authenticated"),
        patch.object(mod, "resolve_repo_params", return_value=_mock_repo()),
        patch(
            "subprocess.run",
            side_effect=_fake_run(protection, rules, protection_err, rules_err),
        ),
    ):
        return mod.main(argv)


class TestNormalize:
    def test_merges_contexts_from_both_sources(self, mod):
        out = mod.normalize(_classic(), _rules(), "main")
        assert out["required_status_check_contexts"] == ["ci/tests", "ruleset-check"]
        assert out["required_status_check_contexts_ruleset"] == ["ruleset-check"]
        assert out["required_approving_review_count"] == 2
        assert out["dismiss_stale_reviews_on_push"] is True

    def test_unprotected_branch(self, mod):
        out = mod.normalize({}, [], "main")
        assert out["protected"] is False
        assert out["required_status_check_contexts"] == []

    def test_rules_only(self, mod):
        out = mod.normalize(None, _rules(), "main")
        assert out["protected"] is True


class TestMain:
    def test_happy_path(self, mod, capsys):
        rc = _run(mod, ["--branch", "main"], _classic(), _rules())
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert result["Data"]["protected"] is True
        assert "ruleset-check" in result["Data"]["required_status_check_contexts"]

    def test_no_protection_404_succeeds(self, mod, capsys):
        rc = _run(mod, [], {}, [], protection_err="404 Not Found", rules_err="404 Not Found")
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert result["Data"]["protected"] is False

    def test_ruleset_403_partial_coverage(self, mod, capsys):
        rc = _run(mod, [], _classic(), [], rules_err="403 Forbidden")
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert result["Data"]["ruleset_rules_read"] is False
        assert result["Data"]["coverage_warning"]

    def test_transport_error_exit_3(self, mod):
        rc = _run(mod, [], None, [], protection_err="connection reset")
        assert rc == 3

    def test_blank_branch_exit_2(self, mod):
        rc = _run(mod, ["--branch", "  "], {}, [])
        assert rc == 2


class TestBranchEncoding:
    def test_slashed_branch_is_encoded_in_path_segments(self, mod):
        seen = []

        def fake_get(path):
            seen.append(path)
            if path.endswith("/protection"):
                return None, "404 Not Found"
            if "/rules/branches/" in path:
                return [], ""
            return {"name": "feature/x"}, ""

        with (
            patch.object(mod, "assert_gh_authenticated"),
            patch.object(mod, "resolve_repo_params", return_value=_mock_repo()),
            patch.object(mod, "gh_api_get", side_effect=fake_get),
        ):
            rc = mod.main(["--branch", "feature/x"])
        assert rc == 0
        assert "repos/o/r/branches/feature%2Fx" in seen[0]
        assert any("branches/feature%2Fx/protection" in p for p in seen)
        assert any("rules/branches/feature%2Fx" in p for p in seen)
        assert not any("branches/feature/x" in p for p in seen)
