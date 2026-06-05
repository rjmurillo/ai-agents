"""Tests for quality-gate workspace path normalization."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.quality_gate import path_utils
from scripts.quality_gate.path_utils import resolve_workspace_path


class TestResolveWorkspacePath:
    def test_relative_path_resolves_under_repository_root(self, tmp_path: Path) -> None:
        resolved = resolve_workspace_path(Path("ai-review-results"), "results-dir")

        assert resolved == tmp_path / "ai-review-results"

    def test_absolute_path_inside_repository_root_is_allowed(self, tmp_path: Path) -> None:
        inside = tmp_path / "ai-review-results"

        assert resolve_workspace_path(inside, "results-dir") == inside

    def test_absolute_path_outside_repository_root_is_rejected(self, tmp_path: Path) -> None:
        outside = tmp_path.parent / "outside"

        with pytest.raises(ValueError, match="results-dir"):
            resolve_workspace_path(outside, "results-dir")

    def test_symlink_escape_is_rejected(self, tmp_path: Path) -> None:
        outside = tmp_path.parent / "outside"
        outside.mkdir(exist_ok=True)
        link = tmp_path / "link"
        link.symlink_to(outside, target_is_directory=True)

        with pytest.raises(ValueError, match="results-dir"):
            resolve_workspace_path(link, "results-dir")
