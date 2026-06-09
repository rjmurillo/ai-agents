"""Tests for .claude/rules/canonical-source-mirror.md applyTo coverage.

Pins REQ-012-03: the canonical-source-mirror rule's applyTo glob must cover
`.claude/review-axes/**` and `.github/prompts/**` in addition to the
original hooks/validation/build/skills scopes. Existing coverage of
`.claude/hooks/**` is preserved.

Test contract handles both YAML shapes the field can take:
    applyTo: "a/**,b/**"        # comma-separated string
    applyTo:                     # YAML list
      - "a/**"
      - "b/**"
"""

from __future__ import annotations

import fnmatch
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RULE_PATH = REPO_ROOT / ".claude" / "rules" / "canonical-source-mirror.md"


def _parse_frontmatter(text: str) -> dict:
    """Return the YAML frontmatter mapping at the head of `text`.

    Frontmatter is bounded by two `---` lines per the project convention
    in `.claude/rules/*.md`.
    """
    if not text.startswith("---"):
        raise AssertionError("rule file missing frontmatter fence")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise AssertionError("rule file missing closing frontmatter fence")
    return yaml.safe_load(parts[1]) or {}


def _coerce_patterns(apply_to: object) -> list[str]:
    """Return apply_to as a list of glob patterns regardless of source shape."""
    if isinstance(apply_to, str):
        return [pat.strip() for pat in apply_to.split(",") if pat.strip()]
    if isinstance(apply_to, list):
        return [str(pat).strip() for pat in apply_to if str(pat).strip()]
    raise AssertionError(f"applyTo must be str or list, got {type(apply_to).__name__}")


def _matches_any(path: str, patterns: list[str]) -> bool:
    """Return True if `path` matches any glob in `patterns` via fnmatch.

    fnmatch treats `**` as `*` semantically, which is acceptable here because
    the patterns are anchored at the top of a repo path. The `*` greedy match
    captures intermediate directory segments in the candidate paths used by
    this test (e.g. `.claude/review-axes/analyst.md`).
    """
    return any(fnmatch.fnmatch(path, pat) for pat in patterns)


@pytest.fixture(scope="module")
def apply_to_patterns() -> list[str]:
    text = RULE_PATH.read_text(encoding="utf-8")
    frontmatter = _parse_frontmatter(text)
    # Claude Code's conditional-load key is `paths`; the Copilot mirror's is
    # `applyTo`. The source rule declares `paths`; accept either so the
    # coverage assertions survive the applyTo->paths key migration.
    scope = frontmatter.get("paths", frontmatter.get("applyTo"))
    if scope is None:
        pytest.fail(
            "canonical-source-mirror.md frontmatter missing paths/applyTo"
        )
    return _coerce_patterns(scope)


def test_review_axes_path_matches(apply_to_patterns: list[str]) -> None:
    """REQ-012-03 AC: .claude/review-axes/analyst.md must match the glob."""
    assert _matches_any(".claude/review-axes/analyst.md", apply_to_patterns), (
        f"applyTo does not cover .claude/review-axes/; patterns={apply_to_patterns}"
    )


def test_github_prompts_path_matches(apply_to_patterns: list[str]) -> None:
    """REQ-012-03 AC: .github/prompts/pr-quality-gate-analyst.md must match."""
    assert _matches_any(
        ".github/prompts/pr-quality-gate-analyst.md", apply_to_patterns
    ), f"applyTo does not cover .github/prompts/; patterns={apply_to_patterns}"


def test_existing_hooks_coverage_preserved(apply_to_patterns: list[str]) -> None:
    """Regression: original .claude/hooks/** coverage must remain in place."""
    assert _matches_any(".claude/hooks/PreToolUse/example.py", apply_to_patterns), (
        f"applyTo no longer covers .claude/hooks/; patterns={apply_to_patterns}"
    )


def test_apply_to_field_present_and_typed(apply_to_patterns: list[str]) -> None:
    """The applyTo field must exist and parse to at least one pattern."""
    assert apply_to_patterns, "applyTo coerced to empty list"
    assert all(isinstance(pat, str) for pat in apply_to_patterns)


@pytest.mark.parametrize(
    "shape",
    [
        # Both YAML shapes the field may legitimately take.
        ('applyTo: "a/**,b/**"', ["a/**", "b/**"]),
        ("applyTo:\n  - 'a/**'\n  - 'b/**'", ["a/**", "b/**"]),
    ],
)
def test_coerce_handles_both_yaml_shapes(shape: tuple[str, list[str]]) -> None:
    """Coercer handles comma-separated string AND YAML list shapes."""
    yaml_text, expected = shape
    parsed = yaml.safe_load(yaml_text)
    assert _coerce_patterns(parsed["applyTo"]) == expected
