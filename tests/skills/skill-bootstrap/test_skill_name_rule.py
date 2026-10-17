"""The three skill-bootstrap scripts apply one skill-name rule.

Skill scripts do not import each other, so each repeats the rule of
`bootstrap_boundary.name_defects`. This table keeps the copies from drifting.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / ".claude" / "skills" / "skill-bootstrap" / "scripts"


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(f"rule_{name}", module)
    spec.loader.exec_module(module)
    return module


boundary = _load("bootstrap_boundary")
drift = _load("bootstrap_drift")
forms = _load("bootstrap_forms")

NAMES = {
    "a": True,
    "abc-def": True,
    "a1": True,
    "a" * 64: True,
    "a--b": False,
    "a" * 65: False,
    "A": False,
    "-a": False,
    "a-": False,
    "1a": False,
    "a_b": False,
    "": False,
}


@pytest.mark.parametrize(("name", "valid"), NAMES.items())
def test_all_three_scripts_agree(name, valid):
    assert (not boundary.name_defects(name)) is valid
    assert drift.valid_skill_name(name) is valid
    assert forms.valid_skill_name(name) is valid
