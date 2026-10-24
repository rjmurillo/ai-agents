"""The completion gate's scanner resolves agent_registry's build-utility load.

An unresolvable load fails the scheduled closure manifest closed
(`scripts/validation/closure_manifest.py`). The scanner resolves only a path
built from `__file__` and literals, so a parameter-driven path regresses it.
"""

from __future__ import annotations

from pathlib import Path

from scripts.validation import agent_registry
from tests.skills.github.dynamic_load_helpers import gate


def test_the_build_utility_load_is_resolved_not_flagged() -> None:
    script = Path(agent_registry.__file__).resolve()
    loads = gate._dynamic_loads(script.read_bytes(), script)
    assert [load.path for load in loads] == [agent_registry._BUILD_UTILITY_PATH]
