"""Bind the skill-bootstrap SKILL.md contract to the shipped script and files.

The SKILL.md documents triggers, a portable script path, bundled references,
the phase order, and exit codes. These tests read the rendered SKILL.md from
every shipped root, so prose drift goes red. The exit-code behavior itself is
asserted in test_plan.py, test_snapshot.py, and test_verify.py.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _template_contract import assert_template_owned_contract

REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_REL = Path("skills") / "skill-bootstrap"
SHIPPED_ROOTS = (".claude", "src/claude", "src/copilot-cli", "src/codex")
TRIGGERS = (
    "bootstrap skills",
    "capture project workflow knowledge",
    "build this repo's skill library",
    "project skill library",
)
BUNDLED = (
    "scripts/bootstrap_boundary.py",
    "references/discovery.md",
    "references/hosted-platforms.md",
    "references/authoring-and-gates.md",
)
PORTABLE_SCRIPT = (
    "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}"
    "/skills/skill-bootstrap/scripts/bootstrap_boundary.py"
)
LINK_RE = re.compile(r"\]\((references/[^)#\s]+)(?:#[^)]*)?\)")


def _skill_dir(root: str) -> Path:
    return REPO_ROOT / root / SKILL_REL


def _skill_md(root: str = ".claude") -> str:
    return (_skill_dir(root) / "SKILL.md").read_text(encoding="utf-8")


def test_skill_md_is_template_owned() -> None:
    assert_template_owned_contract("skill-bootstrap")


@pytest.mark.parametrize("root", SHIPPED_ROOTS)
def test_root_ships_the_skill_md_and_bundled_files(root: str) -> None:
    # The skill is shipped, not repo-local, so every root carries all of it.
    # A missing bundled file means the build mirror is stale.
    skill_dir = _skill_dir(root)
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    assert text.startswith("---\nname: skill-bootstrap\n")
    for rel in BUNDLED:
        assert (skill_dir / rel).is_file(), f"{root}: {rel}"


@pytest.mark.parametrize("root", SHIPPED_ROOTS)
def test_triggers_are_present(root: str) -> None:
    text = _skill_md(root)
    for trigger in TRIGGERS:
        assert trigger in text, f"{root}: {trigger}"


@pytest.mark.parametrize("root", SHIPPED_ROOTS)
def test_reference_links_resolve(root: str) -> None:
    links = LINK_RE.findall(_skill_md(root))
    assert links, "SKILL.md links no references"
    for link in links:
        assert (_skill_dir(root) / link).is_file(), f"{root}: {link}"


@pytest.mark.parametrize("root", SHIPPED_ROOTS)
def test_script_path_is_portable(root: str) -> None:
    text = _skill_md(root)
    assert f'python3 "{PORTABLE_SCRIPT}" snapshot' in text
    assert f'python3 "{PORTABLE_SCRIPT}" plan' in text
    assert f'python3 "{PORTABLE_SCRIPT}" verify' in text


def test_context_optimizer_stage_precedes_skillopt_in_process() -> None:
    text = _skill_md()
    process = text[text.index("## Process") :]
    heading = re.search(r"^### Phase 5: .*$", process, re.MULTILINE)
    assert heading is not None
    title = heading.group(0)
    assert "context-optimizer" in title
    assert "skillopt" in title
    assert title.index("context-optimizer") < title.index("skillopt")


def test_skill_md_documents_exit_codes_in_a_table_with_one_row_per_script() -> None:
    text = _skill_md()
    assert "Exit code 0 means success and exit code 1 means findings" in text
    header = "| Script | Exit 2: configuration | Exit 3: external |"
    assert header in text
    rows = text.split(header, 1)[1].split("\n\n", 1)[0].splitlines()[2:]
    named = {row.split("|")[1].strip().strip("`") for row in rows}
    assert named == {
        "bootstrap_mine.py",
        "bootstrap_forms.py",
        "bootstrap_eval.py",
        "bootstrap_drift.py",
        "bootstrap_boundary.py",
    }


def test_documented_plan_help_runs_from_unrelated_directory(tmp_path: Path) -> None:
    script = _skill_dir(".claude") / "scripts" / "bootstrap_boundary.py"

    result = subprocess.run(
        [sys.executable, str(script), "plan", "--help"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("root", SHIPPED_ROOTS[1:])
def test_shipped_script_is_byte_identical_to_dogfood_copy(root: str) -> None:
    for rel in BUNDLED:
        source = (_skill_dir(".claude") / rel).read_bytes()
        assert (_skill_dir(root) / rel).read_bytes() == source, f"{root}: {rel}"
