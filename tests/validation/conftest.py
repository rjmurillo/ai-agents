from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def clear_workflow_local_test_bypass(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep validation tests independent of the pre-push bypass environment."""
    monkeypatch.delenv("SKIP_WORKFLOW_LOCAL_TEST", raising=False)
