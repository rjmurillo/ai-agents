"""Test fixtures for `.claude/review-axes/` and `.claude/lib/` validation.

Implements REQ-008-01 acceptance criterion: schema-validation fixture asserts
exact section-title strings (literal level-2 headings) and required frontmatter
keys for each canonical axis file.

Spec: .agents/specs/requirements/REQ-008-review-axes-convergence.md
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pytest

# Frontmatter keys required by REQ-008-01 acceptance criterion 2.
REQUIRED_FRONTMATTER_KEYS: frozenset[str] = frozenset(
    {"name", "role", "version", "description"}
)

# Body sections required by REQ-008-01 acceptance criterion 6 (literal match,
# not substring; level-2 headings).
REQUIRED_SECTION_HEADINGS: tuple[str, ...] = (
    "## Grounding Rules",
    "## Analysis Focus Areas",
    "## Output Schema",
)

# Output Schema field names required by REQ-008-01 acceptance criterion 4.
REQUIRED_SCHEMA_FIELDS: tuple[str, ...] = (
    "severity",
    "category",
    "location",
    "recommendation",
    "verdict",
)


def _split_frontmatter(text: str) -> tuple[str, str]:
    """Split a markdown file into (frontmatter, body).

    Returns ("", text) if no frontmatter is present. Frontmatter is delimited
    by `---` on the first and a subsequent line per the YAML frontmatter
    convention.
    """
    if not text.startswith("---\n"):
        return "", text
    end_idx = text.find("\n---\n", 4)
    if end_idx == -1:
        return "", text
    frontmatter = text[4:end_idx]
    body = text[end_idx + 5 :]
    return frontmatter, body


def _parse_frontmatter_keys(frontmatter: str) -> set[str]:
    """Parse top-level YAML keys.

    Uses pyyaml when available; falls back to simple `key:` line scanning when
    not. The fallback is sufficient because REQ-008-01 only requires presence
    of the four scalar keys (`name`, `role`, `version`, `description`); none
    are nested.
    """
    try:
        import yaml  # type: ignore[import-not-found]

        loaded = yaml.safe_load(frontmatter) or {}
        if not isinstance(loaded, dict):
            return set()
        return {str(k) for k in loaded.keys()}
    except ImportError:
        # Fallback: scan for `key:` at start of line, no leading whitespace.
        keys: set[str] = set()
        for line in frontmatter.splitlines():
            if not line or line.startswith((" ", "\t", "#", "-")):
                continue
            colon_idx = line.find(":")
            if colon_idx <= 0:
                continue
            keys.add(line[:colon_idx].strip())
        return keys


def _find_level_2_headings(body: str) -> list[str]:
    """Return all level-2 headings in body order.

    A heading is a line that begins with exactly `## ` (two hashes + space).
    Lines inside fenced code blocks are skipped.
    """
    headings: list[str] = []
    in_fence = False
    for line in body.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if line.startswith("## ") and not line.startswith("### "):
            headings.append(line.rstrip())
    return headings


def validate_axis_schema(path: Path) -> None:
    """Validate a `.claude/review-axes/{role}.md` canonical file against REQ-008-01.

    Raises:
        AssertionError: when frontmatter keys are missing, required level-2
            headings are absent, or `Output Schema` does not mention all
            required field names.
        FileNotFoundError: when path does not exist.
    """
    if not path.exists():
        raise FileNotFoundError(f"axis file not found: {path}")

    text = path.read_text(encoding="utf-8")
    frontmatter, body = _split_frontmatter(text)

    assert frontmatter, (
        f"{path.name}: missing YAML frontmatter (expected --- delimited block at top)"
    )

    keys = _parse_frontmatter_keys(frontmatter)
    missing_keys = REQUIRED_FRONTMATTER_KEYS - keys
    assert not missing_keys, (
        f"{path.name}: frontmatter missing required keys: {sorted(missing_keys)}"
    )

    headings = _find_level_2_headings(body)
    for required in REQUIRED_SECTION_HEADINGS:
        assert required in headings, (
            f"{path.name}: missing required level-2 heading {required!r}; "
            f"found: {headings}"
        )

    # Output Schema field presence: scan only the Output Schema section to
    # avoid matching the literal field names in other sections.
    schema_section = _extract_section(body, "## Output Schema")
    missing_fields = [
        field for field in REQUIRED_SCHEMA_FIELDS if field not in schema_section
    ]
    assert not missing_fields, (
        f"{path.name}: Output Schema section missing field names: {missing_fields}"
    )


def _extract_section(body: str, heading: str) -> str:
    """Return the body of the named level-2 section, up to the next `## ` heading."""
    lines = body.splitlines()
    out: list[str] = []
    in_section = False
    for line in lines:
        if line.rstrip() == heading:
            in_section = True
            continue
        if in_section and line.startswith("## ") and not line.startswith("### "):
            break
        if in_section:
            out.append(line)
    return "\n".join(out)


@pytest.fixture
def validate_axis_schema_fn():
    """Pytest fixture exposing `validate_axis_schema` to test modules."""
    return validate_axis_schema


__all__: Iterable[str] = (
    "REQUIRED_FRONTMATTER_KEYS",
    "REQUIRED_SECTION_HEADINGS",
    "REQUIRED_SCHEMA_FIELDS",
    "validate_axis_schema",
    "validate_axis_schema_fn",
)
