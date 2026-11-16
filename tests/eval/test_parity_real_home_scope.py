"""`eval_runtime_parity.main` sets the `--real-home` opt-in for its run only."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.eval._runtime_parity_test_support import parity, runtime_harness

ENV = runtime_harness.REAL_HOME_ENV


def test_parity_main_sets_real_home_only_for_the_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(ENV, "0")
    seen: list[str | None] = []

    def fake_run(**_kwargs: object) -> tuple[dict[str, object], int]:
        seen.append(os.environ.get(ENV))
        return {}, parity.EXIT_OK

    monkeypatch.setattr(parity, "verify_worktree_identity", lambda: None)
    monkeypatch.setattr(parity, "_require_isolated_login", lambda *_a, **_k: None)
    monkeypatch.setattr(parity, "run_evaluation", fake_run)
    code = parity.main(["--real-home", "--dry-run", "--output", str(tmp_path / "r.json")])
    assert code == parity.EXIT_OK
    assert seen == ["1"]
    assert os.environ.get(ENV) == "0"
