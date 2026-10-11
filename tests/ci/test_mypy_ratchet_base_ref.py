from __future__ import annotations

import pytest

from scripts.ci import mypy_ratchet
from scripts.validation.git_hook_policy import MYPY_RATCHET_BASE_REF_ENV
from tests.ci.mypy_ratchet_git_harness import isolate_env


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    isolate_env(monkeypatch)


def test_default_base_ref_reads_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(MYPY_RATCHET_BASE_REF_ENV, "abc123")

    assert mypy_ratchet.default_base_ref() == "abc123"


def test_default_base_ref_falls_back_when_unset() -> None:
    assert mypy_ratchet.default_base_ref() == "origin/main"


def test_default_base_ref_falls_back_for_zero_sha(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(MYPY_RATCHET_BASE_REF_ENV, "0" * 40)

    assert mypy_ratchet.default_base_ref() == "origin/main"


def test_default_base_ref_uses_origin_main_on_push(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_EVENT_NAME", "push")
    monkeypatch.setenv(MYPY_RATCHET_BASE_REF_ENV, "abc123")

    assert mypy_ratchet.default_base_ref() == "origin/main"
