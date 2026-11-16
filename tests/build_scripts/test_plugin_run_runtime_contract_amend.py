"""ADR-121 decisions 11 and 12 under the real locator text, run through `sh -c`.

The committed locator runs from a working directory that is not a plugin root, as
in `test_plugin_run_runtime_contract.py`, whose fixtures this module reuses.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

from tests.build_scripts.test_plugin_run_runtime_contract import (
    REPO_ROOT,
    SCRIPT,
    World,
    _argv,
    _resolver,
    _run,
    _tag,
    pytestmark,
)
from tests.build_scripts.test_plugin_run_runtime_contract import world as world

sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))
from plugin_run_launcher import ISOLATED_INTERPRETER, UV_INTERPRETER, render_locator

__all__ = ["pytestmark"]


# ---- ADR-121 decision 11: fallthrough to a root that holds the target -------------------


def test_a_root_with_the_resolver_but_not_the_target_falls_through_to_ours(
    world: World,
) -> None:
    """PR #7340: a sibling pack holds the resolver but not this skill."""
    sibling = world.base / "sibling-pack"
    _resolver(sibling)
    result = _run(
        world,
        render_locator(SCRIPT, "a"),
        CLAUDE_PLUGIN_ROOT=str(sibling),
        COPILOT_PLUGIN_ROOT=str(world.ours),
    )
    assert (result.returncode, _tag(result), _argv(result)) == (0, "ours", ["a"])
    assert result.stderr.startswith("ptk_run: note: ")


def test_fallthrough_never_reaches_a_root_without_the_resolver(world: World) -> None:
    """Issue #7281: a foreign same-named script without our resolver still never runs."""
    sibling = world.base / "sibling-pack"
    _resolver(sibling)
    result = _run(
        world,
        render_locator(SCRIPT),
        CLAUDE_PLUGIN_ROOT=str(sibling),
        COPILOT_PLUGIN_ROOT=str(world.foreign_script),
    )
    assert result.returncode == 2
    assert result.stderr.startswith("ptk_run: target is not a file under any plugin root")
    assert result.stdout == ""


# ---- ADR-121 decision 12: interpreter forms ---------------------------------------------

ISOLATION_PROBE = "import json, sys\nprint(json.dumps({'isolated': sys.flags.isolated}))\n"


def test_the_isolated_locator_runs_the_target_isolated(world: World) -> None:
    probe = world.ours / "skills" / "x" / "scripts" / "iso.py"
    probe.write_text(ISOLATION_PROBE, encoding="utf-8")
    plain = _run(
        world, render_locator("skills/x/scripts/iso.py"), COPILOT_PLUGIN_ROOT=str(world.ours)
    )
    isolated = _run(
        world,
        render_locator("skills/x/scripts/iso.py", interpreter=ISOLATED_INTERPRETER),
        COPILOT_PLUGIN_ROOT=str(world.ours),
    )
    assert json.loads(plain.stdout) == {"isolated": 0}
    assert json.loads(isolated.stdout) == {"isolated": 1}


def test_the_isolated_locator_ignores_a_planted_module_in_the_cwd(world: World) -> None:
    """`-I` drops the cwd and PYTHONPATH from the import path, for the target too."""
    planted = world.cwd / "json.py"
    planted.write_text("raise SystemExit('planted json imported')\n", encoding="utf-8")
    result = _run(
        world,
        render_locator(SCRIPT, interpreter=ISOLATED_INTERPRETER),
        COPILOT_PLUGIN_ROOT=str(world.ours),
        PYTHONPATH=str(world.cwd),
    )
    assert (result.returncode, _tag(result)) == (0, "ours"), result.stderr


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv required")
def test_the_uv_locator_runs_the_target_with_the_resolver_interpreter(world: World) -> None:
    probe = world.ours / "skills" / "x" / "scripts" / "exe.py"
    probe.write_text("import sys\nprint(sys.executable)\n", encoding="utf-8")
    result = _run(
        world,
        render_locator("skills/x/scripts/exe.py", interpreter=UV_INTERPRETER),
        COPILOT_PLUGIN_ROOT=str(world.ours),
    )
    assert result.returncode == 0, result.stderr
    assert Path(result.stdout.strip()).name.startswith("python")
