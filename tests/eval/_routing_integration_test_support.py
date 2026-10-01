"""Shared helpers for post-integration regression tests (issue #5768)."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from tests.eval._routing_corpus_test_support import (
    EVAL_DIR,
    REAL_CORPUS,
    edit_scenario,
    grader,
    read_scenario,
    scenario_mod,
)

EXTENSION_CORPUS = Path(__file__).resolve().parents[2] / "evals" / "durable-outcome-live" / "corpus"
TOP_SCORES = "HR-01-top-scores-order"
MERGE_SETTINGS = "HR-02-merge-settings-defaults"
TASKS = (TOP_SCORES, MERGE_SETTINGS)

__all__ = [
    "EVAL_DIR",
    "EXTENSION_CORPUS",
    "MERGE_SETTINGS",
    "REAL_CORPUS",
    "TASKS",
    "TOP_SCORES",
    "copy_extension",
    "edit_scenario",
    "grader",
    "load_extension",
    "read_scenario",
    "scenario_mod",
]


def load_extension(task_id: str) -> Any:
    found = scenario_mod.load_extension_corpus(EXTENSION_CORPUS)
    return next(s for s in found if s.scenario_id == task_id)


def copy_extension(destination: Path) -> Path:
    """Copy the extension corpus so a test can break one scenario without touching it."""
    target = destination / "extension"
    shutil.copytree(EXTENSION_CORPUS, target)
    return target
