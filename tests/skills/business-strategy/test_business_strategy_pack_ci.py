"""CI-collected shim for the business-strategy skill pack tests.

pyproject.toml limits default pytest collection to ``tests`` and ``test``. The
canonical structural suite lives beside the skill so skill authors can run it in
place. This shim re-exports those tests so required CI runs enforce the same
contract.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SKILL_TEST = (
    Path(__file__).resolve().parents[3]
    / ".claude"
    / "skills"
    / "business-strategy"
    / "tests"
    / "test_business_strategy_pack.py"
)
_SPEC = importlib.util.spec_from_file_location("_business_strategy_pack_tests", _SKILL_TEST)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules["_business_strategy_pack_tests"] = _MODULE
_SPEC.loader.exec_module(_MODULE)

test_skill_md_exists = _MODULE.test_skill_md_exists
test_frontmatter_has_required_fields = _MODULE.test_frontmatter_has_required_fields
test_router_references_all_fourteen_books = _MODULE.test_router_references_all_fourteen_books
test_every_referenced_file_exists = _MODULE.test_every_referenced_file_exists
test_no_orphan_references = _MODULE.test_no_orphan_references
test_reference_regex_ignores_temporary_suffixes = (
    _MODULE.test_reference_regex_ignores_temporary_suffixes
)
test_decision_tree_routes_one_primary_reference_first = (
    _MODULE.test_decision_tree_routes_one_primary_reference_first
)
test_reference_is_substantive = _MODULE.test_reference_is_substantive
test_pack_has_no_prohibited_dashes = _MODULE.test_pack_has_no_prohibited_dashes
