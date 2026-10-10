"""The eval conftest must not leave scripts/eval on sys.path after a test."""

from __future__ import annotations

import sys

import pytest

from tests.eval.conftest import EVAL_DIR, import_runtime_harness


def _path_without_eval_dir() -> list[str]:
    return [entry for entry in sys.path if entry != str(EVAL_DIR)]


def test_eval_dir_is_on_path_while_the_fixture_is_active(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "path", _path_without_eval_dir())
    with pytest.MonkeyPatch.context() as scoped:
        import_runtime_harness(scoped)

        assert str(EVAL_DIR) in sys.path


def test_eval_dir_is_off_path_after_the_fixture_finishes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "path", _path_without_eval_dir())
    with pytest.MonkeyPatch.context() as scoped:
        import_runtime_harness(scoped)

    assert str(EVAL_DIR) not in sys.path


def test_import_returns_the_runtime_harness_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = import_runtime_harness(monkeypatch)

    assert hasattr(harness, "ancestor_instructions")


def test_missing_module_raises_after_scoping(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "path", _path_without_eval_dir())
    monkeypatch.setattr("tests.eval.conftest.EVAL_DIR", EVAL_DIR / "does-not-exist")
    monkeypatch.delitem(sys.modules, "_runtime_harness", raising=False)

    with pytest.raises(ModuleNotFoundError):
        import_runtime_harness(monkeypatch)
