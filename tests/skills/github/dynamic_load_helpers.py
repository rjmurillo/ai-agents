"""Shared setup for the completion-gate dynamic-load tests.

The gate is a script under `.claude/skills`, not an importable package, so the
tests load it by path once and share it.
"""

from __future__ import annotations

import importlib.util
import sys
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
GATE_PATH = (
    REPO_ROOT / ".claude" / "skills" / "github" / "scripts" / "pr" / "run_completion_gate.py"
)
NEW_PR = REPO_ROOT / ".claude" / "skills" / "github" / "scripts" / "pr" / "new_pr.py"


def _load_gate():
    spec = importlib.util.spec_from_file_location("run_completion_gate_dynamic", GATE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["run_completion_gate_dynamic"] = module
    spec.loader.exec_module(module)
    return module


gate = _load_gate()


def write(root: Path, relative: str, body: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return path


def loads(tmp_path: Path, body: str, name: str = "verify.py"):
    script = write(tmp_path, name, body)
    return gate._dynamic_loads(script.read_bytes(), script)


def closure(tmp_path: Path, *named: str) -> list[str]:
    return gate._expand_import_closure(list(named), tmp_path)
