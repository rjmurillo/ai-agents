"""Bind the SKILL.md contract for the capability scripts (mine, forms, drift, eval).

Companion to test_skill_md_contract.py, which owns the boundary-script contract.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_skill_md_contract import PORTABLE_SCRIPT, _skill_dir, _skill_md

BUNDLED_SCRIPTS = (
    "scripts/bootstrap_boundary.py",
    "scripts/bootstrap_mine.py",
    "scripts/bootstrap_forms.py",
    "scripts/bootstrap_drift.py",
    "scripts/bootstrap_eval.py",
)


def test_capability_eval_runs_between_context_optimizer_and_skillopt() -> None:
    text = _skill_md()
    heading = re.search(r"^### Phase 5: .*$", text, re.MULTILINE)
    assert heading is not None
    title = heading.group(0)
    assert title.index("context-optimizer") < title.index("capability eval")
    assert title.index("capability eval") < title.index("skillopt")


@pytest.mark.parametrize(
    "script", ("bootstrap_mine.py", "bootstrap_forms.py", "bootstrap_drift.py", "bootstrap_eval.py")
)
def test_every_bundled_script_is_documented_with_the_portable_root(script: str) -> None:
    portable = PORTABLE_SCRIPT.replace("bootstrap_boundary.py", script)

    assert f'python3 "{portable}"' in _skill_md()


def test_every_script_on_disk_is_bundled_and_documented() -> None:
    on_disk = {f"scripts/{p.name}" for p in (_skill_dir(".claude") / "scripts").glob("*.py")}
    text = _skill_md()

    assert on_disk == set(BUNDLED_SCRIPTS)
    for rel in sorted(on_disk):
        portable = PORTABLE_SCRIPT.replace("bootstrap_boundary.py", rel.removeprefix("scripts/"))
        assert f'python3 "{portable}"' in text, rel


def test_skill_md_defines_both_tool_forms_and_both_modes() -> None:
    text = _skill_md()

    for term in ("**scaffold**", "**instrument**", "`workflow` (default)", "`knowledge`"):
        assert term in text, term
