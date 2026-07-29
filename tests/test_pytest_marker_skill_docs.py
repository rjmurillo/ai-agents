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


def _pytest_marker_names() -> list[str]:
    parsed = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    markers = parsed["tool"]["pytest"]["ini_options"]["markers"]
    return [marker.split(":", 1)[0] for marker in markers]


def _line_range(start_predicate: str) -> str:
    lines = PYPROJECT.read_text(encoding="utf-8").splitlines()
    start = next(
        number for number, line in enumerate(lines, start=1) if line == start_predicate
    )
    end = next(
        number
        for number, line in enumerate(lines[start - 1 :], start=start)
        if line == "]"
    )
    return f"pyproject.toml:{start}-{end}"


def _section_range(header: str, closing_line: str) -> str:
    lines = PYPROJECT.read_text(encoding="utf-8").splitlines()
    start = next(number for number, line in enumerate(lines, start=1) if line == header)
    end = next(
        number
        for number, line in enumerate(lines[start - 1 :], start=start)
        if line == closing_line
    )
    return f"pyproject.toml:{start}-{end}"


def test_skill_docs_enumerate_every_pytest_marker() -> None:
    """Skill docs must not omit configured pytest markers."""
    expected = _pytest_marker_names()

    for path in MARKER_DOCS:
        text = path.read_text(encoding="utf-8")
        for marker in expected:
            assert f"`{marker}`" in text, f"{path} omits {marker!r}"


def test_skill_docs_cite_the_marker_list_lines() -> None:
    """Marker guidance must point readers at the marker array, not uv settings."""
    marker_range = _line_range("markers = [")

    for path in MARKER_DOCS:
        text = path.read_text(encoding="utf-8")
        assert marker_range in text
        assert "pyproject.toml:46-51" not in text


def test_validation_skill_provenance_cites_pytest_section() -> None:
    """Validation provenance must include the pytest section, not build metadata."""
    pytest_section = _section_range("[tool.pytest.ini_options]", "]")

    for path in VALIDATION_DOCS:
        text = path.read_text(encoding="utf-8")
        assert pytest_section in text
        assert "pyproject.toml:40-55" not in text


def test_safe_push_transport_marker_has_behavioral_gloss() -> None:
    """The non-local transport marker needs enough context to prevent misuse."""
    pattern = re.compile(
        r"safe_push_transport.*non-local transport.*excluded from pre-push",
        re.IGNORECASE,
    )

    for path in MARKER_DOCS:
        text = path.read_text(encoding="utf-8")
        assert pattern.search(text), f"{path} lacks the safe_push_transport gloss"
