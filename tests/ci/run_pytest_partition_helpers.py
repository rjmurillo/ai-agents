"""Shared helper for the run_pytest_partition test modules."""

from __future__ import annotations

import pytest

from scripts.ci import run_pytest_partition as mod


def capture_runner(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Replace the pytest runner with a recorder and return its call list."""
    calls: list[list[str]] = []

    def fake_main(argv: list[str]) -> int:
        calls.append(list(argv))
        return 0

    monkeypatch.setattr(mod.run_pytest_non_tmp, "main", fake_main)
    return calls
