"""Tests for _extract_incremental_scope in scripts/ci/spec_extract_refs.py."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
import scripts.ci.spec_extract_refs as spec_extract_refs
from scripts.ci.spec_extract_refs import (
    EXIT_EXTERNAL,
    EXIT_OK,
    _extract_incremental_scope,
)


class TestExtractIncrementalScope:
    def test_returns_stdout_on_success(self) -> None:
        mock = MagicMock(returncode=0, stdout="phase-1\n")
        with patch("scripts.ci.spec_extract_refs.subprocess.run", return_value=mock):
            assert _extract_incremental_scope("feat: phase-1 impl") == (EXIT_OK, "phase-1")

    def test_helper_path_comes_from_the_script_own_checkout(self) -> None:
        """review-gates-14: not the working directory, which is the PR tree in CI."""
        mock = MagicMock(returncode=0, stdout="")
        with patch("scripts.ci.spec_extract_refs.subprocess.run", return_value=mock) as run:
            _extract_incremental_scope("feat: x")
        helper = Path(run.call_args.args[0][1])
        assert helper.is_absolute()
        assert helper.is_file()
        assert helper.name == "extract_incremental_scope.py"
        assert helper.parents[2] == Path(spec_extract_refs.__file__).resolve().parents[2]

    def test_returns_external_error_on_failure(self) -> None:
        mock = MagicMock(returncode=1, stdout="", stderr="parser failed")
        with patch("scripts.ci.spec_extract_refs.subprocess.run", return_value=mock):
            assert _extract_incremental_scope("feat: unknown") == (EXIT_EXTERNAL, "")
