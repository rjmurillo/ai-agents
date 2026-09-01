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

Also holds `adr_debate_repo`, the staged-repository fixture shared by the ADR
debate-log gate suites (issue #5205). Its scaffolding lives in
`_adr_debate_repo.py`; only the fixture is here, because a fixture has to be
discoverable by pytest and the helpers do not.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.validation._adr_debate_repo import _init_repo

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


@pytest.fixture
def adr_debate_repo(tmp_path: Path) -> Path:
    """A git repository with two committed ADRs and an empty critique directory.

    Named for its suites rather than `repo`, because this conftest is shared by
    every module under `tests/validation/` and a bare `repo` would be ambiguous
    at the point of use in files that have nothing to do with the ADR gate.
    """
    _init_repo(tmp_path)
    return tmp_path
