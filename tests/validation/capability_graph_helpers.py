"""Shared fixtures for the capability graph gate tests.

`test_check_capability_graph.py` covers the six invariants and the report.
`test_check_capability_graph_partials.py` covers the copied-block check
against canonical partial text (issue #7641). Both build trees in `tmp_path`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_VALIDATION = _REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION) not in sys.path:
    sys.path.insert(0, str(_VALIDATION))

import check_capability_graph as gate

__all__ = ["_REPO_ROOT", "_block", "_projection", "_skill", "_tree", "gate", "tree"]


def _block(**fields: object) -> str:
    """Render one capability block as frontmatter lines."""
    lines = ["metadata:", "  capability:"]
    for key, value in fields.items():
        name = key.replace("_", "-")
        if isinstance(value, list):
            lines.append(f"  {' ' * 2}{name}:")
            lines.extend(f"      - {entry}" for entry in value)
        else:
            lines.append(f"    {name}: {value}")
    return "\n".join(lines)


def _tree(root: Path) -> None:
    """Create the three canonical directories the gate refuses to run without."""
    for subdir, pattern in gate.CANONICAL_GLOBS:
        (root / subdir).mkdir(parents=True, exist_ok=True)
        (root / subdir / pattern.replace("*", "placeholder")).write_text(
            "---\nname: placeholder\n---\n\nNo capability block.\n", encoding="utf-8"
        )


def _skill(root: Path, name: str, block: str, body: str = "Body text.") -> Path:
    path = root / "templates" / "skills" / f"{name}.SKILL.md.tmpl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\nname: {name}\n{block}\n---\n\n{body}\n", encoding="utf-8")
    return path


def _projection(root: Path, name: str, block: str) -> Path:
    path = root / ".claude" / "skills" / name / "SKILL.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\nname: {name}\n{block}\n---\n\nBody text.\n", encoding="utf-8")
    return path


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    _tree(tmp_path)
    return tmp_path
