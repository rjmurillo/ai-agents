"""Tests for scripts.validation.verify_issue_close (issue #2481).

Covers the citation-truth gate: extraction of commit/PR resolution claims from a
close rationale, the injected-checker orchestration, the git/gh verification
helpers (subprocess mocked at the boundary), and the CLI exit codes. Domain logic
is never mocked; only the subprocess runner and the module's own verify helpers
are substituted at their boundaries.
"""

from __future__ import annotations

import datetime
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

    def test_git_runner_uses_utf8_encoding_and_c_locale(self):
        captured: dict[str, object] = {}

        def runner(*args, **kwargs):
            captured["args"] = args
            captured["kwargs"] = kwargs
            return _proc(0)

        assert v.verify_commit_exists("abc1234", runner=runner) is True
        kwargs = captured["kwargs"]
        assert kwargs["encoding"] == "utf-8"
        assert kwargs["errors"] == "replace"
        assert kwargs["env"]["LC_ALL"] == "C"

    def test_repo_context_verifies_commit_with_github_api(self):
        captured: dict[str, object] = {}

        def runner(*args, **kwargs):
            captured["args"] = args
            captured["kwargs"] = kwargs
            return _proc(0)

        assert v.verify_commit_exists("abc1234", repo="o/r", runner=runner) is True
        assert captured["args"][0] == ["gh", "api", "repos/o/r/commits/abc1234"]
        kwargs = captured["kwargs"]
        assert kwargs["encoding"] == "utf-8"
        assert kwargs["errors"] == "replace"
        assert "env" not in kwargs

    def test_repo_context_missing_commit_is_false(self):
        def runner(*a, **k):
            return _proc(1)

        assert v.verify_commit_exists("deadbeef", repo="o/r", runner=runner) is False

    def test_absent_commit(self):
        assert v.verify_commit_exists("deadbeef", runner=lambda *a, **k: _proc(1)) is False

    def test_runner_error_is_false(self):
        def boom(*a, **k):
            raise OSError("git missing")

        assert v.verify_commit_exists("abc1234", runner=boom) is False


class TestVerifyPrMerged:
    def test_merged_and_on_main(self):
        """MERGED + ancestry on origin/main -> True (issue #4624 positive)."""
        calls = []

        def runner(*args, **kwargs):
            calls.append(args[0])
            if "gh" in args[0][0]:
                return _proc(0, stdout='{"state": "MERGED", "mergeCommit": {"oid": "abc123"}}')
            # git merge-base --is-ancestor
            return _proc(0)

        assert v.verify_pr_merged(5, "o/r", runner=runner) is True
        assert len(calls) == 2
        assert "merge-base" in calls[1]

    def test_open_pr_is_rejected(self):
        """An OPEN PR must NOT pass verification (issue #4624 core defect)."""
        def runner(*a, **k):
            return _proc(0, stdout='{"state": "OPEN", "mergeCommit": null}')

        assert v.verify_pr_merged(5, "o/r", runner=runner) is False

    def test_merged_not_on_main(self):
        """MERGED but merge commit not ancestor of origin/main -> False (#4624)."""
        def runner(*args, **kwargs):
            if "gh" in args[0][0]:
                return _proc(0, stdout='{"state": "MERGED", "mergeCommit": {"oid": "dead"}}')
            # git merge-base returns 1 (not an ancestor)
            return _proc(1)

        assert v.verify_pr_merged(5, "o/r", runner=runner) is False

    def test_merged_no_merge_commit_sha(self):
        """MERGED but gh omits mergeCommit -> unverifiable -> False."""
        def runner(*a, **k):
            return _proc(0, stdout='{"state": "MERGED", "mergeCommit": null}')

        assert v.verify_pr_merged(5, "o/r", runner=runner) is False

    def test_gh_runner_uses_utf8_encoding(self):
        captured: dict[str, object] = {}

        def runner(*args, **kwargs):
            captured["args"] = args
            captured["kwargs"] = kwargs
            if "gh" in args[0][0]:
                return _proc(0, stdout='{"state": "MERGED", "mergeCommit": {"oid": "a1b2"}}')
            return _proc(0)

        assert v.verify_pr_merged(5, "o/r", runner=runner) is True
        kwargs = captured["kwargs"]
        assert kwargs["encoding"] == "utf-8"
        assert kwargs["errors"] == "replace"

    def test_closed_unmerged(self):
        def runner(*a, **k):
            return _proc(0, stdout='{"state": "CLOSED", "mergeCommit": null}')

        assert v.verify_pr_merged(5, "o/r", runner=runner) is False

    def test_null_state_is_unmerged(self):
        def runner(*a, **k):
            return _proc(0, stdout='{"state": null}')

        assert v.verify_pr_merged(5, "o/r", runner=runner) is False

    def test_non_object_payload_is_unmerged(self):
        def runner(*a, **k):
            return _proc(0, stdout='["MERGED"]')

        assert v.verify_pr_merged(5, "o/r", runner=runner) is False

    def test_non_zero_returncode(self):
        assert v.verify_pr_merged(5, "o/r", runner=lambda *a, **k: _proc(1)) is False

    def test_bad_json(self):
        def runner(*a, **k):
            return _proc(0, stdout="{not json")

        assert v.verify_pr_merged(5, "o/r", runner=runner) is False

    def test_runner_error_is_false(self):
        def boom(*a, **k):
            raise subprocess.TimeoutExpired(cmd="gh", timeout=1)

        assert v.verify_pr_merged(5, "o/r", runner=boom) is False

    def test_require_ancestry_false_skips_git_check(self):
        """When ancestry check disabled, only state matters."""
        def runner(*a, **k):
            return _proc(0, stdout='{"state": "MERGED", "mergeCommit": {"oid": "x"}}')

        assert v.verify_pr_merged(5, "o/r", require_ancestry=False, runner=runner) is True


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


class TestCheckUnresolvedScope:
    """Tests for check_unresolved_scope timestamp-based rule (issue #4625)."""

    def _ts(self, iso: str) -> datetime.datetime:
        return datetime.datetime.fromisoformat(iso)

    def _comment(
        self, author: str = "human", author_type: str = "User",
        created_at: str = "2026-07-01T12:00:00+00:00", body: str = "", url: str = "",
    ) -> v.IssueComment:
        return v.IssueComment(
            author=author,
            author_type=author_type,
            created_at=self._ts(created_at),
            url=url or f"https://github.com/o/r/issues/1#comment-{id(body)}",
            body=body,
        )

    def test_human_comment_after_fix_blocks(self):
        """Core rule: human comment after fix timestamp blocks auto-close."""
        fix_time = self._ts("2026-07-01T10:00:00+00:00")
        comments = [self._comment(created_at="2026-07-01T11:00:00+00:00", body="still broken")]
        blocks = v.check_unresolved_scope(comments, fix_time)
        assert len(blocks) == 1
        assert "human" in blocks[0].reason.lower() or "@human" in blocks[0].reason

    def test_bot_comment_after_fix_does_not_block(self):
        """Bot comments are not human scope; they must not block."""
        fix_time = self._ts("2026-07-01T10:00:00+00:00")
        comments = [self._comment(
            author="github-actions[bot]", author_type="Bot",
            created_at="2026-07-01T11:00:00+00:00", body="auto-triage",
        )]
        blocks = v.check_unresolved_scope(comments, fix_time)
        assert blocks == []

    def test_human_comment_before_fix_does_not_block(self):
        """Comments predating the fix are addressed by the fix itself."""
        fix_time = self._ts("2026-07-01T10:00:00+00:00")
        comments = [self._comment(created_at="2026-06-30T09:00:00+00:00")]
        blocks = v.check_unresolved_scope(comments, fix_time)
        assert blocks == []

    def test_no_comments_does_not_block(self):
        """Zero comments is safe (successful empty fetch)."""
        fix_time = self._ts("2026-07-01T10:00:00+00:00")
        blocks = v.check_unresolved_scope([], fix_time)
        assert blocks == []

    def test_timezone_offset_comparison(self):
        """Mixed offset forms must compare as real datetimes, not strings."""
        # These are the same instant: 2026-07-01T10:00:00 UTC
        fix_time = self._ts("2026-07-01T10:00:00+00:00")
        # Comment at 2026-07-01T12:00:00+02:00 == 10:00:00 UTC (same instant)
        comments = [self._comment(created_at="2026-07-01T12:00:00+02:00")]
        blocks = v.check_unresolved_scope(comments, fix_time)
        # Same instant as fix, not after: should not block (uses <=)
        assert blocks == []

    def test_timezone_offset_after(self):
        """Comment one second after fix in a different offset still blocks."""
        fix_time = self._ts("2026-07-01T10:00:00+00:00")
        # 2026-07-01T12:00:01+02:00 == 10:00:01 UTC, one second after fix
        comments = [self._comment(created_at="2026-07-01T12:00:01+02:00")]
        blocks = v.check_unresolved_scope(comments, fix_time)
        assert len(blocks) == 1

    def test_automation_author_filtered(self):
        """Comments from the automation account itself do not block."""
        fix_time = self._ts("2026-07-01T10:00:00+00:00")
        comments = [self._comment(
            author="auto-closer", author_type="User",
            created_at="2026-07-01T11:00:00+00:00",
        )]
        blocks = v.check_unresolved_scope(
            comments, fix_time, automation_authors=frozenset({"auto-closer"}),
        )
        assert blocks == []

    def test_novel_phrasing_still_blocks(self):
        """A comment with phrasing no keyword list could match still blocks.

        This is the proof the timestamp design fixes #4625: any human comment
        after the fix blocks, regardless of wording. The old phrase-matching
        implementation would have let this through because the text contains
        none of its enumerated patterns.
        """
        fix_time = self._ts("2026-07-01T10:00:00+00:00")
        # Intentionally uses wording that no reasonable keyword list covers
        comments = [self._comment(
            created_at="2026-07-01T11:00:00+00:00",
            body="fwiw the ARM64 path panics on the same input",
        )]
        blocks = v.check_unresolved_scope(comments, fix_time)
        assert len(blocks) == 1

    def test_reason_names_comment_url_and_author(self):
        """The block reason must name the comment for human triage."""
        fix_time = self._ts("2026-07-01T10:00:00+00:00")
        comments = [self._comment(
            author="reviewer", created_at="2026-07-02T08:00:00+00:00",
            url="https://github.com/o/r/issues/1#issuecomment-999",
        )]
        blocks = v.check_unresolved_scope(comments, fix_time)
        assert "issuecomment-999" in blocks[0].reason
        assert "@reviewer" in blocks[0].reason
