"""Shared loader for harness capability tests (issue #5423)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
EVAL_DIR = REPO_ROOT / "scripts" / "eval"
CLI_SCRIPT = EVAL_DIR / "eval_harness_capability.py"
MATRIX = EVAL_DIR / "examples" / "harness-capability-matrix.json"
# The matrix as it stood before any live probe ran: every cell UNVERIFIED and
# no runtime version. CLI tests start from it so their assertions about what a
# fake run may fill do not depend on what the last real run recorded.
UNPROBED_MATRIX = (
    Path(__file__).resolve().parent / "fixtures" / "harness-capability-matrix-unprobed.json"
)

_path_added = str(EVAL_DIR) not in sys.path
if _path_added:
    sys.path.insert(0, str(EVAL_DIR))
try:
    import _capability_probes as probes
    import _capability_topology as topology
    import _harness_capability as capability

    _spec = importlib.util.spec_from_file_location("eval_harness_capability", CLI_SCRIPT)
    assert _spec and _spec.loader
    cli = importlib.util.module_from_spec(_spec)
    sys.modules[_spec.name] = cli
    _spec.loader.exec_module(cli)
finally:
    if _path_added:
        sys.path.remove(str(EVAL_DIR))

__all__ = ["MATRIX", "UNPROBED_MATRIX", "capability", "cli", "probes", "topology"]
