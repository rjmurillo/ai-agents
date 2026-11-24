"""Frontmatter edge cases for the adr-review change detector (PR #7531 review).

The shared fence match absorbs whitespace-only lines after the opening fence,
so the detector decodes from the end of the physical opening line. A tab-only
line there is malformed YAML and must refuse the frontmatter-only exemption,
as it did on the base. YAML merge keys loaded on the base through
``yaml.safe_load``, so status detection must still read them.
"""

from __future__ import annotations

import sys
from pathlib import Path

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
PROJECT_ROOT = str(Path(__file__).resolve().parents[3])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from claude_skills_import import import_skill_script

mod = import_skill_script(".claude/skills/adr-review/scripts/detect_adr_changes.py")


def test_a_tab_only_first_line_refuses_the_frontmatter_only_exemption() -> None:
    old = "---\n\t\nstatus: proposed\nimplemented: false\n---\n# Body\n"
    new = old.replace("implemented: false", "implemented: true")

    assert mod._parse_frontmatter(new) is None
    assert mod._only_non_decision_fields_changed(old, new) is False


def test_without_the_tab_line_the_same_edit_is_exempt() -> None:
    old = "---\nstatus: proposed\nimplemented: false\n---\n# Body\n"
    new = old.replace("implemented: false", "implemented: true")

    assert mod._only_non_decision_fields_changed(old, new) is True


def test_a_merge_key_keeps_status_detection(tmp_path: Path) -> None:
    adr = tmp_path / "ADR-001.md"
    adr.write_text(
        "---\nstatus: accepted\nbase: &b {owner: x}\nmeta:\n  <<: *b\n---\n# Title\n",
        encoding="utf-8",
    )

    assert mod._get_adr_status(adr) == "accepted"


def test_a_status_repeated_inside_an_inline_merge_is_refused() -> None:
    """`construct_mapping` flattens `<<` without the strict constructor (PR #7531 review)."""
    for merge in ("<<: {status: accepted, status: proposed}\n", "<<: [{status: a, status: b}]\n"):
        assert mod._parse_frontmatter(f"---\n{merge}---\n# Body\n") is None
    assert mod._parse_frontmatter("---\n<<: [{status: a}, {status: b}]\n---\n") == {"status": "a"}


def test_a_repeated_status_key_still_reads_unknown(tmp_path: Path) -> None:
    adr = tmp_path / "ADR-001.md"
    adr.write_text("---\nstatus: proposed\nstatus: accepted\n---\n# Title\n", encoding="utf-8")

    assert mod._get_adr_status(adr) == "unknown"
