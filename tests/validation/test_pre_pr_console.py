"""Tests for pre_pr_console: line buffering and once-per-run base-ref notes (D19).

A redirected ``pre_pr.py`` log sat at about 120 lines for minutes because
stdout was block-buffered, and the ``[base-ref] selected`` note repeated about
900 times because every gate printed it again.
"""

from __future__ import annotations

import subprocess
import sys
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.validation import checks_common
from scripts.validation.checks_common import (
    _PrViewProbe,
    _reset_gh_base_cache,
    _resolve_branch_base_ref,
    _resolve_default_base_ref,
)
from tests.gh_base_ref_test_helpers import _commit, _init_git_repo

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts" / "validation"

_CHILD = (
    "import sys\n"
    f"sys.path.insert(0, {str(SCRIPTS_DIR)!r})\n"
    "from pre_pr_console import enable_line_buffering\n"
    "if sys.argv[1] == 'on':\n"
    "    enable_line_buffering()\n"
    "print('first-line')\n"
    "sys.stdin.read()\n"
)


def _first_line_arrives(mode: str, wait: float) -> bool:
    """True when the child's first stdout line reaches a pipe within ``wait`` seconds.

    The child prints one line, then blocks on stdin, so a block-buffered
    child cannot deliver the line until the parent closes stdin.
    """
    proc = subprocess.Popen(
        [sys.executable, "-c", _CHILD, mode],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    assert proc.stdin is not None
    assert proc.stdout is not None
    stdout = proc.stdout
    received: list[str] = []
    reader = threading.Thread(target=lambda: received.append(stdout.readline()), daemon=True)
    reader.start()
    reader.join(wait)
    arrived = bool(received)
    proc.stdin.close()
    reader.join(10)
    proc.wait(timeout=10)
    proc.stdout.close()
    return arrived


class TestEnableLineBuffering:
    def test_piped_line_arrives_while_child_still_running(self) -> None:
        assert _first_line_arrives("on", wait=10.0)

    def test_piped_line_is_withheld_without_the_call(self) -> None:
        """Negative control: proves the positive test can fail."""
        assert not _first_line_arrives("off", wait=1.0)

    def test_stream_without_reconfigure_is_left_alone(self) -> None:
        from scripts.validation.pre_pr_console import enable_line_buffering

        with (
            patch.object(sys, "stdout", object()),
            patch.object(sys, "stderr", object()),
        ):
            enable_line_buffering()

    @pytest.mark.parametrize("error", [OSError("closed"), ValueError("closed file")])
    def test_rejecting_stream_does_not_raise(self, error: Exception) -> None:
        from scripts.validation.pre_pr_console import enable_line_buffering

        class Rejecting:
            def reconfigure(self, **_kwargs: object) -> None:
                raise error

        with (
            patch.object(sys, "stdout", Rejecting()),
            patch.object(sys, "stderr", Rejecting()),
        ):
            enable_line_buffering()

    def test_reconfigures_both_streams_with_line_buffering(self) -> None:
        from scripts.validation.pre_pr_console import enable_line_buffering

        calls: list[dict[str, object]] = []

        class Recording:
            def reconfigure(self, **kwargs: object) -> None:
                calls.append(kwargs)

        with (
            patch.object(sys, "stdout", Recording()),
            patch.object(sys, "stderr", Recording()),
        ):
            enable_line_buffering()

        assert calls == [{"line_buffering": True}, {"line_buffering": True}]


class TestBaseRefNoteOnce:
    def setup_method(self) -> None:
        _reset_gh_base_cache()

    @staticmethod
    def _repo_with_origin_main(tmp_path: Path) -> Path:
        repo = tmp_path / "solo"
        repo.mkdir()
        _init_git_repo(repo)
        _commit(repo, "a.txt", "a\n", "chore: seed")
        subprocess.run(
            ["git", "update-ref", "refs/remotes/origin/main", "HEAD"],
            cwd=repo,
            check=True,
            capture_output=True,
        )
        return repo

    def test_pr_base_note_prints_once_across_many_gates(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        repo = self._repo_with_origin_main(tmp_path)
        with (
            patch("scripts.validation.checks_common.shutil.which", return_value="/usr/bin/gh"),
            patch(
                "scripts.validation.checks_common._gh_pr_base_ref_name",
                return_value=_PrViewProbe("main", False, 0, ""),
            ),
        ):
            for _ in range(5):
                assert _resolve_branch_base_ref(repo) == "origin/main"

        err = capsys.readouterr().err
        assert err.count("[base-ref] selected origin/main: open PR base branch") == 1

    def test_fallback_note_prints_once_across_many_gates(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        repo = self._repo_with_origin_main(tmp_path)
        with patch("scripts.validation.checks_common.shutil.which", return_value=None):
            for _ in range(5):
                assert _resolve_branch_base_ref(repo) == "origin/main"

        err = capsys.readouterr().err
        assert err.count("[base-ref] selected origin/main: no PR base resolved") == 1

    def test_upstream_head_note_prints_once(
        self, capsys: pytest.CaptureFixture[str], tmp_path: Path
    ) -> None:
        repo = self._repo_with_origin_main(tmp_path)
        probes = [
            _PrViewProbe(None, True, 1, "no pull requests found"),
            _PrViewProbe("main", False, 0, ""),
        ]
        with (
            patch("scripts.validation.checks_common.shutil.which", return_value="/usr/bin/gh"),
            patch(
                "scripts.validation.checks_common._upstream_head_ref_name", return_value="feat/x"
            ),
            patch(
                "scripts.validation.checks_common._is_self_tracking_upstream", return_value=False
            ),
        ):
            for _ in range(3):
                checks_common._gh_pr_base_cache.clear()
                with patch(
                    "scripts.validation.checks_common._gh_pr_base_ref_name",
                    side_effect=list(probes),
                ):
                    assert checks_common._gh_base_ref(repo) == "origin/main"

        err = capsys.readouterr().err
        assert err.count("PR resolved by upstream head 'feat/x'") == 1

    def test_reset_lets_the_next_run_print_the_note_again(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        repo = self._repo_with_origin_main(tmp_path)
        with patch("scripts.validation.checks_common.shutil.which", return_value=None):
            _resolve_branch_base_ref(repo)
            _reset_gh_base_cache()
            _resolve_branch_base_ref(repo)

        err = capsys.readouterr().err
        assert err.count("[base-ref] selected origin/main: no PR base resolved") == 2

    def test_a_different_note_still_prints(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        repo = self._repo_with_origin_main(tmp_path)
        with (
            patch("scripts.validation.checks_common.shutil.which", return_value="/usr/bin/gh"),
            patch(
                "scripts.validation.checks_common._gh_pr_base_ref_name",
                return_value=_PrViewProbe("main", False, 0, ""),
            ),
        ):
            _resolve_branch_base_ref(repo)
            assert _resolve_default_base_ref(repo) == "origin/main"

        err = capsys.readouterr().err
        assert err.count("[base-ref] selected") == 1


class TestMainEnablesLineBuffering:
    def test_main_enables_line_buffering_before_running(self) -> None:
        from scripts.validation import pre_pr

        with (
            patch.object(pre_pr, "enable_line_buffering") as enable,
            patch.object(pre_pr, "validate_markdown_lint", return_value=True),
        ):
            assert pre_pr.main(["--markdown-lint-only"]) == 0

        enable.assert_called_once_with()
