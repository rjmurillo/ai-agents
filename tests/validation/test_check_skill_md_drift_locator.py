"""ADR-121: the drift path scan does not read a locator's script target as a path."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))

from plugin_run_launcher import render_locator

from scripts.validation.check_skill_md_drift import _extract_paths_from_text

TARGET = "skills/memory/scripts/search_memory.py"


def test_a_locator_target_is_not_a_path_reference() -> None:
    text = f"Run `{render_locator(TARGET, chr(34) + 'topic' + chr(34))}` first."
    assert _extract_paths_from_text(text) == set()


def test_negative_control_the_same_target_outside_a_locator_is_a_path_reference() -> None:
    assert TARGET in _extract_paths_from_text(f"Open {TARGET} before you start.")


def test_text_around_a_locator_still_counts() -> None:
    text = f"See .agents/governance/foo.md then run {render_locator(TARGET)}."
    assert _extract_paths_from_text(text) == {".agents/governance/foo.md"}


def test_two_locators_on_one_line_are_both_blanked() -> None:
    line = f"{render_locator(TARGET)} and {render_locator('skills/memory/scripts/other.py')}"
    assert _extract_paths_from_text(line) == set()
