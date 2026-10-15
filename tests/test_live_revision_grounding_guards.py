"""Fail-closed guards for live_revision_grounding.py (issue #5634 review).

Covers:
- --since equal to live must not vouch for a checkout that is behind
- Citation ranges that start or end past the end of a file
- Option-like --remote and malformed --since values (CWE-88)

Shares the git fixtures with test_live_revision_grounding.py.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.test_live_revision_grounding import (
    _advance_remote,
    _git,
    _mod,
    _run,
    make_repos,
)


@pytest.fixture
def repos(tmp_path: Path) -> dict[str, Path]:
    return make_repos(tmp_path)


class TestStaleCheckoutWithSince:
    """--since equal to live must not vouch for a checkout that is behind."""

    def test_since_equal_to_live_with_local_behind_is_unverified(self, repos, capsys):
        new_live = _advance_remote(repos)
        code, rec = _run(repos, capsys, "--since", new_live, "--require-current")
        assert code == 1
        assert rec["status"] == "behind"
        assert rec["live_changed"] is False
        assert rec["finding_status"] == "UNVERIFIED"
        assert "no --cite" in rec["reason"]

    def test_documented_two_run_pattern_fails_closed(self, repos, capsys):
        _advance_remote(repos)
        _code, first = _run(repos, capsys)
        assert first["finding_status"] == "UNVERIFIED"
        code, second = _run(repos, capsys, "--since", first["live_sha"], "--require-current")
        assert code == 1
        assert second["finding_status"] == "UNVERIFIED"

    def test_since_equal_to_live_with_changed_citation_is_stale(self, repos, capsys):
        new_live = _advance_remote(repos)
        _code, rec = _run(repos, capsys, "--since", new_live, "--cite", "a.txt:8")
        assert rec["finding_status"] == "STALE"
        assert rec["citations"][0]["revision"] == rec["local_head"]

    def test_since_equal_to_live_with_unchanged_citation_is_current(self, repos, capsys):
        new_live = _advance_remote(repos)
        code, rec = _run(repos, capsys, "--since", new_live, "--cite", "b.txt", "--require-current")
        assert code == 0
        assert rec["finding_status"] == "CURRENT"

    def test_since_and_local_head_both_compared_when_both_differ(self, repos, capsys):
        _code, first = _run(repos, capsys)
        _advance_remote(repos, "b.txt", "changed\n")
        _advance_remote(repos, "c.txt", "new\n")
        _git(repos["local"], "commit", "-q", "--allow-empty", "-m", "local only")
        _git(repos["local"], "pull", "-q", "--no-rebase", "origin", "main")
        _code, rec = _run(repos, capsys, "--since", first["live_sha"], "--cite", "a.txt")
        revisions = {row["revision"] for row in rec["citations"]}
        assert revisions == {first["live_sha"], rec["local_head"]}
        assert rec["finding_status"] == "CURRENT"

    def test_pulled_checkout_with_since_equal_to_live_is_current(self, repos, capsys):
        _advance_remote(repos)
        _git(repos["local"], "pull", "-q", "origin", "main")
        _code, first = _run(repos, capsys)
        code, second = _run(repos, capsys, "--since", first["live_sha"], "--require-current")
        assert code == 0
        assert second["finding_status"] == "CURRENT"


class TestCitationRange:
    def test_range_starting_past_eof_is_unverified(self, repos, capsys):
        _advance_remote(repos, "b.txt", "changed\n")
        code, rec = _run(repos, capsys, "--cite", "a.txt:500-600", "--require-current")
        assert code == 1
        assert rec["finding_status"] == "UNVERIFIED"
        assert "past the end" in rec["citations"][0]["detail"]

    def test_single_line_past_eof_is_unverified(self, repos, capsys):
        _advance_remote(repos, "b.txt", "changed\n")
        _code, rec = _run(repos, capsys, "--cite", "a.txt:11")
        assert rec["finding_status"] == "UNVERIFIED"

    def test_last_line_is_in_range(self, repos, capsys):
        _advance_remote(repos, "b.txt", "changed\n")
        _code, rec = _run(repos, capsys, "--cite", "a.txt:10")
        assert rec["finding_status"] == "CURRENT"
        assert "clamped" not in rec["citations"][0]["detail"]

    def test_range_end_past_eof_is_clamped_and_flagged(self, repos, capsys):
        _advance_remote(repos, "b.txt", "changed\n")
        _code, rec = _run(repos, capsys, "--cite", "a.txt:8-50")
        assert rec["finding_status"] == "CURRENT"
        assert "clamped to line 10" in rec["citations"][0]["detail"]

    def test_range_past_eof_on_shorter_live_file_is_unverified(self, repos, capsys):
        _advance_remote(repos, "a.txt", "line 1\nline 2\n")
        _code, rec = _run(repos, capsys, "--cite", "a.txt:8-9")
        assert rec["finding_status"] == "UNVERIFIED"


class TestArgumentInjection:
    @pytest.mark.parametrize("remote", ["--upload-pack=touch pwned", "-x", ""])
    def test_option_like_remote_exits_two(self, repos, capsys, remote):
        code, rec = _run(repos, capsys, f"--remote={remote}")
        assert code == 2
        assert rec["finding_status"] == "UNVERIFIED"
        assert "Invalid --remote" in rec["reason"]

    @pytest.mark.parametrize("since", ["--upload-pack=x", "abc123", "G" * 40, "A" * 40, "a" * 41])
    def test_bad_since_exits_two(self, repos, capsys, since):
        code, rec = _run(repos, capsys, f"--since={since}")
        assert code == 2
        assert "--since must be" in rec["reason"]

    @pytest.mark.parametrize("since", ["a" * 40, "0" * 64])
    def test_full_length_since_passes_validation(self, since):
        _mod.validate_inputs("origin", since)
