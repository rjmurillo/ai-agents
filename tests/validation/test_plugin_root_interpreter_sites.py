"""Site detection for the plugin-root validator: shell names and locator lookup paths (ADR-121).

``plugin_root_interpreter_sites.py`` is the one definition of a site that the validator,
the ratchet, and ``build/scripts/plugin_run_fix.py`` share.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from scripts.validation import check_plugin_root_interpreter as checker
from scripts.validation import plugin_root_interpreter_sites as sites
from tests.validation.test_check_plugin_root_interpreter import REPO_ROOT, make_repo

sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))
from plugin_run_launcher import render_locator

_ROOT = "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}"
_BAR = "skills/foo/scripts/bar.py"
_STDLIB = {f".claude/{_BAR}": "import json\n"}


# --- assignment names ------------------------------------------------------


@pytest.mark.parametrize("name", ["SCRIPTS_DIR", "SCRIPTS_DIR2", "_dir", "d9_x", "A1"])
def test_a_valid_shell_name_is_an_assignment(name: str) -> None:
    text = f'{name}="{_ROOT}/skills/foo"\n'
    assert sites.count_legacy_sites(text) == sites.LegacyCounts(invocations=0, assignments=1)


@pytest.mark.parametrize("name", ["2DIR", "SCRIPTS-DIR", "SCRIPTS DIR", "a.b"])
def test_a_string_that_is_not_a_shell_name_is_not_an_assignment(name: str) -> None:
    text = f'{name}="{_ROOT}/skills/foo"\n'
    assert sites.count_legacy_sites(text).assignments == 0


# --- the lookup path of a locator ------------------------------------------


@pytest.mark.parametrize(
    ("script_rel", "expected"),
    [
        (_BAR, _BAR),
        ("skills/foo/./scripts/bar.py", _BAR),
        ("skills//foo/scripts/bar.py", _BAR),
        ("skills/foo/./././scripts/bar.py", _BAR),
        ("skills/../bar.py", "skills/../bar.py"),
        ("skills/../../etc/x.py", "skills/../../etc/x.py"),
    ],
)
def test_lookup_path_collapses_dot_and_slash_runs_and_stays_inside_skills(
    script_rel: str, expected: str
) -> None:
    assert sites.lookup_path(script_rel) == expected


def _locator_text(script_rel: str) -> str:
    return f"Run `{render_locator(script_rel)}`.\n"


@pytest.mark.parametrize(
    "script_rel", ["skills/foo/./scripts/bar.py", "skills//foo/scripts/bar.py"]
)
def test_a_locator_with_dot_segments_finds_its_tracked_target(
    tmp_path: Path, script_rel: str
) -> None:
    repo = make_repo(tmp_path, {**_STDLIB, "README.md": _locator_text(script_rel)})
    assert checker.scan(repo) == []


def test_the_locator_text_keeps_the_path_as_written() -> None:
    script_rel = "skills/foo/./scripts/bar.py"
    [found] = sites.find_locator_invocations(render_locator(script_rel))
    assert script_rel in render_locator(script_rel)
    assert found.tail == _BAR


def test_a_missing_target_with_dot_segments_is_still_dangling(tmp_path: Path) -> None:
    """Negative control: normalizing the lookup does not make a missing file pass."""
    text = _locator_text("skills/foo/./scripts/missing.py")
    [offense] = checker.scan(make_repo(tmp_path, {**_STDLIB, "README.md": text}))
    assert ".claude/skills/foo/scripts/missing.py is not a tracked file" in offense
