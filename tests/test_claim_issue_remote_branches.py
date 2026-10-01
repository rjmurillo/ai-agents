"""Remote-branch probe in claim_issue.py (issue #5428).

The probe runs real git against a temporary bare origin, so ``ls-remote`` and
``rev-list`` behave as they do for a worker. Only the gh calls are faked.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_SCRIPT = (
    Path(__file__).resolve().parents[1]
    / ".claude" / "skills" / "github" / "scripts" / "issue" / "claim_issue.py"
)


def _load():
    name = "claim_issue_remote_branches_under_test"
    spec = importlib.util.spec_from_file_location(name, _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


claim = _load()
_REAL_MERGED = claim.merged_through_pr


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=True,
    )
    return result.stdout.strip()


def _push_branch(clone: Path, name: str, commits: int) -> None:
    """Push ``name`` from main with ``commits`` extra commits (0 means an ancestor)."""
    _git(clone, "checkout", "-q", "-B", name, "main")
    for index in range(commits):
        (clone / f"{index}.txt").write_text(name, encoding="utf-8")
        _git(clone, "add", "-A")
        _git(clone, "commit", "-q", "-m", f"work {index}")
    _git(clone, "push", "-q", "origin", name)
    _git(clone, "checkout", "-q", "main")


@pytest.fixture()
def clone(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    bare = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True)
    work = tmp_path / "work"
    subprocess.run(["git", "clone", "-q", str(bare), str(work)], check=True,
                   capture_output=True)
    _git(work, "config", "user.email", "t@example.com")
    _git(work, "config", "user.name", "T")
    _git(work, "config", "commit.gpgsign", "false")
    _git(work, "checkout", "-q", "-b", "main")
    (work / "a.txt").write_text("a", encoding="utf-8")
    _git(work, "add", "-A")
    _git(work, "commit", "-q", "-m", "init")
    _git(work, "push", "-q", "-u", "origin", "main")
    monkeypatch.chdir(work)
    return work


@pytest.fixture(autouse=True)
def _no_merged_prs():
    """Default: gh finds no merged PR. Tests that need one patch it themselves."""
    with patch.object(claim, "merged_through_pr", return_value=False):
        yield


class TestMatchingRemoteHeads:
    def test_matches_issue_number_in_branch(self):
        out = "a1\trefs/heads/codex/5420-a-paths\nb2\trefs/heads/fix-5420-x\n"
        assert claim.matching_remote_heads(out, 5420) == [
            ("codex/5420-a-paths", "a1"), ("fix-5420-x", "b2"),
        ]

    def test_rejects_numeric_near_miss(self):
        out = "a1\trefs/heads/feat/54200-x\nb2\trefs/heads/feat/15420-y\n"
        assert claim.matching_remote_heads(out, 5420) == []

    def test_skips_non_branch_refs(self):
        out = "a1\trefs/tags/v5420\nb2\trefs/pull/5420/head\n"
        assert claim.matching_remote_heads(out, 5420) == []

    def test_skips_blank_and_malformed_lines(self):
        assert claim.matching_remote_heads("\nnot-a-ref-line\n", 5420) == []


class TestFindInFlightBranches:
    def test_no_matching_branch(self, clone):
        _push_branch(clone, "feat/9999-other", 1)
        assert claim.find_in_flight_branches("o", "r", 5420) == ([], [])

    def test_ancestor_branch_is_not_a_warning(self, clone):
        _push_branch(clone, "old/5420-stale", 0)
        assert claim.find_in_flight_branches("o", "r", 5420) == ([], [])

    def test_branch_ahead_of_main_is_reported(self, clone):
        _push_branch(clone, "codex/5420-a-paths", 3)
        in_flight, warnings = claim.find_in_flight_branches("o", "r", 5420)
        assert warnings == []
        assert [(b["branch"], b["ahead"]) for b in in_flight] == [("codex/5420-a-paths", 3)]

    def test_near_miss_number_is_ignored(self, clone):
        _push_branch(clone, "feat/54200-other", 2)
        assert claim.find_in_flight_branches("o", "r", 5420) == ([], [])

    def test_own_current_branch_is_omitted(self, clone):
        _push_branch(clone, "feat/5420-mine", 2)
        _git(clone, "checkout", "-q", "feat/5420-mine")
        assert claim.find_in_flight_branches("o", "r", 5420) == ([], [])

    def test_unreadable_count_is_kept_as_unverified(self, clone):
        _push_branch(clone, "feat/5420-x", 1)
        with patch.object(claim, "commits_ahead", return_value=None):
            in_flight, _ = claim.find_in_flight_branches("o", "r", 5420)
        assert in_flight[0]["ahead"] is None

    def test_squash_merged_branch_is_omitted(self, clone):
        _push_branch(clone, "codex/5420-merged", 2)
        with patch.object(claim, "merged_through_pr", return_value=True):
            assert claim.find_in_flight_branches("o", "r", 5420) == ([], [])

    def test_non_main_default_branch_classifies_ancestor(self, clone):
        _git(clone, "branch", "-m", "main", "develop")
        _git(clone, "push", "-q", "origin", "develop")
        _git(clone, "update-ref", "-d", "refs/remotes/origin/main")
        _git(clone, "remote", "set-head", "origin", "develop")
        _git(clone, "checkout", "-q", "-B", "old/5420-stale", "develop")
        _git(clone, "push", "-q", "origin", "old/5420-stale")
        _git(clone, "checkout", "-q", "develop")
        assert claim.find_in_flight_branches("o", "r", 5420) == ([], [])

    @pytest.mark.parametrize("target", ["current_branch", "origin_base_ref", "commits_ahead"])
    def test_per_branch_failure_degrades_to_named_warning(self, clone, target):
        _push_branch(clone, "feat/5420-x", 1)
        with patch.object(claim, target, side_effect=RuntimeError("git timed out")):
            in_flight, warnings = claim.find_in_flight_branches("o", "r", 5420)
        assert in_flight == []
        assert warnings == ["remote branch probe skipped: git timed out"]

    def test_ls_remote_failure_degrades_to_named_warning(self, clone):
        _git(clone, "remote", "set-url", "origin", str(clone / "does-not-exist"))
        in_flight, warnings = claim.find_in_flight_branches("o", "r", 5420)
        assert in_flight == []
        assert len(warnings) == 1
        assert warnings[0].startswith("remote branch probe skipped:")

    def test_ls_remote_runtime_error_degrades_to_named_warning(self, clone):
        with patch.object(claim, "_run", side_effect=RuntimeError("git timed out")):
            assert claim.find_in_flight_branches("o", "r", 5420) == (
                [], ["remote branch probe skipped: git timed out"],
            )


class TestCommitsAhead:
    def test_counts_commits_beyond_main(self, clone):
        _push_branch(clone, "feat/x", 2)
        sha = _git(clone, "rev-parse", "origin/feat/x")
        assert claim.commits_ahead(sha, "origin/main") == 2

    def test_unknown_object_returns_none(self, clone):
        assert claim.commits_ahead("f" * 40, "origin/main") is None

    def test_missing_base_ref_returns_none(self, clone):
        assert claim.commits_ahead("f" * 40, None) is None

    def test_non_integer_output_returns_none(self):
        done = subprocess.CompletedProcess(["git"], 0, stdout="abc\n", stderr="")
        with patch.object(claim, "_run", return_value=done):
            assert claim.commits_ahead("x", "origin/main") is None


class TestOriginBaseRef:
    def test_reads_origin_head(self, clone):
        _git(clone, "remote", "set-head", "origin", "main")
        assert claim.origin_base_ref() == "origin/main"

    def test_non_main_default_branch(self, clone):
        _git(clone, "branch", "-m", "main", "develop")
        _git(clone, "push", "-q", "origin", "develop")
        _git(clone, "branch", "-q", "--set-upstream-to=origin/develop", "develop")
        _git(clone, "update-ref", "-d", "refs/remotes/origin/main")
        _git(clone, "remote", "set-head", "origin", "develop")
        assert claim.origin_base_ref() == "origin/develop"

    def test_falls_back_to_common_names_without_origin_head(self, clone):
        _git(clone, "remote", "set-head", "origin", "-d")
        assert claim.origin_base_ref() == "origin/main"

    def test_none_when_no_candidate_exists(self, clone):
        _git(clone, "remote", "set-head", "origin", "-d")
        _git(clone, "update-ref", "-d", "refs/remotes/origin/main")
        assert claim.origin_base_ref() is None


class TestMergedThroughPr:
    def test_true_when_merged_pr_head_matches(self):
        done = subprocess.CompletedProcess(["gh"], 0, stdout="abc\ndef\n", stderr="")
        with patch.object(claim, "_run", return_value=done):
            assert _REAL_MERGED("o", "r", "b", "def") is True

    def test_false_when_head_differs(self):
        done = subprocess.CompletedProcess(["gh"], 0, stdout="abc\n", stderr="")
        with patch.object(claim, "_run", return_value=done):
            assert _REAL_MERGED("o", "r", "b", "zzz") is False

    def test_false_when_lookup_fails(self):
        done = subprocess.CompletedProcess(["gh"], 1, stdout="", stderr="boom")
        with patch.object(claim, "_run", return_value=done):
            assert _REAL_MERGED("o", "r", "b", "abc") is False


class TestCurrentBranch:
    def test_returns_empty_when_git_fails(self):
        failed = subprocess.CompletedProcess(["git"], 128, stdout="", stderr="no repo")
        with patch.object(claim, "_run", return_value=failed):
            assert claim.current_branch() == ""


def _fake_run(real_run):
    """Fake gh calls; pass git calls through to the real command."""

    def run(cmd):
        if cmd[0] == "git":
            return real_run(cmd)
        if cmd[:3] == ["gh", "api", "user"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="alice\n", stderr="")
        if cmd[:3] == ["gh", "issue", "view"]:
            return subprocess.CompletedProcess(
                cmd, 0, stdout=json.dumps({"assignees": [{"login": "alice"}]}), stderr="",
            )
        raise AssertionError(f"unexpected call: {cmd}")

    return run


class TestMainReportsInFlight:
    def _run_main(self, fmt: str) -> int:
        with (
            patch.object(claim, "assert_gh_authenticated", return_value=None),
            patch.object(claim, "resolve_repo_params") as resolve,
            patch.object(claim, "_run", side_effect=_fake_run(claim._run)),
        ):
            resolve.return_value.owner = "o"
            resolve.return_value.repo = "r"
            return claim.main(["--issue", "5420", "--output-format", fmt])

    def test_json_output_carries_in_flight_branches(self, clone, capsys):
        _push_branch(clone, "codex/5420-a-paths", 2)
        assert self._run_main("json") == 0
        data = json.loads(capsys.readouterr().out)
        assert data["Data"]["in_flight_branches"][0]["ahead"] == 2

    def test_human_output_warns(self, clone, capsys):
        _push_branch(clone, "codex/5420-a-paths", 2)
        assert self._run_main("human") == 0
        out = capsys.readouterr().out
        assert "WARNING: pushed branches already carry work" in out
        assert "codex/5420-a-paths (2 ahead)" in out

    def test_unverified_branch_is_described(self):
        text = claim.describe_in_flight([{"branch": "b", "sha": "s", "ahead": None}])
        assert "b (unverified)" in text

    def test_probe_warning_is_printed(self, clone, capsys):
        _git(clone, "remote", "set-url", "origin", str(clone / "missing"))
        assert self._run_main("human") == 0
        assert "WARNING: remote branch probe skipped" in capsys.readouterr().out
