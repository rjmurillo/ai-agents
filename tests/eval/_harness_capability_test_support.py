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
    import _capability_evidence as evidence
    import _capability_probes as probes
    import _capability_topology as topology
    import _codex_frames as codex_frames
    import _codex_rollout as rollout
    import _context_reset as context_reset
    import _copilot_wire as copilot_wire
    import _harness_capability as capability
    import _offline_capability as offline
    import _pending_live_probes as pending
    import _recorded_captures as captures
    import _runtime_harness as runtime_harness

    _recorded_spec = importlib.util.spec_from_file_location(
        "eval_recorded_capabilities", EVAL_DIR / "eval_recorded_capabilities.py"
    )
    assert _recorded_spec and _recorded_spec.loader
    recorded_cli = importlib.util.module_from_spec(_recorded_spec)
    sys.modules[_recorded_spec.name] = recorded_cli
    _recorded_spec.loader.exec_module(recorded_cli)

    _spec = importlib.util.spec_from_file_location("eval_harness_capability", CLI_SCRIPT)
    assert _spec and _spec.loader
    cli = importlib.util.module_from_spec(_spec)
    sys.modules[_spec.name] = cli
    _spec.loader.exec_module(cli)
finally:
    if _path_added:
        sys.path.remove(str(EVAL_DIR))

FIXTURES = REPO_ROOT / "tests" / "eval" / "fixtures" / "harness_capability"

__all__ = [
    "FIXTURES",
    "MATRIX",
    "UNPROBED_MATRIX",
    "capability",
    "captures",
    "cli",
    "codex_frames",
    "context_reset",
    "copilot_wire",
    "evidence",
    "offline",
    "pending",
    "probes",
    "recorded_cli",
    "rollout",
    "runtime_harness",
    "topology",
]
