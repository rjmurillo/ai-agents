"""Tests for scripts/validation/push_ref_staleness.py (issue #3862)."""

from __future__ import annotations

from io import StringIO
from unittest.mock import MagicMock, patch

import pytest

from scripts.validation.push_ref_staleness import (
    _current_remote_sha,
    _is_zero_sha,
    _parse_stdin,
    _PushRef,
    check_refs,
    main,
)

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

_SHA_A = "a" * 40
_SHA_B = "b" * 40
_SHA_ZERO = "0" * 40
_SHA_SHORT = "abc123"


def _make_ref(
    *,
    local_sha: str = _SHA_A,
    remote_sha: str = _SHA_B,
    remote_ref: str = "refs/heads/fix/test",
) -> _PushRef:
    return _PushRef("refs/heads/fix/test", local_sha, remote_ref, remote_sha)


# ---------------------------------------------------------------------------
# _is_zero_sha
# ---------------------------------------------------------------------------


class TestIsZeroSha:
    def test_all_zeros_40(self) -> None:
        assert _is_zero_sha("0" * 40)

    def test_all_zeros_64(self) -> None:
        assert _is_zero_sha("0" * 64)

    def test_nonzero_sha(self) -> None:
        assert not _is_zero_sha(_SHA_A)

    def test_mixed_sha(self) -> None:
        assert not _is_zero_sha("0" * 39 + "1")

    def test_short_all_zeros(self) -> None:
        assert not _is_zero_sha("0" * 7)


# ---------------------------------------------------------------------------
# _parse_stdin
# ---------------------------------------------------------------------------


class TestParseStdin:
    def test_single_valid_line(self) -> None:
        lines = [f"refs/heads/main {_SHA_A} refs/heads/main {_SHA_B}"]
        refs = _parse_stdin(lines)
        assert len(refs) == 1
        assert refs[0].local_sha == _SHA_A
        assert refs[0].remote_sha == _SHA_B

    def test_multiple_valid_lines(self) -> None:
        lines = [
            f"refs/heads/main {_SHA_A} refs/heads/main {_SHA_B}",
            f"refs/heads/feat {_SHA_B} refs/heads/feat {_SHA_A}",
        ]
        assert len(_parse_stdin(lines)) == 2

    def test_new_branch_zero_remote(self) -> None:
        lines = [f"refs/heads/new {_SHA_A} refs/heads/new {_SHA_ZERO}"]
        refs = _parse_stdin(lines)
        assert refs[0].remote_sha == _SHA_ZERO

    def test_deletion_zero_local(self) -> None:
        lines = [f"refs/heads/gone {_SHA_ZERO} refs/heads/gone {_SHA_B}"]
        refs = _parse_stdin(lines)
        assert refs[0].local_sha == _SHA_ZERO

    def test_malformed_too_few_fields_exits_2(self) -> None:
        with pytest.raises(SystemExit) as exc_info:
            _parse_stdin(["refs/heads/main"])
        assert exc_info.value.code == 2

    def test_malformed_short_sha_exits_2(self) -> None:
        with pytest.raises(SystemExit) as exc_info:
            _parse_stdin([f"refs/heads/main {_SHA_SHORT} refs/heads/main {_SHA_B}"])
        assert exc_info.value.code == 2

    def test_empty_input(self) -> None:
        assert _parse_stdin([]) == []


# ---------------------------------------------------------------------------
# _current_remote_sha
# ---------------------------------------------------------------------------


class TestCurrentRemoteSha:
    def test_returns_sha_when_ref_exists(self) -> None:
        ls_output = f"{_SHA_A}\trefs/heads/main\n"
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=ls_output, stderr="")
            result = _current_remote_sha("origin", "refs/heads/main")
        assert result == _SHA_A

    def test_returns_none_when_ref_absent(self) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            result = _current_remote_sha("origin", "refs/heads/gone")
        assert result is None

    def test_raises_on_nonzero_returncode(self) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=128, stdout="", stderr="network error")
            with pytest.raises(RuntimeError, match="network error"):
                _current_remote_sha("origin", "refs/heads/main")


# ---------------------------------------------------------------------------
# check_refs
# ---------------------------------------------------------------------------


class TestCheckRefs:
    def _mock_ls_remote(self, sha: str) -> MagicMock:
        return MagicMock(returncode=0, stdout=f"{sha}\trefs/heads/fix/test\n", stderr="")

    def test_unchanged_ref_passes(self) -> None:
        ref = _make_ref(remote_sha=_SHA_B)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = self._mock_ls_remote(_SHA_B)
            assert check_refs([ref]) is True

    def test_advanced_ref_returns_false(self) -> None:
        ref = _make_ref(remote_sha=_SHA_B)
        advanced_sha = "c" * 40
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = self._mock_ls_remote(advanced_sha)
            assert check_refs([ref]) is False

    def test_new_branch_skips_check(self) -> None:
        ref = _make_ref(remote_sha=_SHA_ZERO)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = self._mock_ls_remote(_SHA_A)
            assert check_refs([ref]) is True
        mock_run.assert_not_called()

    def test_deletion_skips_check(self) -> None:
        ref = _make_ref(local_sha=_SHA_ZERO, remote_sha=_SHA_B)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = self._mock_ls_remote(_SHA_B)
            assert check_refs([ref]) is True
        mock_run.assert_not_called()

    def test_ref_absent_on_remote_passes(self) -> None:
        ref = _make_ref(remote_sha=_SHA_B)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            assert check_refs([ref]) is True

    def test_ls_remote_failure_exits_3(self) -> None:
        ref = _make_ref(remote_sha=_SHA_B)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=128, stdout="", stderr="fatal: unable to connect"
            )
            with pytest.raises(SystemExit) as exc_info:
                check_refs([ref])
        assert exc_info.value.code == 3

    def test_multiple_refs_all_unchanged(self) -> None:
        refs = [
            _make_ref(remote_sha=_SHA_A, remote_ref="refs/heads/a"),
            _make_ref(remote_sha=_SHA_B, remote_ref="refs/heads/b"),
        ]
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout=f"{_SHA_A}\trefs/heads/a\n", stderr=""),
                MagicMock(returncode=0, stdout=f"{_SHA_B}\trefs/heads/b\n", stderr=""),
            ]
            assert check_refs(refs) is True

    def test_one_of_two_refs_advanced_returns_false(self) -> None:
        refs = [
            _make_ref(remote_sha=_SHA_A, remote_ref="refs/heads/a"),
            _make_ref(remote_sha=_SHA_B, remote_ref="refs/heads/b"),
        ]
        advanced = "d" * 40
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout=f"{_SHA_A}\trefs/heads/a\n", stderr=""),
                MagicMock(returncode=0, stdout=f"{advanced}\trefs/heads/b\n", stderr=""),
            ]
            assert check_refs(refs) is False


# ---------------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------------


class TestMain:
    def test_clean_push_exits_0(self) -> None:
        stdin_text = f"refs/heads/main {_SHA_A} refs/heads/main {_SHA_B}\n"
        ls_output = f"{_SHA_B}\trefs/heads/main\n"
        with (
            patch("sys.stdin", StringIO(stdin_text)),
            patch("sys.argv", ["push_ref_staleness.py"]),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(returncode=0, stdout=ls_output, stderr="")
            main()

    def test_stale_push_exits_3(self) -> None:
        stdin_text = f"refs/heads/main {_SHA_A} refs/heads/main {_SHA_B}\n"
        advanced = "c" * 40
        ls_output = f"{advanced}\trefs/heads/main\n"
        with (
            patch("sys.stdin", StringIO(stdin_text)),
            patch("sys.argv", ["push_ref_staleness.py"]),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(returncode=0, stdout=ls_output, stderr="")
            with pytest.raises(SystemExit) as exc_info:
                main()
        assert exc_info.value.code == 3

    def test_empty_stdin_exits_0(self) -> None:
        with (
            patch("sys.stdin", StringIO("")),
            patch("sys.argv", ["push_ref_staleness.py"]),
        ):
            main()

    def test_unexpected_args_exits_2(self) -> None:
        with (
            patch("sys.argv", ["push_ref_staleness.py", "--some-arg"]),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()
        assert exc_info.value.code == 2

    def test_new_branch_not_checked(self) -> None:
        stdin_text = f"refs/heads/new {_SHA_A} refs/heads/new {_SHA_ZERO}\n"
        with (
            patch("sys.stdin", StringIO(stdin_text)),
            patch("sys.argv", ["push_ref_staleness.py"]),
            patch("subprocess.run") as mock_run,
        ):
            main()
        mock_run.assert_not_called()
