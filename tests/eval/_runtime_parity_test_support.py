"""Shared loader for runtime parity evaluator tests."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
EVAL_DIR = REPO_ROOT / "scripts" / "eval"
SCRIPT = EVAL_DIR / "eval_runtime_parity.py"
FIXTURES = EVAL_DIR / "examples" / "runtime-parity-fixtures.json"

spec = importlib.util.spec_from_file_location("eval_runtime_parity", SCRIPT)
assert spec and spec.loader
parity = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = parity
path_added = str(EVAL_DIR) not in sys.path
if path_added:
    sys.path.insert(0, str(EVAL_DIR))
try:
    spec.loader.exec_module(parity)
finally:
    if path_added:
        sys.path.remove(str(EVAL_DIR))

runtime_parity = sys.modules["_runtime_parity"]
