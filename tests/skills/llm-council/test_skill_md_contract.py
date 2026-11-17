"""ADR-108 template contract for llm-council; see _template_contract.py."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_SUPPORT_SPEC = importlib.util.spec_from_file_location(
    "llm_council_support", Path(__file__).with_name("_support.py")
)
if _SUPPORT_SPEC is None or _SUPPORT_SPEC.loader is None:
    raise ImportError("llm-council _support.py is missing")
support = importlib.util.module_from_spec(_SUPPORT_SPEC)
_SUPPORT_SPEC.loader.exec_module(support)

# _template_contract imports build/scripts modules by bare name and inserts that
# directory on sys.path itself; load_module restores sys.path afterwards.
_contract = support.load_module(
    Path(__file__).resolve().parents[1] / "_template_contract.py", "_template_contract"
)


def test_skill_md_matches_its_template() -> None:
    _contract.assert_template_owned_contract("llm-council")
