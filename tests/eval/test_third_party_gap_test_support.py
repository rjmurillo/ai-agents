"""Tests for tests/eval/_third_party_gap_test_support.py: no import state leaks."""

from __future__ import annotations

import sys
from types import ModuleType

from tests.eval._third_party_gap_test_support import EVAL_DIR, eval_path, load_script


def test_load_script_restores_sys_path_and_the_module_binding() -> None:
    before_path = list(sys.path)
    sentinel = ModuleType("sentinel")
    sys.modules["mine_third_party_review_findings"] = sentinel
    try:
        module = load_script("mine_third_party_review_findings")

        assert sys.path == before_path
        assert sys.modules["mine_third_party_review_findings"] is sentinel
        assert callable(module.main)
    finally:
        sys.modules.pop("mine_third_party_review_findings", None)


def test_load_script_leaves_no_binding_when_none_existed() -> None:
    sys.modules.pop("build_third_party_gap_corpus", None)

    load_script("build_third_party_gap_corpus")

    assert "build_third_party_gap_corpus" not in sys.modules


def test_eval_path_is_scoped_to_the_block() -> None:
    before = list(sys.path)

    with eval_path():
        assert sys.path[0] == str(EVAL_DIR)

    assert sys.path == before
