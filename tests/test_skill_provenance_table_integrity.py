"""Regression guard: escaped pipes in skill SKILL.md provenance tables.

Escaped pipes (``\\|``) are valid Markdown table syntax but reach a raw shell
reader intact. In a re-verify command column, the escape lets a second shell
statement hide the first statement's failure (the first statement exits non-zero
and the shell sees a literal ``|`` as a pipe character, silently continuing).

This test scans every ``## Provenance`` table in every ``.claude/skills/*/SKILL.md``
and reports any row that contains ``\\|``.

Scope: all skills under ``.claude/skills/``. The ``src/copilot-cli/`` mirrors
are identical; scanning one tree is sufficient.

Background: the defect first appeared in the docs-of-record skill and was
caught locally; this test broadens the guard repo-wide so the same class of
defect cannot recur in any skill.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_SKILLS_ROOT = Path(__file__).resolve().parents[1] / ".claude" / "skills"


def _provenance_rows(skill_md: Path) -> list[tuple[str, str]]:
    """Return (row_text, skill_name) tuples from the ## Provenance table."""
    rows: list[tuple[str, str]] = []
    skill_name = skill_md.parent.name
    in_table = False
    for line in skill_md.read_text(encoding="utf-8").splitlines():
        if line.startswith("## Provenance"):
            in_table = True
            continue
        if in_table:
            if line.startswith("#"):
                break
            if not line.startswith("|"):
                continue
            if line.startswith("|---"):
                continue
            rows.append((line, skill_name))
    return rows


def _all_provenance_rows() -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for skill_md in sorted(_SKILLS_ROOT.glob("*/SKILL.md")):
        rows.extend(_provenance_rows(skill_md))
    return rows


_PROVENANCE_ROWS = _all_provenance_rows()


class TestSkillProvenanceTableIntegrity:
    def test_provenance_tables_found(self):
        """At least one provenance table exists across all skills."""
        assert _PROVENANCE_ROWS, "no provenance rows found in any SKILL.md"

    @pytest.mark.parametrize(
        "row,skill_name",
        [
            pytest.param(row, skill, id=f"{skill}:{row[:40].strip()}")
            for row, skill in _PROVENANCE_ROWS
        ],
    )
    def test_no_escaped_pipe_in_provenance_row(self, row: str, skill_name: str):
        """An escaped pipe in a re-verify command can mask a failing shell statement.

        The escape character reaches a raw reader intact; a second shell
        command after the escaped pipe runs even when the first fails.
        """
        assert r"\|" not in row, (
            f"escaped pipe in {skill_name} provenance row: {row[:80]}"
        )
