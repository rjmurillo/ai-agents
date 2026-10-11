"""pre_pr prints push-verification guidance when it is not running as a hook.

Split from tests/test_validation_pre_pr.py (issue #6211). The banner tests
are slow, so they run in two files: this one for runs that must print the
guidance, and test_pre_pr_banner_suppressed.py for runs that must not.
"""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import patch

import pytest

from scripts.validation.pre_pr import main
from tests.validation.pre_pr_main_helpers import (
    healthy_git_run,
    sequence_with_passing_corpus_gates,
)


class TestHookModeBanner:
    """The success banner must not claim PR-readiness when running as a hook job.

    Issue #4506: pre_pr.py runs in a parallel lefthook group alongside
    python-tests, ratchets, and other jobs. It only validates its own subset.
    Printing "Ready to create pull request!" is a false claim when sibling jobs
    may still be running or may have failed.

    SKIP_AUTOFIX=1 is the marker lefthook sets on the pre-pr-validation job.
    It is absent in direct interactive use.
    """

    @patch(
        "pre_pr_sequence._SEQUENCE",
        new_callable=sequence_with_passing_corpus_gates,
    )
    @patch("subprocess.run")
    @patch("shutil.which")
    def test_interactive_mode_prints_verification_guidance(
        self,
        mock_which: Any,
        mock_run: Any,
        _mock_sequence: Any,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Direct invocation (no hook env) must print push-verification guidance."""
        mock_run.side_effect = healthy_git_run
        mock_which.return_value = "/usr/bin/tool"

        with patch.dict("os.environ", {}, clear=False):
            os.environ.pop("SKIP_AUTOFIX", None)
            result = main(["--quick"])

        assert result == 0
        captured = capsys.readouterr()
        assert "Verify the push landed" in captured.out
        assert "same SHA" in captured.out
        assert "sibling hook jobs" not in captured.out

    @patch(
        "pre_pr_sequence._SEQUENCE",
        new_callable=sequence_with_passing_corpus_gates,
    )
    @patch("subprocess.run")
    @patch("shutil.which")
    def test_skip_autofix_zero_is_not_hook_mode(
        self,
        mock_which: Any,
        mock_run: Any,
        _mock_sequence: Any,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """SKIP_AUTOFIX=0 is not hook mode; the verification guidance must still print."""
        mock_run.side_effect = healthy_git_run
        mock_which.return_value = "/usr/bin/tool"

        with patch.dict("os.environ", {"SKIP_AUTOFIX": "0"}):
            result = main(["--quick"])

        assert result == 0
        captured = capsys.readouterr()
        assert "Verify the push landed" in captured.out

    @patch(
        "pre_pr_sequence._SEQUENCE",
        new_callable=sequence_with_passing_corpus_gates,
    )
    @patch("subprocess.run")
    @patch("shutil.which")
    def test_success_output_requires_remote_sha_to_match_head(
        self,
        mock_which: Any,
        mock_run: Any,
        _mock_sequence: Any,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Issue #4506: verification must reject an existing but stale remote ref."""
        mock_run.side_effect = healthy_git_run
        mock_which.return_value = "/usr/bin/tool"

        result = main(["--quick"])
        assert result == 0
        out = capsys.readouterr().out
        assert "Verify the push landed" in out
        assert "git rev-parse HEAD" in out
        assert "git ls-remote origin <branch>" in out
        assert "same SHA" in out
