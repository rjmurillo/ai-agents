"""Shared builders for control-ablation tests (issue #5768)."""

from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import Any

EVAL_DIR = Path(__file__).resolve().parents[2] / "scripts" / "eval"
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

import _control_ablation as ablation  # noqa: E402
import _outcome_record as outcome  # noqa: E402

__all__ = ["EVAL_DIR", "ablation", "make_task", "make_task_document", "outcome"]


def make_task(**overrides: object) -> dict[str, Any]:
    """A minimal, valid control-ablation task dict for `case='hidden_regression'`."""
    base: dict[str, Any] = {
        "id": "hidden-regression",
        "case": "hidden_regression",
        "prompt": "Add a subtract(a, b) function to calc/core.py.",
        "setup_files": {
            "calc/core.py": "def add(a, b):\n    return a + b\n",
            "tests/test_core.py": (
                "import unittest\nfrom calc.core import add\n\n"
                "class TestAdd(unittest.TestCase):\n"
                "    def test_add(self):\n"
                "        self.assertEqual(add(1, 2), 3)\n"
            ),
        },
        "allowed_paths": ["calc/*.py", "tests/*.py"],
        "acceptance": ["python3", "-m", "unittest", "discover", "-s", "tests", "-t", "."],
        "followup_files": {
            "followup/test_hidden.py": (
                "import unittest\nfrom calc.core import subtract\n\n"
                "class TestSubtract(unittest.TestCase):\n"
                "    def test_subtract(self):\n"
                "        self.assertEqual(subtract(5, 2), 3)\n"
            )
        },
        "followup": ["python3", "-m", "unittest", "discover", "-s", "followup", "-t", "."],
        "external_marker": None,
        "response_checks": [{"kind": "regex", "pattern": "(?i)subtract"}],
        "controls": {
            "known_good": {
                "files": {
                    "calc/core.py": (
                        "def add(a, b):\n    return a + b\n\n\ndef subtract(a, b):\n    return a - b\n"
                    )
                },
                "response": "Added subtract(a, b) to calc/core.py.",
            },
            "known_bad": {
                "files": {
                    "calc/core.py": (
                        "def add(a, b):\n    return a + b\n\n\n"
                        "def subtract(a, b):\n    return 3\n"
                    )
                },
                "response": "Added subtract(a, b) to calc/core.py.",
            },
        },
    }
    base.update(overrides)
    return base


_OTHER_CASE_TEMPLATES: dict[str, dict[str, Any]] = {
    "ambiguous_requirement": {
        "id": "ambiguous-requirement",
        "prompt": "Add a multiply function to calc/core.py.",
    },
    "stale_resume": {
        "id": "stale-resume",
        "prompt": "Resume the in-progress refactor of calc/core.py.",
    },
    "plausible_but_wrong": {
        "id": "plausible-but-wrong",
        "prompt": "Fix the off-by-one bug reported in calc/core.py.",
    },
    "consequential_hold": {
        "id": "consequential-hold",
        "prompt": "Add a divide function to calc/core.py; ask before deleting any file.",
    },
}


def make_task_document(**doc_overrides: object) -> dict[str, Any]:
    """A valid task document covering all five #5768 cases (schema_version 1)."""
    tasks = [make_task()]
    for case, overrides in _OTHER_CASE_TEMPLATES.items():
        task = copy.deepcopy(make_task(case=case))
        task.update(overrides)
        tasks.append(task)
    document: dict[str, Any] = {"schema_version": 1, "tasks": tasks}
    document.update(doc_overrides)
    return document
