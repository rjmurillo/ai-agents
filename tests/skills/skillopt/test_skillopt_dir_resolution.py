"""ADR-121 decision 14: `SKILLOPT_DIR` comes from the same root as the locator.

The documented POSIX block runs `skillopt.py where` through the locator. A found
root wins over a preset value, a preset is used only when no root holds the
script, and the block aborts when neither exists. The PowerShell block is
hand-written, so a structure test pins its candidate order and its two checks.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_MD = REPO_ROOT / ".claude" / "skills" / "skillopt" / "SKILL.md"
DOGFOOD_ROOT = REPO_ROOT / ".claude"
SCRIPTS = "skills/skillopt/scripts"

pytestmark = pytest.mark.skipif(
    os.name != "posix" or shutil.which("bash") is None, reason="POSIX bash required"
)


def _posix_block() -> str:
    """Return the two documented lines that set and check `SKILLOPT_DIR`."""
    text = SKILL_MD.read_text(encoding="utf-8")
    found = re.search(r"^SKILLOPT_FOUND=.*$", text, re.MULTILINE)
    check = re.search(r'^: "\$\{SKILLOPT_DIR:\?.*$', text, re.MULTILINE)
    assert found and check, "SKILL.md has no SKILLOPT_DIR block"
    return f"{found.group(0)}\n{check.group(0)}\nprintf '%s' \"$SKILLOPT_DIR\"\n"


def _run(block: str, cwd: Path, **env: str) -> subprocess.CompletedProcess[str]:
    base = {k: v for k, v in os.environ.items() if "PLUGIN_ROOT" not in k and k != "SKILLOPT_DIR"}
    return subprocess.run(
        ["bash", "-c", block],
        cwd=cwd,
        env={**base, **env},
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )


def _foreign_root(tmp_path: Path) -> Path:
    """A root that holds a same-named script but not our resolver (issue #7281)."""
    script = tmp_path / "foreign" / SCRIPTS / "skillopt.py"
    script.parent.mkdir(parents=True)
    script.write_text("print('/foreign/scripts')\n", encoding="utf-8")
    return tmp_path / "foreign"


def test_where_prints_the_scripts_folder_of_the_chosen_root(tmp_path: Path) -> None:
    result = _run(
        _posix_block(),
        tmp_path,
        CLAUDE_PLUGIN_ROOT=str(DOGFOOD_ROOT),
        COPILOT_PLUGIN_ROOT=str(_foreign_root(tmp_path)),
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == str(DOGFOOD_ROOT / SCRIPTS)


def test_a_found_root_wins_over_a_preset(tmp_path: Path) -> None:
    result = _run(
        _posix_block(),
        tmp_path,
        CLAUDE_PLUGIN_ROOT=str(DOGFOOD_ROOT),
        SKILLOPT_DIR="/preset/scripts",
    )
    assert (result.returncode, result.stdout) == (0, str(DOGFOOD_ROOT / SCRIPTS))


def test_a_preset_is_kept_when_no_root_holds_the_script(tmp_path: Path) -> None:
    result = _run(_posix_block(), tmp_path, SKILLOPT_DIR="/preset/scripts")
    assert (result.returncode, result.stdout) == (0, "/preset/scripts")
    assert result.stderr.startswith("ptk_run:")


def test_no_root_and_no_preset_aborts_loud(tmp_path: Path) -> None:
    result = _run(_posix_block(), tmp_path, COPILOT_PLUGIN_ROOT=str(_foreign_root(tmp_path)))
    assert result.returncode != 0
    assert result.stdout == ""
    assert "SKILLOPT_DIR" in result.stderr


def test_powershell_block_probes_resolver_and_target_in_locator_order() -> None:
    text = SKILL_MD.read_text(encoding="utf-8")
    block = text.split("```powershell", 1)[1].split("```", 1)[0]
    assert "@($env:CLAUDE_PLUGIN_ROOT, $env:COPILOT_PLUGIN_ROOT, '.claude')" in block
    assert block.count("Test-Path -LiteralPath") == 2
    assert "'lib/ptk_run.py'" in block
    assert "'skills/skillopt/scripts/skillopt.py'" in block
    assert block.index("if ($Found)") < block.index("if (-not $SkillOptDir)")
    assert "COPILOT_PLUGIN_ROOT) { $env:COPILOT_PLUGIN_ROOT }" not in block
