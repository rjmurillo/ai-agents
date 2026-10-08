"""Integration tests for the scripts.validation.pre_pr main entry point.

Split from tests/test_validation_pre_pr.py (issue #6211). Under xdist
``--dist loadfile`` one worker runs a whole file, so these slow tests sit in
their own file instead of extending one worker's run.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from scripts.validation.pre_pr import main
from tests.validation.pre_pr_main_helpers import (
    healthy_git_run,
    sequence_with_passing_corpus_gates,
)


class TestMain:
    """Integration tests for main entry point.

    External tool calls are mocked to avoid requiring actual tools.
    """

    @patch(
        "pre_pr_sequence._SEQUENCE",
        new_callable=sequence_with_passing_corpus_gates,
    )
    @patch("subprocess.run")
    @patch("shutil.which")
    def test_quick_mode_skips_slow_checks(
        self,
        mock_which: Any,
        mock_run: Any,
        _mock_sequence: Any,
    ) -> None:
        mock_run.side_effect = healthy_git_run
        mock_which.return_value = "/usr/bin/tool"

        # Quick mode should skip path normalization, planning, agent drift, yaml style
        result = main(["--quick"])
        assert result == 0

    @patch(
        "pre_pr_sequence._SEQUENCE",
        new_callable=sequence_with_passing_corpus_gates,
    )
    @patch("subprocess.run")
    @patch("shutil.which")
    def test_all_pass_returns_zero(
        self,
        mock_which: Any,
        mock_run: Any,
        _mock_sequence: Any,
    ) -> None:
        mock_run.side_effect = healthy_git_run
        mock_which.return_value = "/usr/bin/tool"

        # All external tools pass
        result = main(["--quick"])
        assert result == 0
