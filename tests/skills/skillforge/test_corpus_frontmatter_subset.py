"""Every shipped SKILL.md frontmatter parses under skillforge's stdlib subset parser.

`_conformance_parse.py` reads frontmatter without PyYAML on purpose, so a
consumer's verdict does not depend on what is installed. It supports block
mappings, block sequences, plain and quoted scalars, block scalars, and flow
lists of plain scalars. A flow mapping or a mapping inside a sequence raises
UnsupportedError, and conformance then reports every MUST rule NOT_EVALUATED
and exits 1.

PyYAML-based gates accept those shapes, so nothing else in the repository
notices. ADR-123's first schema used flow collections and broke 16 of 110 skills
at `b8bedf583`; this test is the guard that keeps the defect class from returning.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPTS = _REPO_ROOT / "src" / "claude" / "skills" / "skillforge" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import _conformance_parse as subset_parser

_TREES = (
    "src/claude/skills",
    "src/copilot-cli/skills",
    "src/codex/skills",
    "src/cursor/skills",
    "src/muse/skills",
)


def _skill_dirs(tree: str) -> list[Path]:
    root = _REPO_ROOT / tree
    return sorted(p for p in root.iterdir() if (p / "SKILL.md").is_file())


@pytest.mark.parametrize("tree", _TREES)
def test_every_shipped_frontmatter_parses_under_the_subset(tree: str) -> None:
    skill_dirs = _skill_dirs(tree)

    failures = {
        directory.name: doc.unsupported or doc.parse_error or doc.frontmatter_error
        for directory in skill_dirs
        for doc in [subset_parser.load_skill(directory, _REPO_ROOT)]
        if doc.unsupported or doc.parse_error or doc.frontmatter_error
    }

    assert len(skill_dirs) > 100, f"examined only {len(skill_dirs)} skills under {tree}"
    assert failures == {}


@pytest.mark.parametrize(
    ("block", "reason"),
    [
        ("  inputs: [{artifact: x}]\n", "flow mapping"),
        ("  inputs:\n    - artifact: x\n", "mapping inside a sequence"),
        ("  capability: {kind: orchestrator}\n", "flow mapping"),
    ],
    ids=["flow-list-of-mappings", "block-list-of-mappings", "flow-mapping"],
)
def test_shapes_outside_the_subset_are_refused(tmp_path: Path, block: str, reason: str) -> None:
    skill = tmp_path / "demo"
    skill.mkdir()
    (skill / "SKILL.md").write_text(
        f"---\nname: demo\ndescription: Demo.\nmetadata:\n{block}---\n\nBody.\n",
        encoding="utf-8",
    )

    doc = subset_parser.load_skill(skill, tmp_path)

    assert doc.unsupported, f"{reason} should be outside the subset"


def test_artifact_keyed_shape_is_inside_the_subset(tmp_path: Path) -> None:
    skill = tmp_path / "demo"
    skill.mkdir()
    (skill / "SKILL.md").write_text(
        "---\nname: demo\ndescription: Demo.\nmetadata:\n"
        "  inputs:\n    requirements-spec:\n      required: false\n    change-request:\n"
        "  outputs:\n    execution-plan:\n      path: plans/active/\n"
        "---\n\nBody.\n",
        encoding="utf-8",
    )

    doc = subset_parser.load_skill(skill, tmp_path)

    assert doc.unsupported is None
    assert doc.fields is not None
    metadata = doc.fields["metadata"]
    assert isinstance(metadata, dict)
    assert set(metadata["inputs"]) == {"requirements-spec", "change-request"}
