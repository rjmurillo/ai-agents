"""pre_pr suppresses its banners when it runs as a hook job or fails.

Split from tests/test_validation_pre_pr.py (issue #6211). The banner tests
are slow, so they run in two files: this one for runs that must not print
the guidance, and test_pre_pr_banner_shown.py for runs that must.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from scripts.validation.pre_pr import main
from tests.validation.pre_pr_main_helpers import (
    healthy_git_run,
    sequence_with_failing_python_syntax,
    sequence_with_passing_corpus_gates,
)


class TestHookModeBanner:
    """Hook mode and failed runs suppress the banner. Issue #4506.

    The rationale, and what SKIP_AUTOFIX=1 marks, is in the class of the same
    name in test_pre_pr_banner_shown.py.
    """

    @patch(
        "pre_pr_sequence._SEQUENCE",
        new_callable=sequence_with_passing_corpus_gates,
    )
    @patch("subprocess.run")
    @patch("shutil.which")
    def test_hook_mode_does_not_print_pr_ready_banner(
        self,
        mock_which: Any,
        mock_run: Any,
        _mock_sequence: Any,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """SKIP_AUTOFIX=1 (hook mode) must suppress the PR-ready banner. Issue #4506."""
        mock_run.side_effect = healthy_git_run
        mock_which.return_value = "/usr/bin/tool"

        with patch.dict("os.environ", {"SKIP_AUTOFIX": "1"}):
            result = main(["--quick"])

        assert result == 0
        captured = capsys.readouterr()
        assert "Verify the push landed" not in captured.out
        assert "sibling hook jobs" in captured.out

    @patch(
        "pre_pr_sequence._SEQUENCE",
        new_callable=sequence_with_failing_python_syntax,
    )
    @patch("subprocess.run")
    @patch("shutil.which")
    def test_hook_mode_failure_does_not_print_either_banner(
        self,
        mock_which: Any,
        mock_run: Any,
        _mock_sequence: Any,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A failing run in hook mode must not print either banner."""
        mock_run.side_effect = healthy_git_run
        mock_which.return_value = "/usr/bin/tool"

        with patch.dict("os.environ", {"SKIP_AUTOFIX": "1"}):
            result = main(["--quick"])

        assert result == 1
        captured = capsys.readouterr()
        assert "Verify the push landed" not in captured.out
        assert "sibling hook jobs" not in captured.out
