"""Tests for scripts.validation.verify_issue_close (issue #2481).

Covers the citation-truth gate: extraction of commit/PR resolution claims from a
close rationale, the injected-checker orchestration, the git/gh verification
helpers (subprocess mocked at the boundary), and the CLI exit codes. Domain logic
is never mocked; only the subprocess runner and the module's own verify helpers
are substituted at their boundaries.
"""

from __future__ import annotations

import subprocess

from scripts.validation import verify_issue_close as v


def _proc(returncode: int, stdout: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(["x"], returncode, stdout=stdout, stderr="")


class TestExtractCommitShas:
    def test_keyword_form(self):
        assert v.extract_commit_shas("resolved by commit 61c56cbe here") == ["61c56cbe"]

    def test_full_sha_without_keyword(self):
        sha = "a" * 40
        assert v.extract_commit_shas(f"see {sha}") == [sha]

    def test_dedupes_and_lowercases(self):
        assert v.extract_commit_shas("commit ABC1234 and commit abc1234") == ["abc1234"]

    def test_none_present(self):
        assert v.extract_commit_shas("stale, superseded by the new design") == []

    def test_short_hex_without_keyword_is_ignored(self):
        # A bare short hex token is not a commit citation without the keyword,
        # and is too short to be a full 40-char SHA. It must not be flagged.
        assert v.extract_commit_shas("error code abc1234 was logged") == []


class TestExtractPrNumbers:
    def test_pr_hash_form(self):
        assert v.extract_pr_numbers("closed via PR #1024 today") == [1024]

    def test_pr_space_form(self):
        assert v.extract_pr_numbers("merged in PR 1024") == [1024]

    def test_bare_hash_is_ignored(self):
        assert v.extract_pr_numbers("superseded by #2357") == []

    def test_dedupes(self):
        assert v.extract_pr_numbers("PR #5 and PR #5 again") == [5]


class TestUnverifiedClaims:
    def test_all_verified_returns_empty(self):
        bad = v.unverified_claims(
            "resolved by commit abc1234 via PR #5",
            commit_exists=lambda s: True,
            pr_is_merged=lambda p: True,
        )
        assert bad == []

    def test_missing_commit_flagged(self):
        bad = v.unverified_claims(
            "resolved by commit 61c56cbe",
            commit_exists=lambda s: False,
            pr_is_merged=lambda p: True,
        )
        assert bad == ["commit 61c56cbe"]

    def test_unmerged_pr_flagged(self):
        bad = v.unverified_claims(
            "via PR #1024",
            commit_exists=lambda s: True,
            pr_is_merged=lambda p: False,
        )
        assert bad == ["PR #1024"]

    def test_no_claims_returns_empty(self):
        bad = v.unverified_claims(
            "stale",
            commit_exists=lambda s: False,
            pr_is_merged=lambda p: False,
        )
        assert bad == []


class TestVerifyCommitExists:
    def test_present_commit(self):
        assert v.verify_commit_exists("abc1234", runner=lambda *a, **k: _proc(0)) is True

    def test_absent_commit(self):
        assert v.verify_commit_exists("deadbeef", runner=lambda *a, **k: _proc(1)) is False

    def test_runner_error_is_false(self):
        def boom(*a, **k):
            raise OSError("git missing")

        assert v.verify_commit_exists("abc1234", runner=boom) is False


class TestVerifyPrMerged:
    def test_merged(self):
        runner = lambda *a, **k: _proc(0, stdout='{"state": "MERGED"}')
        assert v.verify_pr_merged(5, "o/r", runner=runner) is True

    def test_closed_unmerged(self):
        runner = lambda *a, **k: _proc(0, stdout='{"state": "CLOSED"}')
        assert v.verify_pr_merged(5, "o/r", runner=runner) is False

    def test_non_zero_returncode(self):
        assert v.verify_pr_merged(5, "o/r", runner=lambda *a, **k: _proc(1)) is False

    def test_bad_json(self):
        runner = lambda *a, **k: _proc(0, stdout="{not json")
        assert v.verify_pr_merged(5, "o/r", runner=runner) is False

    def test_runner_error_is_false(self):
        def boom(*a, **k):
            raise subprocess.TimeoutExpired(cmd="gh", timeout=1)

        assert v.verify_pr_merged(5, "o/r", runner=boom) is False


class TestCliMain:
    def test_no_claims_exits_zero(self, capsys):
        assert v.main(["--rationale", "stale and superseded"]) == 0
        assert "OK" in capsys.readouterr().out

    def test_pr_cited_without_repo_is_config_error(self, capsys):
        assert v.main(["--rationale", "via PR #5"]) == 2
        assert "--repo is required" in capsys.readouterr().err

    def test_unverified_commit_exits_one(self, monkeypatch, capsys):
        monkeypatch.setattr(v, "verify_commit_exists", lambda sha, **k: False)
        rc = v.main(["--rationale", "resolved by commit 61c56cbe"])
        assert rc == 1
        assert "UNVERIFIED" in capsys.readouterr().err

    def test_verified_commit_exits_zero(self, monkeypatch):
        monkeypatch.setattr(v, "verify_commit_exists", lambda sha, **k: True)
        assert v.main(["--rationale", "resolved by commit abc1234"]) == 0
