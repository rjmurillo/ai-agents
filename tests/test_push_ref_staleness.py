"""Tests for push_ref_staleness.py (issue #3862).

Covers:
- Positive: remote matches cached SHA -> exit 0
- Positive: new branch (no remote) -> exit 0
- Positive: empty stdin -> exit 0
- Positive: deletion push (zeros) -> exit 0
- Positive: remote advanced but we already merged it (ancestor) -> exit 0
- Negative: remote advanced and we haven't merged it -> exit 3
- Edge: multiple refs, one stale -> exit 3
- Edge: multiple refs, all clean -> exit 0
- Edge: malformed stdin line -> skip gracefully
- Remote resolution: named remote, remote URL, missing argument, blank argument,
  and unexpanded lefthook placeholders (issue #4634)
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import patch

_SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts" / "validation" / "push_ref_staleness.py"
)


def _import_script(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _import_script("push_ref_staleness_test")
main = _mod.main

_LOCAL_SHA = "a" * 40
_REMOTE_SHA_OLD = "b" * 40
_REMOTE_SHA_NEW = "c" * 40
_REF = "refs/heads/feature"


def _make_stdin(local_sha=_LOCAL_SHA, remote_sha=_REMOTE_SHA_OLD, ref=_REF):
    return StringIO(f"{ref} {local_sha} {ref} {remote_sha}\n")


def _mock_remote_sha(sha_or_none):
    """Return a patcher that makes _remote_sha return sha_or_none."""
    return patch.object(_mod, "_remote_sha", return_value=sha_or_none)


def _mock_is_ancestor(result):
    return patch.object(_mod, "_is_ancestor", return_value=result)


class TestEmptyAndDeletion:
    def test_empty_stdin_exits_zero(self):
        with patch("sys.stdin", StringIO("")):
            assert main([]) == 0

    def test_deletion_push_exits_zero(self):
        # Deletion: local_sha is all zeros
        zeros = "0" * 40
        stdin = StringIO(f"{_REF} {zeros} {_REF} {_REMOTE_SHA_OLD}\n")
        with patch("sys.stdin", stdin), _mock_remote_sha(_REMOTE_SHA_NEW):
            assert main([]) == 0


class TestRemoteUnchanged:
    def test_remote_matches_cached_sha_exits_zero(self):
        # live_sha == cached remote sha: no race
        with patch("sys.stdin", _make_stdin(remote_sha=_REMOTE_SHA_OLD)), \
                _mock_remote_sha(_REMOTE_SHA_OLD):
            assert main([]) == 0

    def test_no_remote_ref_exits_zero(self):
        # New branch: ls-remote returns None
        with patch("sys.stdin", _make_stdin()), _mock_remote_sha(None):
            assert main([]) == 0


class TestRemoteLookupFailure:
    def test_absent_remote_ref_returns_none(self):
        result = subprocess.CompletedProcess(["git"], 0, "", "")
        with patch.object(_mod, "_run", return_value=result):
            assert _mod._remote_sha("origin", _REF) is None

    def test_network_failure_exits_three(self, capsys):
        error = _mod.RemoteLookupError("network is unreachable", 3)
        with patch("sys.stdin", _make_stdin()), \
                patch.object(_mod, "_remote_sha", side_effect=error):
            assert main(["origin"]) == 3
        assert "Remote lookup failed: network is unreachable" in capsys.readouterr().err

    def test_authentication_failure_exits_four(self, capsys):
        result = subprocess.CompletedProcess(
            ["git"], 128, "", "fatal: Authentication failed for remote"
        )
        with patch.object(_mod, "_run", return_value=result), \
                patch("sys.stdin", _make_stdin()):
            assert main(["origin"]) == 4
        assert "Remote lookup failed: fatal: Authentication failed" in (
            capsys.readouterr().err
        )

    def test_unknown_remote_failure_exits_three(self, capsys):
        result = subprocess.CompletedProcess(
            ["git"], 2, "", "fatal: 'missing' does not appear to be a git repository"
        )
        with patch.object(_mod, "_run", return_value=result), \
                patch("sys.stdin", _make_stdin()):
            assert main(["missing"]) == 3
        assert "does not appear to be a git repository" in capsys.readouterr().err

    def test_remote_timeout_exits_three(self, capsys):
        with patch.object(
            _mod,
            "_run",
            side_effect=subprocess.TimeoutExpired(["git", "ls-remote"], 10),
        ), patch("sys.stdin", _make_stdin()):
            assert main(["origin"]) == 3
        assert "git ls-remote timed out after 10 seconds" in capsys.readouterr().err


class TestRemoteAdvanced:
    def test_remote_advanced_and_not_merged_exits_three(self):
        # live != cached, and local does NOT contain the new remote commit
        with patch("sys.stdin", _make_stdin(remote_sha=_REMOTE_SHA_OLD)), \
                _mock_remote_sha(_REMOTE_SHA_NEW), \
                _mock_is_ancestor(False):
            assert main([]) == 3

    def test_remote_advanced_but_already_merged_exits_zero(self):
        # live != cached, but local IS an ancestor of the new remote
        with patch("sys.stdin", _make_stdin(remote_sha=_REMOTE_SHA_OLD)), \
                _mock_remote_sha(_REMOTE_SHA_NEW), \
                _mock_is_ancestor(True):
            assert main([]) == 0


class TestMultipleRefs:
    def test_all_clean_exits_zero(self):
        stdin_text = (
            f"refs/heads/a {_LOCAL_SHA} refs/heads/a {_REMOTE_SHA_OLD}\n"
            f"refs/heads/b {_LOCAL_SHA} refs/heads/b {_REMOTE_SHA_OLD}\n"
        )
        with patch("sys.stdin", StringIO(stdin_text)), \
                _mock_remote_sha(_REMOTE_SHA_OLD):
            assert main([]) == 0

    def test_one_stale_exits_three(self):
        sha_clean = "d" * 40
        sha_stale_cached = "e" * 40
        sha_stale_live = "f" * 40
        stdin_text = (
            f"refs/heads/ok {_LOCAL_SHA} refs/heads/ok {sha_clean}\n"
            f"refs/heads/bad {_LOCAL_SHA} refs/heads/bad {sha_stale_cached}\n"
        )

        def _fake_remote_sha(_remote, refspec):
            if "bad" in refspec:
                return sha_stale_live
            return sha_clean

        with patch("sys.stdin", StringIO(stdin_text)), \
                patch.object(_mod, "_remote_sha", side_effect=_fake_remote_sha), \
                _mock_is_ancestor(False):
            assert main([]) == 3


class TestMalformedInput:
    def test_short_line_skipped(self):
        stdin = StringIO("only two fields\n")
        with patch("sys.stdin", stdin):
            assert main([]) == 0

    def test_empty_lines_skipped(self):
        stdin = StringIO("\n\n\n")
        with patch("sys.stdin", stdin):
            assert main([]) == 0


class TestRemoteResolution:
    """The remote comes from the pre-push argument, never from a placeholder.

    Issue #4634: the lefthook job passed `{remote}`, which lefthook does not
    substitute. `git ls-remote "{remote}" <ref>` failed, `_remote_sha` returned
    None, and `main` read that as "new branch, no race", so the job reported
    success on every push while checking nothing. These tests pin both halves:
    a real argument is queried, and a placeholder never becomes a remote name.
    """

    @staticmethod
    def _queried_remote(argv):
        """Run main() over one clean ref and return the remote it queried."""
        with patch("sys.stdin", _make_stdin(remote_sha=_REMOTE_SHA_OLD)), \
                patch.object(
                    _mod, "_remote_sha", return_value=_REMOTE_SHA_OLD
                ) as query:
            assert main(argv) == 0
        assert query.call_count == 1
        return query.call_args.args[0]

    @staticmethod
    def _exit_code_for(argv):
        """Run main() over one clean ref and return its exit code."""
        with patch("sys.stdin", _make_stdin(remote_sha=_REMOTE_SHA_OLD)), \
                patch.object(_mod, "_remote_sha", return_value=_REMOTE_SHA_OLD):
            return main(argv)

    def test_named_remote_argument_is_queried(self):
        assert self._queried_remote(["upstream"]) == "upstream"

    def test_remote_url_argument_is_queried(self):
        url = "https://github.com/rjmurillo/ai-agents.git"
        assert self._queried_remote([url]) == url

    def test_missing_argument_falls_back_to_origin(self):
        assert self._queried_remote([]) == "origin"

    def test_blank_argument_falls_back_to_origin(self):
        assert self._queried_remote(["   "]) == "origin"

    def test_unexpanded_positional_placeholder_is_a_configuration_error(self, capsys):
        # `lefthook run pre-push` with no arguments leaves `{1}` literal.
        assert self._exit_code_for(["{1}"]) == 2
        assert "unexpanded placeholder" in capsys.readouterr().err

    def test_unsupported_placeholder_is_a_configuration_error(self, capsys):
        # The exact token the broken job passed (issue #4634).
        assert self._exit_code_for(["{remote}"]) == 2
        assert "'{remote}'" in capsys.readouterr().err

    def test_placeholder_never_queries_a_remote(self):
        """A placeholder stops the run; it never quietly checks some other remote.

        Substituting a default would compare the pushed refs against a remote
        the caller never named, and a clean comparison there exits 0. That is
        the same false green as issue #4634 wearing a different mask.
        """
        with patch("sys.stdin", _make_stdin(remote_sha=_REMOTE_SHA_OLD)), \
                patch.object(_mod, "_remote_sha") as query:
            assert main(["{remote}"]) == 2
        query.assert_not_called()
