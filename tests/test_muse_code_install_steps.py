"""Replay the Muse Code install block from the install guide into a scratch HOME.

Muse Code loads user skills from ``${XDG_CONFIG_HOME:-~/.config}/muse/skills/``,
not the personal agent's ``~/workspace/custom-skills/``. Skill scripts resolve
shared packages from ``lib/`` one level above the skills directory, so the
install must place ``lib/`` at ``~/.config/muse/lib/``. A re-run moves the old
copies to a backup directory and never deletes them (ADR-115 Decision 8).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
GUIDE = REPO_ROOT / "docs" / "training" / "install-on-every-host.md"
SECTION_HEADING = "### Install on Muse Code"
SKILL_SCRIPT = Path("github/scripts/pr/get_pr_checks.py")
LIB_MISSING_MESSAGE = "Plugin lib directory not found"
BACKUP_GLOB = "install-backup-*"
_LIB_RESOLUTION_ENV = frozenset(
    {"COPILOT_PLUGIN_ROOT", "CLAUDE_PLUGIN_ROOT", "GITHUB_WORKSPACE", "XDG_CONFIG_HOME"}
)

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="bash is required")


def _install_block() -> str:
    text = GUIDE.read_text(encoding="utf-8")
    section = text.split(SECTION_HEADING, 1)[1].split("\n### ", 1)[0]
    blocks = re.findall(r"```bash\n(.*?)```", section, flags=re.DOTALL)
    assert len(blocks) == 1, "expected exactly one bash block in the Muse Code section"
    # The guide indents the block under a numbered list item.
    return "\n".join(line.removeprefix("   ") for line in blocks[0].splitlines())


def _scratch_env(home: Path, xdg_config_home: Path | None = None) -> dict[str, str]:
    # GITHUB_WORKSPACE is always set in CI. The skill script would then read
    # $GITHUB_WORKSPACE/.claude/lib and hide the install layout under test.
    env = {k: v for k, v in os.environ.items() if k not in _LIB_RESOLUTION_ENV}
    env["HOME"] = str(home)
    if xdg_config_home is not None:
        env["XDG_CONFIG_HOME"] = str(xdg_config_home)
    return env


def _install(home: Path, xdg_config_home: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-euo", "pipefail", "-c", _install_block()],
        cwd=REPO_ROOT,
        env=_scratch_env(home, xdg_config_home),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
        check=False,
    )


def _run_skill_script(skills_root: Path, home: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", "-I", str(skills_root / SKILL_SCRIPT), "--help"],
        env=_scratch_env(home),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )


def _shipped_skill_names() -> set[str]:
    return {p.name for p in (REPO_ROOT / "src" / "muse" / "skills").iterdir() if p.is_dir()}


def test_install_places_every_skill_and_lib_under_the_muse_config_root(tmp_path: Path) -> None:
    installed = _install(tmp_path)

    assert installed.returncode == 0, installed.stderr
    root = tmp_path / ".config" / "muse"
    assert {p.name for p in (root / "skills").iterdir()} == _shipped_skill_names()
    assert (root / "lib" / "github_core").is_dir()
    assert not (tmp_path / "workspace").exists()
    assert not (tmp_path / ".agents").exists()


def test_installed_skill_script_resolves_lib_and_runs(tmp_path: Path) -> None:
    assert _install(tmp_path).returncode == 0

    result = _run_skill_script(tmp_path / ".config" / "muse" / "skills", tmp_path)

    assert result.returncode == 0, result.stderr
    assert "usage: get_pr_checks.py" in result.stdout


def test_skill_script_fails_with_missing_lib_message_when_lib_is_absent(tmp_path: Path) -> None:
    assert _install(tmp_path).returncode == 0
    root = tmp_path / ".config" / "muse"
    (root / "lib").rename(tmp_path / "lib-moved-away")

    result = _run_skill_script(root / "skills", tmp_path)

    assert result.returncode != 0
    assert LIB_MISSING_MESSAGE in result.stderr


def test_install_honors_xdg_config_home(tmp_path: Path) -> None:
    xdg = tmp_path / "xdg"

    assert _install(tmp_path / "home", xdg).returncode == 0

    assert (xdg / "muse" / "skills" / "github" / "SKILL.md").is_file()
    assert (xdg / "muse" / "lib" / "github_core").is_dir()
    assert not (tmp_path / "home" / ".config").exists()


def test_fresh_install_creates_no_backup(tmp_path: Path) -> None:
    assert _install(tmp_path).returncode == 0

    assert list((tmp_path / ".config" / "muse").glob(BACKUP_GLOB)) == []


def test_rerun_replaces_skills_and_lib_and_moves_old_copies_to_backup(tmp_path: Path) -> None:
    assert _install(tmp_path).returncode == 0
    root = tmp_path / ".config" / "muse"
    local_edit = root / "skills" / "github" / "local-edit.txt"
    local_edit.write_text("mine", encoding="utf-8")
    stale_module = root / "lib" / "dropped_upstream.py"
    stale_module.write_text("# removed in the new release\n", encoding="utf-8")
    user_skill = root / "skills" / "my-own-skill" / "SKILL.md"
    user_skill.parent.mkdir()
    user_skill.write_text("---\nname: my-own-skill\ndescription: x\n---\n", encoding="utf-8")

    rerun = _install(tmp_path)

    assert rerun.returncode == 0, rerun.stderr
    assert not local_edit.exists()
    assert not stale_module.exists()
    assert user_skill.is_file(), "a skill the toolkit does not ship must be left alone"
    (backup,) = root.glob(BACKUP_GLOB)
    assert (backup / "skills" / "github" / "local-edit.txt").read_text(encoding="utf-8") == "mine"
    assert (backup / "lib" / "dropped_upstream.py").is_file()
    assert _run_skill_script(root / "skills", tmp_path).returncode == 0


LIMIT_HEADING = "### Known limit: skill scripts under the default Muse Code sandbox"
# Each phrase is one fact issue #7364 asks the guide to state.
LIMIT_FACTS = {
    "the symptom users see": "[Errno 13] Permission denied",
    "the folder the sandbox denies": "~/.config/muse",
    "the workaround flag": "--disable-sandbox",
    "the absence of a supported allowlist": "no supported setting",
}


def _limit_section(text: str) -> str:
    """Return the guide's known-limit section, or "" when the heading is absent."""
    if LIMIT_HEADING not in text:
        return ""
    return text.split(LIMIT_HEADING, 1)[1].split("\n## ", 1)[0]


def _limit_gaps(text: str) -> list[str]:
    section = _limit_section(text)
    return [name for name, phrase in LIMIT_FACTS.items() if phrase not in section]


def test_guide_states_the_sandbox_limit_and_the_workaround() -> None:
    text = GUIDE.read_text(encoding="utf-8")

    assert _limit_section(text) != "", "the known-limit section is missing"
    assert _limit_gaps(text) == []


def test_guide_check_section_points_the_permission_denied_failure_at_the_limit() -> None:
    text = GUIDE.read_text(encoding="utf-8")
    check = text.split("### Check Muse Code", 1)[1].split(LIMIT_HEADING, 1)[0]

    assert "[Errno 13] Permission denied" in check
    assert "See the next section." in check


def test_limit_check_reports_every_fact_when_the_section_is_absent() -> None:
    assert _limit_gaps("### Check Muse Code\n\nOnly the old paragraph.\n") == list(LIMIT_FACTS)


def test_limit_check_reports_the_missing_workaround_and_nothing_else() -> None:
    text = GUIDE.read_text(encoding="utf-8")
    section = _limit_section(text)
    without_flag = text.replace(section, section.replace("--disable-sandbox", "--some-flag"))

    assert _limit_gaps(without_flag) == ["the workaround flag"]


def test_limit_check_ignores_facts_that_sit_outside_the_section() -> None:
    stub = f"{LIMIT_HEADING}\n\nNothing useful.\n\n## Next\n\n{' '.join(LIMIT_FACTS.values())}\n"

    assert _limit_gaps(stub) == list(LIMIT_FACTS)
