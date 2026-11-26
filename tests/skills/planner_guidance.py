"""Load the planner skill's planner.py and executor.py, and flatten their guidance.

The planner delegation tests read the text both scripts emit, so they share
one copy of each loaded script and one way to join a guidance dict.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

SCRIPTS = Path(__file__).resolve().parents[2] / "src" / "claude" / "skills" / "planner" / "scripts"


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        f"planner_guidance_{name}", SCRIPTS / f"{name}.py"
    )
    assert spec is not None and spec.loader is not None, name
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


planner = _load("planner")
executor = _load("executor")


def flatten(guidance: dict) -> str:
    """Join every guidance value, list items included, one per line."""
    parts: list[str] = []
    for value in guidance.values():
        parts.extend(value if isinstance(value, list) else [str(value)])
    return "\n".join(parts)
