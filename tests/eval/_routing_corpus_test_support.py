"""Shared helpers for routing corpus tests (issue #5425)."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any

EVAL_DIR = Path(__file__).resolve().parents[2] / "scripts" / "eval"
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

import _routing_fixtures as fixtures_mod  # noqa: E402
import _routing_grader as grader  # noqa: E402
import _routing_scenario as scenario_mod  # noqa: E402
import eval_routing_corpus as cli  # noqa: E402

REAL_CORPUS = cli.DEFAULT_CORPUS

BOUNDED = "RB-01-bounded-implementation"
MULTI_FILE = "RB-02-multi-file-invariants"
INVESTIGATE = "RB-03-investigate-before-edit"
SCOPE = "RB-04-scope-expansion"
PLAUSIBLE = "RB-05-plausible-but-wrong"
ARCHITECTURE = "RB-06-architecture-resolved"

__all__ = [
    "ARCHITECTURE",
    "BOUNDED",
    "EVAL_DIR",
    "INVESTIGATE",
    "MULTI_FILE",
    "PLAUSIBLE",
    "REAL_CORPUS",
    "SCOPE",
    "cli",
    "copy_corpus",
    "edit_scenario",
    "fixtures_mod",
    "grader",
    "read_scenario",
    "scenario_mod",
]


def copy_corpus(destination: Path) -> Path:
    """Copy the real corpus so a test can break one scenario without touching it."""
    target = destination / "scenarios"
    shutil.copytree(REAL_CORPUS, target)
    return target


def read_scenario(root: Path, scenario_id: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((root / scenario_id / "scenario.json").read_text("utf-8"))
    return data


def edit_scenario(root: Path, scenario_id: str, **changes: object) -> None:
    """Rewrite scenario.json with `changes`; a value of `None` deletes the key."""
    data = read_scenario(root, scenario_id)
    for key, value in changes.items():
        if value is None:
            data.pop(key, None)
        else:
            data[key] = value
    (root / scenario_id / "scenario.json").write_text(json.dumps(data, indent=2), "utf-8")
