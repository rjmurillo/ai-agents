"""Hermetic env for the workflow-local-run gate tests (#3115).

`scripts/validation/run_workflow_local_test.py` reads process env vars
(`SKIP_WORKFLOW_LOCAL_TEST`, the remote-container markers, and `CI`) to decide
whether to bypass or degrade. `tests/validation/test_run_workflow_local_test.py`
asserts the non-bypassed behavior, so if a real push exports
`SKIP_WORKFLOW_LOCAL_TEST=true` to get past an act-unrunnable workflow, that var
leaks into the pre-push pytest subprocess and breaks these tests. That made the
gate's own documented bypass unusable during any workflow-touching push.

Clear those vars before every test in this directory so the suite pins the
script's behavior from a known-empty environment. A test that wants a specific
value sets it explicitly via monkeypatch.
"""

from __future__ import annotations

import pytest

_GATE_ENV_VARS = (
    "SKIP_WORKFLOW_LOCAL_TEST",
    "CLAUDECODE",
    "CODESPACES",
    "CI",
)


@pytest.fixture(autouse=True)
def _clear_workflow_gate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove ambient workflow-gate env vars so tests run hermetically."""
    for name in _GATE_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
