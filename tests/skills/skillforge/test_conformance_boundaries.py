"""conformance.py reads nothing outside the root it is given (PR #7376 review).

Each test points a symlink inside the skill at a file outside the root, then
checks the rule reports it and never reads the outside content.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from tests.skills.skillforge.conformance_support import DESCRIPTION, conformance, make_skill

SECRET = "outside-secret-value"

pytestmark = pytest.mark.skipif(not hasattr(os, "symlink"), reason="needs symlinks")


def _results(skill: Path, root: Path) -> dict[str, Any]:
    found, notes = conformance.evaluate(skill, "spec", set(), root)
    return {"notes": notes, **{r.rule.id: r for r in found}}


def _outside(tmp_path: Path, name: str, text: str) -> Path:
    target = tmp_path / "outside" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return target


def _link(path: Path, target: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"cannot create a symlink here: {exc}")


def test_skill_md_outside_the_root_is_not_read(tmp_path: Path) -> None:
    root = tmp_path / "root"
    skill = root / "release-notes"
    skill.mkdir(parents=True)
    secret = _outside(tmp_path, "SKILL.md", f"---\nname: {SECRET}\ndescription: x\n---\n")
    _link(skill / "SKILL.md", secret)

    found = _results(skill, root)

    assert "outside the root" in " ".join(found["spec.frontmatter.delimited"].problems)
    assert SECRET not in repr(found)


def test_script_outside_the_root_is_skipped_with_a_note(tmp_path: Path) -> None:
    root = tmp_path / "root"
    skill = make_skill(root, body="Run `run.py`.\n")
    secret = _outside(tmp_path, "run.py", f'"{SECRET}"\nif __name__ == "__main__":\n    input()\n')
    _link(skill / "scripts" / "run.py", secret)

    found = _results(skill, root)

    assert found["scripts.no-interactive-prompts"].status == "NOT_APPLICABLE"
    assert any("run.py" in note and "outside the root" in note for note in found["notes"])


def test_evals_file_outside_the_root_is_not_read(tmp_path: Path) -> None:
    root = tmp_path / "root"
    skill = make_skill(root)
    secret = _outside(tmp_path, "evals.json", f'{{"skill_name": "{SECRET}", "evals": []}}')
    _link(skill / "evals" / "evals.json", secret)

    found = _results(skill, root)

    assert found["evals.file-shape"].status == "NOT_EVALUATED"
    assert SECRET not in repr(found)


def test_eval_input_that_leaves_the_skill_is_reported(tmp_path: Path) -> None:
    root = tmp_path / "root"
    _outside(tmp_path, "private.txt", SECRET)
    evals = (
        '{"skill_name": "release-notes", "evals": [{"id": 1, "prompt": "p",'
        ' "expected_output": "o", "files": ["../private.txt"]}]}'
    )
    skill = make_skill(root, files={"evals/evals.json": evals})

    problems = " ".join(_results(skill, root)["evals.file-shape"].problems)

    assert "leaves the skill directory" in problems


def test_linked_reference_outside_the_root_is_reported_not_read(tmp_path: Path) -> None:
    root = tmp_path / "root"
    skill = make_skill(root, body="See [guide](references/guide.md).\n")
    secret = _outside(tmp_path, "guide.md", f"[{SECRET}](other.md)\n")
    _link(skill / "references" / "guide.md", secret)

    found = _results(skill, root)

    assert "outside the root" in " ".join(found["spec.references.resolve"].problems)
    assert found["spec.references.one-level"].status == "PASS"
    assert SECRET not in repr(found)


def test_default_root_is_the_skill_directory(tmp_path: Path) -> None:
    skill = make_skill(tmp_path / "root", body="See [guide](references/guide.md).\n")
    secret = _outside(tmp_path, "guide.md", "# Guide\n")
    _link(skill / "references" / "guide.md", secret)

    found, _notes = conformance.evaluate(skill, "spec", set())
    problems = " ".join(next(r for r in found if r.rule.id == "spec.references.resolve").problems)

    assert "outside the root" in problems
    assert DESCRIPTION
