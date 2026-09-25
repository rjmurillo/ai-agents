"""Shared fixtures for the skill routing-role gate tests (REQ-038, DESIGN-036).

Every helper writes into `tmp_path`, never the working tree.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_VALIDATION = _REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION) not in sys.path:
    sys.path.insert(0, str(_VALIDATION))


def _routing(**fields: object) -> str:
    """Render one metadata.routing block as frontmatter lines."""
    lines = ["metadata:", "  routing:"]
    for key, value in fields.items():
        name = key.replace("_", "-")
        if isinstance(value, bool):
            lines.append(f"    {name}: {'true' if value else 'false'}")
        else:
            lines.append(f"    {name}: {value}")
    return "\n".join(lines)


def _skill(
    root: Path,
    name: str,
    block: str,
    body: str = "Body text.",
    *,
    user_invocable: bool | None = None,
) -> Path:
    path = root / "templates" / "skills" / f"{name}.SKILL.md.tmpl"
    path.parent.mkdir(parents=True, exist_ok=True)
    extra = "" if user_invocable is None else f"user-invocable: {str(user_invocable).lower()}\n"
    path.write_text(f"---\nname: {name}\n{extra}{block}\n---\n\n{body}\n", encoding="utf-8")
    return path


def _agent(root: Path, name: str, body: str = "Agent body.") -> Path:
    path = root / "templates" / "agents" / f"{name}.shared.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\nrole: support\n---\n\n{body}\n", encoding="utf-8")
    return path


def _reference(root: Path, skill_name: str, filename: str, body: str) -> Path:
    path = root / ".claude" / "skills" / skill_name / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _scenario_file(root: Path, rel: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}\n", encoding="utf-8")
    return path


@pytest.fixture(name="tree")
def tree_fixture(tmp_path: Path) -> Path:
    (tmp_path / "templates" / "skills").mkdir(parents=True)
    (tmp_path / "templates" / "agents").mkdir(parents=True)
    return tmp_path
