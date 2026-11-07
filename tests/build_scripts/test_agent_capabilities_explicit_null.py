"""An explicit null platform tools key is authoritative, as the generator treats it (#6506)."""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[2] / "build" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import agent_capabilities as caps  # noqa: E402

DECLARATION_UNIT = f"copilot:{caps.DECLARATION}"


def _units(frontmatter: dict[str, object]) -> dict[str, str]:
    return caps.capability_units(frontmatter, "tools_copilot", "copilot", {}, fallback_key="tools")


def test_null_platform_key_does_not_fall_back_to_the_bare_key() -> None:
    units = _units({"tools_copilot": None, "tools": "read, edit"})

    assert units == {DECLARATION_UNIT: caps.UNRESTRICTED}


def test_absent_platform_key_falls_back_to_the_bare_key() -> None:
    units = _units({"tools": "read, edit"})

    assert units[DECLARATION_UNIT] != caps.UNRESTRICTED
