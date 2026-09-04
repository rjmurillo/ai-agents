"""Shared loader for harness capability tests (issue #5423)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
EVAL_DIR = REPO_ROOT / "scripts" / "eval"
CLI_SCRIPT = EVAL_DIR / "eval_harness_capability.py"
MATRIX = EVAL_DIR / "examples" / "harness-capability-matrix.json"

_path_added = str(EVAL_DIR) not in sys.path
if _path_added:
    sys.path.insert(0, str(EVAL_DIR))
try:
    import _harness_capability as capability

    _spec = importlib.util.spec_from_file_location("eval_harness_capability", CLI_SCRIPT)
    assert _spec and _spec.loader
    cli = importlib.util.module_from_spec(_spec)
    sys.modules[_spec.name] = cli
    _spec.loader.exec_module(cli)
finally:
    if _path_added:
        sys.path.remove(str(EVAL_DIR))

__all__ = ["MATRIX", "capability", "cli"]
