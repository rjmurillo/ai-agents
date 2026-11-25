"""The ship spec names every STOP reason and NEXT act the scripts can print.

#7586 builds the driver's STOP table from this set, so a reason the spec
omits would leave a STOP with no fix section.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SPEC = ROOT / ".project-toolkit" / "specs" / "SPEC-ship-driver.md"
SCRIPTS = ROOT / "src" / "claude" / "skills" / "ship" / "scripts"
_TOKEN = r'"([a-z][a-z0-9-]*)"'


def next_acts() -> set[str]:
    """Every literal act passed to ``result.next`` in the ship scripts."""
    acts: set[str] = set()
    for path in sorted(SCRIPTS.glob("ship_*.py")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if ".next(" in line:
                acts.update(re.findall(_TOKEN, line))
    return acts


def missing_from(spec: str, names: set[str]) -> list[str]:
    return sorted(name for name in names if f"`{name}`" not in spec)


@pytest.mark.parametrize("index", [1, 2, 3])
def test_every_stop_reason_is_in_the_spec(scripts, index):
    assert missing_from(SPEC.read_text(encoding="utf-8"), set(scripts[index].REASONS)) == []


def test_every_next_act_is_in_the_spec():
    acts = next_acts()
    assert {"preflight", "rerun-pipeline", "compare-paths-by-hand", "discharge"} <= acts
    assert missing_from(SPEC.read_text(encoding="utf-8"), acts) == []


def test_a_name_the_spec_omits_is_reported():
    spec = SPEC.read_text(encoding="utf-8").replace("`paths-not-checked`", "paths-not-checked")
    assert missing_from(spec, {"paths-not-checked", "tree-dirty"}) == ["paths-not-checked"]
