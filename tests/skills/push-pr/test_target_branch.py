"""push-pr checks and opens a GitHub PR against the named target branch.

Issue #7660: step 5 ran the validator with ``--base origin/main`` and step 7
ran ``new_pr.py`` with no ``--base``, so a PR meant for another branch was
checked against and opened on the default branch. These tests pin the fix in
the template and in every rendered copy.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
TEMPLATE = REPO_ROOT / "templates" / "skills" / "push-pr.SKILL.md.tmpl"
RENDERED = [
    REPO_ROOT / "src" / tree / "skills" / "push-pr" / "SKILL.md"
    for tree in (
        "claude",
        "copilot-cli",
        "codex",
        "cursor",
        "muse",
        "hermes/project-toolkit-delivery",
    )
]
COPIES = [TEMPLATE, *RENDERED]
_SECTION_RE = r"^## {heading}\n(.*?)(?=^## |\Z)"
_ITEM_RE = re.compile(r"^(\d+)\. ", re.M)


def _section(text: str, heading: str) -> str:
    match = re.search(_SECTION_RE.format(heading=re.escape(heading)), text, re.M | re.S)
    assert match, f"push-pr must carry a '## {heading}' section"
    return match.group(1)


def _step(process: str, number: int) -> str:
    starts = [(int(m.group(1)), m.start()) for m in _ITEM_RE.finditer(process)]
    for index, (found, begin) in enumerate(starts):
        if found == number:
            end = starts[index + 1][1] if index + 1 < len(starts) else len(process)
            return process[begin:end]
    raise AssertionError(f"Process has no step {number}")


@pytest.fixture(params=COPIES, ids=lambda p: str(p.relative_to(REPO_ROOT)))
def skill_text(request: pytest.FixtureRequest) -> str:
    return Path(request.param).read_text(encoding="utf-8")


@pytest.fixture
def process(skill_text: str) -> str:
    return _section(skill_text, "Process")


def test_process_names_the_target_branch_before_step_1(process: str) -> None:
    first_step = _ITEM_RE.search(process)
    assert first_step, "Process has no numbered steps"
    preamble = process[: first_step.start()]
    assert "`<target>`" in preamble
    assert "default branch" in preamble
    guard = "Accept only a name made of letters, digits, `.`, `_`, `/`, and `-`;"
    assert f"{guard} otherwise stop and ask the user" in " ".join(preamble.split())


def test_no_github_step_hardcodes_origin_main(process: str) -> None:
    assert "origin/main" not in process


def test_step_5_validates_against_the_target(process: str) -> None:
    step = _step(process, 5)
    assert "--base origin/<target>" in step
    assert "git diff origin/<target>...HEAD" in step


def test_step_7_opens_the_pr_against_the_target(process: str) -> None:
    step = " ".join(_step(process, 7).split())
    assert 'add `--base "<target>"` inside the command, before its `; fi`' in step


def test_windows_fallback_step_7_opens_the_pr_against_the_target(skill_text: str) -> None:
    fallback = " ".join(_section(skill_text, "Windows PR Body Fallback").split())
    assert 'add `--base "<target>"` before the `; fi`, as in step 7' in fallback


def test_ado_target_branch_rule_is_unchanged() -> None:
    ado = " ".join(
        _section(TEMPLATE.read_text(encoding="utf-8"), "Azure DevOps PR Creation").split()
    )
    assert "`--base origin/<branch>`" in ado
