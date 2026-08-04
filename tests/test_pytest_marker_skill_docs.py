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


def test_skill_docs_enumerate_every_pytest_marker() -> None:
    """Skill docs must not omit configured pytest markers."""
    expected = _pytest_marker_names()

    for path in MARKER_DOCS:
        text = path.read_text(encoding="utf-8")
        for marker in expected:
            assert f"`{marker}`" in text, f"{path} omits {marker!r}"


def test_skill_docs_cite_the_marker_list_lines() -> None:
    """Marker guidance must point readers at the marker array by section anchor.

    Citing by line number is fragile: any insertion above the marker section
    shifts the numbers and fails the gate for unrelated changes. The section
    anchor ``pyproject.toml [tool.pytest.ini_options] markers`` is stable
    across insertions.
    """
    anchor = "pyproject.toml `[tool.pytest.ini_options]` markers"

    for path in MARKER_DOCS:
        text = path.read_text(encoding="utf-8")
        assert anchor in text, (
            f"{path} must cite '{anchor}' instead of a fragile line number"
        )
        # Guard: the old fragile line-number form must not reappear.
        stale_pattern = re.compile(r"pyproject\.toml:\d+-\d+")
        stale = stale_pattern.search(text)
        assert stale is None, (
            f"{path} still contains a fragile line-range citation: {stale.group()!r}"
        )


def test_validation_skill_provenance_cites_pytest_section() -> None:
    """Validation provenance must include the pytest section by section anchor.

    Citing by line number is fragile: any insertion above the pytest section
    shifts the numbers and fails the gate for unrelated changes. The section
    anchor ``pyproject.toml [tool.pytest.ini_options]`` is stable.
    """
    anchor = "pyproject.toml `[tool.pytest.ini_options]`"

    for path in VALIDATION_DOCS:
        text = path.read_text(encoding="utf-8")
        assert anchor in text, (
            f"{path} must cite '{anchor}' instead of a fragile line number"
        )
        # Guard: the old fragile form must not reappear.
        stale_pattern = re.compile(r"pyproject\.toml:\d+-\d+")
        stale = stale_pattern.search(text)
        assert stale is None, (
            f"{path} still contains a fragile line-range citation: {stale.group()!r}"
        )


def test_safe_push_transport_marker_has_behavioral_gloss() -> None:
    """The non-local transport marker needs enough context to prevent misuse."""
    pattern = re.compile(
        r"safe_push_transport.*non-local transport.*excluded from pre-push",
        re.IGNORECASE,
    )

    for path in MARKER_DOCS:
        text = path.read_text(encoding="utf-8")
        assert pattern.search(text), f"{path} lacks the safe_push_transport gloss"
