"""Tests for the advisory needs-split label wrapper."""

from __future__ import annotations

import pytest

from scripts.ci import update_needs_split_label


def test_main_requires_github_context(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    monkeypatch.delenv("PR_NUMBER", raising=False)

    assert (
        update_needs_split_label.main(["--mode", "add"])
        == update_needs_split_label.CONFIG_ERROR
    )
