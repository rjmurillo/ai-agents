"""Shared loader for runtime parity evaluator tests."""

from __future__ import annotations

import importlib.util
import json
import subprocess
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
runtime_harness = sys.modules["_runtime_harness"]
runtime_grader = sys.modules["_runtime_grader"]


class FixedResponseRunner:
    """A CLI runner that answers every fixture with one fixed response."""

    def __init__(self, response: str, *, model: str = parity.DEFAULT_MODEL) -> None:
        self.response = response
        self.model = model
        self.calls: list[list[str]] = []

    def __call__(self, argv, **kwargs):
        args = [str(value) for value in argv]
        self.calls.append(args)
        executable = Path(args[0]).name.lower()
        if "--version" in args:
            return subprocess.CompletedProcess(args, 0, f"{executable} test-version\n", "")
        if executable.startswith("claude"):
            output = [
                {"type": "system", "subtype": "init", "model": self.model},
                {"type": "result", "subtype": "success", "result": self.response},
            ]
        else:
            output = [
                {
                    "type": "assistant.message",
                    "data": {"content": self.response, "model": self.model},
                }
            ]
        return subprocess.CompletedProcess(
            args, 0, "\n".join(json.dumps(event) for event in output) + "\n", ""
        )


def corpus_with_instructions(
    tmp_path: Path,
    *,
    instructions: list[str] | None = None,
    default_instructions: bool = True,
    semantic: bool = False,
) -> Path:
    source = json.loads(FIXTURES.read_text(encoding="utf-8"))
    fixture = dict(source["fixtures"][0])  # "resume-phase-3"
    if instructions is None and default_instructions:
        instructions = [".claude/rules/voice.md"]
    if instructions is not None:
        fixture["instructions"] = list(instructions)
    if semantic:
        fixture["assertions"] = [
            *fixture["assertions"],
            {"kind": "semantic", "rubric": "FAIL on any continuation offer; PASS otherwise."},
        ]
    path = tmp_path / "fixtures.json"
    path.write_text(
        json.dumps({"schema_version": 1, "fixtures": [fixture]}), encoding="utf-8"
    )
    return path
