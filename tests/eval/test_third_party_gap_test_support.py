"""Tests for tests/eval/_third_party_gap_test_support.py: no import state leaks."""

from __future__ import annotations

import sys
from types import ModuleType
from typing import cast

import pytest

from tests.eval._third_party_gap_test_support import EVAL_DIR, eval_path, load_script

MINER = "mine_third_party_review_findings"
BUILDER = "build_third_party_gap_corpus"


def test_load_script_restores_sys_path_and_the_module_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before_path = list(sys.path)
    sentinel = ModuleType("sentinel")
    monkeypatch.setitem(sys.modules, MINER, sentinel)

    module = load_script(MINER)

    assert sys.path == before_path
    assert sys.modules[MINER] is sentinel
    assert callable(module.main)


def test_load_script_keeps_an_entry_bound_to_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, MINER, cast(ModuleType, None))

    load_script(MINER)

    assert MINER in sys.modules
    assert sys.modules[MINER] is None


def test_load_script_leaves_no_binding_when_none_existed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delitem(sys.modules, BUILDER, raising=False)

    load_script(BUILDER)

    assert BUILDER not in sys.modules


def test_eval_path_is_scoped_to_the_block() -> None:
    before = list(sys.path)

    with eval_path():
        assert sys.path[0] == str(EVAL_DIR)

    assert sys.path == before
