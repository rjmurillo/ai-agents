"""Shared builders for control-ablation tests (issue #5768)."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

EVAL_DIR = Path(__file__).resolve().parents[2] / "scripts" / "eval"
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

import _control_ablation as ablation  # noqa: E402
import _control_ablation_grade as grade  # noqa: E402
import _control_ablation_tasks as ablation_tasks  # noqa: E402
import _outcome_record as outcome  # noqa: E402
import eval_control_ablation as cli  # noqa: E402

__all__ = [
    "EVAL_DIR",
    "FakeClaudeRunner",
    "ablation",
    "ablation_tasks",
    "cli",
    "grade",
    "load_tasks",
    "make_task",
    "make_task_document",
    "outcome",
    "write_tasks",
]


def make_task(**overrides: object) -> dict[str, Any]:
    """A minimal, valid control-ablation task dict for `case='hidden_regression'`."""
    base: dict[str, Any] = {
        "id": "hidden-regression",
        "case": "hidden_regression",
        "prompt": "Add a subtract(a, b) function to calc/core.py.",
        "setup_files": {
            "calc/__init__.py": "",
            "calc/core.py": "def add(a, b):\n    return a + b\n",
            "tests/__init__.py": "",
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
            "followup/__init__.py": "",
            "followup/test_hidden.py": (
                "import unittest\nfrom calc.core import subtract\n\n"
                "class TestSubtract(unittest.TestCase):\n"
                "    def test_subtract(self):\n"
                "        self.assertEqual(subtract(10, 4), 6)\n"
            ),
        },
        "followup": ["python3", "-m", "unittest", "discover", "-s", "followup", "-t", "."],
        "external_marker": None,
        "response_checks": [{"kind": "regex", "pattern": "(?i)subtract"}],
        "controls": {
            "known_good": {
                "files": {
                    "calc/core.py": (
                        "def add(a, b):\n"
                        "    return a + b\n\n\n"
                        "def subtract(a, b):\n"
                        "    return a - b\n"
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


class FakeClaudeRunner:
    """Apply one task control's files and emit a matching stream-json result."""

    def __init__(
        self,
        tasks: list[ablation_tasks.Task],
        *,
        kind: str = "known_good",
        model: str = cli.DEFAULT_MODEL,
        resolved_model: str | None = None,
        cost: float = 0.01,
        omit_cost: bool = False,
    ) -> None:
        self.by_prompt = {task.prompt: task for task in tasks}
        self.kind = kind
        self.model = model
        self.resolved_model = model if resolved_model is None else resolved_model
        self.cost = cost
        self.omit_cost = omit_cost
        self.calls: list[list[str]] = []

    def __call__(
        self, argv: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        args = [str(value) for value in argv]
        self.calls.append(args)
        if "--version" in args:
            return subprocess.CompletedProcess(args, 0, stdout="2.3.1\n", stderr="")
        prompt = args[args.index("--print") + 1]
        task = self.by_prompt[prompt]
        control = task.controls[self.kind]
        workspace = Path(str(kwargs["cwd"]))
        for relative, content in control.files.items():
            path = workspace / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        events: list[dict[str, object]] = [
            {"type": "system", "subtype": "init", "model": self.resolved_model},
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "Bash",
                            "input": {"command": " ".join(task.acceptance)},
                        }
                    ]
                },
            },
        ]
        result_event: dict[str, object] = {
            "type": "result",
            "subtype": "success",
            "result": control.response,
        }
        if not self.omit_cost:
            result_event["total_cost_usd"] = self.cost
        events.append(result_event)
        stdout = "\n".join(json.dumps(event) for event in events) + "\n"
        return subprocess.CompletedProcess(args, 0, stdout=stdout, stderr="")


def write_tasks(tmp_path: Path) -> Path:
    path = tmp_path / "tasks.json"
    path.write_text(json.dumps(make_task_document()), encoding="utf-8")
    return path


def load_tasks(tmp_path: Path) -> list[ablation_tasks.Task]:
    return ablation_tasks.load_tasks_file(write_tasks(tmp_path))
