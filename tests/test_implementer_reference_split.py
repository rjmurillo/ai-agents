"""Static guards for the implementer reference split.

The implementer body moved three blocks into ``build`` skill references: the
design and error handling detail, the code impact analysis template, and the
estimation detail. These tests pin, for every surface:

1. ``Reference Loading`` exists once, names every reference with a load
   condition, and carries the unresolved-path rule for a harness with no skill
   tree (VS Code).
2. Each stub keeps the rule that must hold without the reference, and names it.
3. Each reference exists and keeps the lines a trim would silently lose.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
REFERENCE_DIR = REPO_ROOT / "src" / "claude" / "skills" / "build" / "references"
LOADING_HEADING = "## Reference Loading"
PATH_FORM = "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/build/references/"
UNRESOLVED_RULE = "apply the rules in this file and state that the reference was unavailable"

IMPLEMENTER_PATHS = (
    Path("templates/agents/implementer.shared.md"),
    Path("src/claude/agents/implementer.md"),
    Path(".claude/agents/implementer.md"),
    Path(".github/agents/implementer.agent.md"),
    Path("src/copilot-cli/agents/implementer.agent.md"),
    Path("src/vs-code-agents/implementer.agent.md"),
    Path("src/cursor/agents/implementer.md"),
    Path("src/muse/agents/implementer.md"),
)

# reference -> (load condition phrase in Reference Loading, stub heading in the body)
REFERENCES = {
    "implementer-design-and-errors.md": (
        "design or refactor code",
        "## Software Hierarchy of Needs",
    ),
    "implementer-impact-analysis.md": (
        "requests impact analysis",
        "### Impact Analysis Deliverable",
    ),
    "implementer-estimation.md": ("estimate complexity", "## Complexity Estimation"),
}

# One or two lines per reference that a trim would silently lose.
LOAD_BEARING_LINES = {
    "implementer-design-and-errors.md": (
        "throw new MaxRetriesExceededException();",
        "| Business | Return result type | Insufficient funds, item unavailable |",
    ),
    "implementer-impact-analysis.md": (
        "## Breaking Changes",
        "**Deprecation Strategy**",
    ),
    "implementer-estimation.md": (
        "| Completely new territory | 3-4x | 6-8 days |",
        "**Will revisit**: [When you'll re-estimate]",
    ),
}


def _text(path: Path) -> str:
    return " ".join((REPO_ROOT / path).read_text(encoding="utf-8").split())


def _after(text: str, heading: str) -> str:
    """Return the flattened text from ``heading`` to the next Markdown heading."""
    start = text.index(heading) + len(heading)
    following = re.search(r" #{2,6} ", text[start:])
    return text[start : start + following.start()] if following else text[start:]


def _loading_section(path: Path) -> str:
    text = _text(path)
    assert text.count(LOADING_HEADING) == 1, f"{path} must carry {LOADING_HEADING!r} once"
    return _after(text, LOADING_HEADING)


@pytest.mark.parametrize("path", IMPLEMENTER_PATHS, ids=str)
def test_reference_loading_names_every_reference_with_a_condition(path: Path) -> None:
    section = _loading_section(path)

    assert PATH_FORM in section, f"{path} Reference Loading lacks the plugin-root path form"
    for name, (condition, _) in REFERENCES.items():
        assert name in section, f"{path} Reference Loading does not list {name}"
        assert condition in section, f"{path} has no load condition {condition!r} for {name}"


@pytest.mark.parametrize("path", IMPLEMENTER_PATHS, ids=str)
def test_harness_without_a_skill_tree_has_a_fallback_rule(path: Path) -> None:
    assert UNRESOLVED_RULE in _loading_section(path), f"{path} has no unresolved-path rule"


@pytest.mark.parametrize("name", sorted(REFERENCES))
def test_reference_exists_and_keeps_its_load_bearing_lines(name: str) -> None:
    ref = REFERENCE_DIR / name

    assert ref.is_file(), f"missing reference {ref}"
    text = ref.read_text(encoding="utf-8")
    for line in LOAD_BEARING_LINES[name]:
        assert line in text, f"{name} lost {line!r}"


@pytest.mark.parametrize("name", sorted(REFERENCES))
@pytest.mark.parametrize("path", IMPLEMENTER_PATHS, ids=str)
def test_stub_names_its_reference(path: Path, name: str) -> None:
    heading = REFERENCES[name][1]
    text = _text(path)

    assert heading in text, f"{path} lost {heading!r}"
    assert name in _after(text, heading), f"{path} stub under {heading!r} never names {name}"


@pytest.mark.parametrize("path", IMPLEMENTER_PATHS, ids=str)
def test_design_and_error_stub_keeps_the_rules_without_the_reference(path: Path) -> None:
    stub = _after(_text(path), "## Software Hierarchy of Needs")

    for token in (
        "never fail silently",
        "Retry only transient failures",
        "at most 3 retries",
        "Validation errors fail fast with no retry",
        "business errors return a result type",
    ):
        assert token in stub, f"{path} design stub lost {token!r}"


@pytest.mark.parametrize("path", IMPLEMENTER_PATHS, ids=str)
def test_estimation_stub_keeps_the_size_table_and_the_xl_blocker(path: Path) -> None:
    stub = _after(_text(path), "## Complexity Estimation")

    for token in (
        "XS (1-2 hours",
        "XL (16+",
        "Flag XL as a blocker.",
        "Request decomposition before proceeding.",
    ):
        assert token in stub, f"{path} estimation stub lost {token!r}"


@pytest.mark.parametrize("path", IMPLEMENTER_PATHS, ids=str)
def test_impact_stub_names_every_section_without_the_reference(path: Path) -> None:
    stub = _after(_text(path), "### Impact Analysis Deliverable")

    assert "If it is unavailable, write a document titled" in stub, path
    for section in (
        "Impacts Identified",
        "Testing Complexity",
        "Breaking Changes",
        "Issues Discovered",
        "Estimated Effort",
    ):
        assert section in stub, f"{path} impact stub lost {section}"


def test_every_rendered_implementer_copy_is_pinned() -> None:
    """Converse of the surface list: a new platform render cannot dodge these pins.

    Compare file names exactly: a case-insensitive glob on Windows would also match
    unrelated policy files.
    """
    names = {"implementer.md", "implementer.agent.md"}
    on_disk = {
        p.resolve()
        for pattern in ("*/agents/*.md", "*/*.agent.md", "*/*.md")
        for p in (REPO_ROOT / "src").glob(pattern)
        if p.name in names
    }
    listed = {(REPO_ROOT / p).resolve() for p in IMPLEMENTER_PATHS}
    unpinned = sorted(str(p.relative_to(REPO_ROOT)) for p in on_disk - listed)

    assert on_disk, "the converse found no implementer copies, so its glob is wrong"
    assert not unpinned, f"implementer copies missing from IMPLEMENTER_PATHS: {unpinned}"


def test_negative_control_unrelated_file_has_no_reference_loading() -> None:
    assert LOADING_HEADING not in (REPO_ROOT / "README.md").read_text(encoding="utf-8")
