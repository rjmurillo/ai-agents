"""Tests for _resolve_default_base_ref (issue #2571).

pre_pr.py missed changed workflow files that the pre-push hook detected,
because its base resolver could fall back to the branch's own upstream
(``@{u}``), which yields an empty diff once the branch is pushed. The
default-branch resolver must mirror pre-push (merge-base with origin/main)
and must never request ``@{u}``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

from scripts.validation.checks_common import _resolve_default_base_ref


class TestResolveDefaultBaseRef:
    def test_uses_gh_pr_base_when_verifiable(self) -> None:
        with patch(
            "scripts.validation.checks_common._gh_base_ref", return_value="main"
        ), patch(
            "scripts.validation.checks_common._run_subprocess",
            return_value=(0, "", ""),
        ) as mock_run:
            result = _resolve_default_base_ref(Path("/repo"))
        assert result == "main"
        # The first verify call targets the gh PR base.
        assert mock_run.call_args_list[0][0][0][-1] == "main"

    def test_never_requests_branch_upstream(self) -> None:
        # gh base unavailable; the resolver walks origin/HEAD, origin/main, main.
        # It must never rev-parse "@{u}" (the #2571 regression).
        def fake_run(cmd: list[str], *_: Any, **__: Any) -> tuple[int, str, str]:
            ref = cmd[-1]
            return (0, "", "") if ref == "origin/main" else (1, "", "")

        with patch(
            "scripts.validation.checks_common._gh_base_ref", return_value=None
        ), patch(
            "scripts.validation.checks_common._run_subprocess", side_effect=fake_run
        ) as mock_run:
            result = _resolve_default_base_ref(Path("/repo"))
        assert result == "origin/main"
        requested = [c[0][0][-1] for c in mock_run.call_args_list]
        assert "@{u}" not in requested

    def test_returns_none_when_nothing_resolves(self) -> None:
        with patch(
            "scripts.validation.checks_common._gh_base_ref", return_value=None
        ), patch(
            "scripts.validation.checks_common._run_subprocess",
            return_value=(1, "", ""),
        ):
            assert _resolve_default_base_ref(Path("/repo")) is None
