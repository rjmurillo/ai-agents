"""Tests for security retrospective subprocess timeouts."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts.security.invoke_security_retrospective import (
    SUBPROCESS_TIMEOUT_SECONDS,
    ExternalReviewSource,
    SecurityRetrospective,
)


def _retrospective(tmp_path: Path) -> SecurityRetrospective:
    with patch.object(SecurityRetrospective, "_find_repo_root", return_value=tmp_path):
        return SecurityRetrospective(1, ExternalReviewSource.MANUAL)


def test_fetch_comments_includes_timeout(tmp_path: Path) -> None:
    retro = _retrospective(tmp_path)

    with patch.object(retro, "_get_owner_repo", return_value="o/r"), patch(
        "scripts.security.invoke_security_retrospective.subprocess.run",
    ) as run:
        run.return_value = MagicMock(returncode=0, stdout=json.dumps([]), stderr="")
        assert retro._fetch_external_review_comments() == []

    assert run.call_args.kwargs["timeout"] == SUBPROCESS_TIMEOUT_SECONDS


def test_owner_repo_lookup_includes_timeout(tmp_path: Path) -> None:
    retro = _retrospective(tmp_path)

    with patch("scripts.security.invoke_security_retrospective.subprocess.run") as run:
        run.return_value = MagicMock(returncode=0, stdout="o/r\n")
        assert retro._get_owner_repo() == "o/r"

    assert run.call_args.kwargs["timeout"] == SUBPROCESS_TIMEOUT_SECONDS
