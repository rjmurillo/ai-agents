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

for _NAME in dir(_MODULE):
    if _NAME.startswith("test_"):
        globals()[_NAME] = getattr(_MODULE, _NAME)
