"""Regression coverage for pytest marker guidance in repository skills."""

from __future__ import annotations

import re
from pathlib import Path

import tomllib

REPO_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = REPO_ROOT / "pyproject.toml"
MARKER_DOCS = (
    REPO_ROOT / ".claude/skills/ai-agents-config-catalog/SKILL.md",
    REPO_ROOT / ".claude/skills/ai-agents-validation-and-qa/SKILL.md",
    REPO_ROOT / "src/copilot-cli/skills/ai-agents-config-catalog/SKILL.md",
    REPO_ROOT / "src/copilot-cli/skills/ai-agents-validation-and-qa/SKILL.md",
)
VALIDATION_DOCS = (
    REPO_ROOT / ".claude/skills/ai-agents-validation-and-qa/SKILL.md",
    REPO_ROOT / "src/copilot-cli/skills/ai-agents-validation-and-qa/SKILL.md",
)
SKILL_DOC_ROOTS = (
    REPO_ROOT / ".claude/skills",
    REPO_ROOT / "src/copilot-cli/skills",
)
PYTEST_MARKER_ANCHOR = "pyproject.toml [tool.pytest.ini_options].markers"
PYTEST_SECTION_ANCHOR = "pyproject.toml [tool.pytest.ini_options]"
PYPROJECT_LINE_CITATION = re.compile(r"pyproject\.toml:\d")


def _pytest_marker_names() -> list[str]:
    parsed = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    markers = parsed["tool"]["pytest"]["ini_options"]["markers"]
    return [marker.split(":", 1)[0] for marker in markers]


def _skill_docs() -> list[Path]:
    return sorted(path for root in SKILL_DOC_ROOTS for path in root.rglob("*.md"))


def test_skill_docs_enumerate_every_pytest_marker() -> None:
    """Skill docs must not omit configured pytest markers."""
    expected = _pytest_marker_names()

    for path in MARKER_DOCS:
        text = path.read_text(encoding="utf-8")
        for marker in expected:
            assert f"`{marker}`" in text, f"{path} omits {marker!r}"


def test_skill_docs_cite_the_marker_list_anchor() -> None:
    """Marker guidance must point readers at the marker array, not uv settings."""
    parsed = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    assert "markers" in parsed["tool"]["pytest"]["ini_options"]

    for path in MARKER_DOCS:
        text = path.read_text(encoding="utf-8")
        assert PYTEST_MARKER_ANCHOR in text


def test_validation_skill_provenance_cites_pytest_section_anchor() -> None:
    """Validation provenance must include the pytest section, not build metadata."""
    parsed = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    assert "ini_options" in parsed["tool"]["pytest"]

    for path in VALIDATION_DOCS:
        text = path.read_text(encoding="utf-8")
        assert PYTEST_SECTION_ANCHOR in text


def test_skill_docs_do_not_cite_pyproject_by_absolute_line_number() -> None:
    """pyproject guidance must use stable TOML keys, not line offsets."""
    offenders: list[str] = []

    for path in _skill_docs():
        text = path.read_text(encoding="utf-8")
        if PYPROJECT_LINE_CITATION.search(text):
            offenders.append(str(path.relative_to(REPO_ROOT)))

    assert offenders == []


def test_safe_push_transport_marker_has_behavioral_gloss() -> None:
    """The non-local transport marker needs enough context to prevent misuse."""
    pattern = re.compile(
        r"safe_push_transport.*non-local transport.*excluded from pre-push",
        re.IGNORECASE,
    )

    for path in MARKER_DOCS:
        text = path.read_text(encoding="utf-8")
        assert pattern.search(text), f"{path} lacks the safe_push_transport gloss"
