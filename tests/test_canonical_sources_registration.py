"""Regression tests for code-quality and code-review-norms canonical sources.

Issue #1863 registered two harness-neutral canonical sources:

- ``.agents/governance/code-quality.md``
- ``.agents/governance/code-review-norms.md``

Both are listed in the ``.gemini/styleguide.md`` Canonical Sources table and
referenced from ``.github/PULL_REQUEST_TEMPLATE.md``. These tests pin that
contract so a future edit cannot silently drop a canonical file, point the
routing table at a path that does not exist, or move the canonical files under a
harness-scoped tree (``.claude/``, ``.github/instructions/``).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

CODE_QUALITY = REPO_ROOT / ".agents/governance/code-quality.md"
CODE_REVIEW_NORMS = REPO_ROOT / ".agents/governance/code-review-norms.md"
STYLEGUIDE = REPO_ROOT / ".gemini/styleguide.md"
PR_TEMPLATE = REPO_ROOT / ".github/PULL_REQUEST_TEMPLATE.md"

# Relative-from-.gemini paths exactly as they appear in the styleguide table.
STYLEGUIDE_ROWS = (
    ("Code quality", "../.agents/governance/code-quality.md"),
    ("Code review norms", "../.agents/governance/code-review-norms.md"),
)

# Repo-root-relative paths exactly as they appear in PR template links.
PR_TEMPLATE_REFS = (
    ".agents/governance/code-quality.md",
    ".agents/governance/code-review-norms.md",
)

# Harness-scoped prefixes that disqualify a canonical source per the issue
# Acceptance: each row "points to a file that is harness-neutral".
HARNESS_SCOPED_PREFIXES = (".claude/", ".github/instructions/")


def test_code_quality_canonical_file_exists() -> None:
    """The harness-neutral code-quality canonical source exists and is non-empty."""
    assert CODE_QUALITY.exists(), f"Missing canonical source at {CODE_QUALITY}"
    assert CODE_QUALITY.read_text(encoding="utf-8").strip(), "code-quality.md is empty"


def test_code_review_norms_canonical_file_exists() -> None:
    """The harness-neutral code-review-norms canonical source exists and is non-empty."""
    assert CODE_REVIEW_NORMS.exists(), f"Missing canonical source at {CODE_REVIEW_NORMS}"
    assert CODE_REVIEW_NORMS.read_text(encoding="utf-8").strip(), (
        "code-review-norms.md is empty"
    )


@pytest.mark.parametrize("path", (CODE_QUALITY, CODE_REVIEW_NORMS))
def test_canonical_sources_are_harness_neutral(path: Path) -> None:
    """Canonical files live outside harness-scoped trees.

    A canonical source under ``.claude/`` or ``.github/instructions/`` is only
    loaded by one harness and reintroduces the drift the issue closed.
    """
    rel = path.relative_to(REPO_ROOT).as_posix()
    for bad in HARNESS_SCOPED_PREFIXES:
        assert not rel.startswith(bad), (
            f"{rel} is harness-scoped ({bad}). Canonical sources must be neutral."
        )


@pytest.mark.parametrize(("topic", "rel_path"), STYLEGUIDE_ROWS)
def test_styleguide_table_row_points_to_existing_file(topic: str, rel_path: str) -> None:
    """Each new Canonical Sources row exists in the table and resolves to a real file."""
    styleguide_text = STYLEGUIDE.read_text(encoding="utf-8")
    assert f"]({rel_path})" in styleguide_text, (
        f"styleguide.md has no Canonical Sources row linking {rel_path} for '{topic}'."
    )
    # Resolve the relative-from-.gemini link to a real path on disk.
    resolved = (STYLEGUIDE.parent / rel_path).resolve()
    assert resolved.exists(), (
        f"styleguide.md row for '{topic}' points at {rel_path}, which does not resolve "
        f"to an existing file ({resolved})."
    )


def test_styleguide_rows_are_in_canonical_sources_table() -> None:
    """The new rows sit inside the Canonical Sources table, not elsewhere in the doc.

    Edge case: a link could appear in prose far from the table and still satisfy a
    naive substring check. Anchor the rows to the table region between the
    'Canonical Sources' heading and the next top-level section.
    """
    text = STYLEGUIDE.read_text(encoding="utf-8")
    start = text.find("## Canonical Sources")
    assert start != -1, "styleguide.md lost its '## Canonical Sources' heading."
    end = text.find("\n## ", start + 1)
    table_region = text[start:] if end == -1 else text[start:end]
    for topic, rel_path in STYLEGUIDE_ROWS:
        assert f"| {topic} |" in table_region, (
            f"Row '{topic}' is not inside the Canonical Sources table."
        )
        assert rel_path in table_region, (
            f"Link {rel_path} is not inside the Canonical Sources table."
        )


@pytest.mark.parametrize("ref", PR_TEMPLATE_REFS)
def test_pr_template_references_canonical_paths(ref: str) -> None:
    """The PR template links the canonical governance paths, not just the routing index."""
    template_text = PR_TEMPLATE.read_text(encoding="utf-8")
    assert ref in template_text, (
        f"PULL_REQUEST_TEMPLATE.md must reference {ref}. Acceptance requires the "
        "template to point at the canonical paths."
    )


def test_pr_template_norms_summary_defers_to_canonical() -> None:
    """The template's inlined norms summary names the canonical file as authoritative.

    The norms live in exactly one canonical file. The template keeps a render-safe
    summary, so it must explicitly defer authority to the canonical source to avoid
    becoming a second source of truth.
    """
    template_text = PR_TEMPLATE.read_text(encoding="utf-8")
    review_norms_link = ".agents/governance/code-review-norms.md"
    # The summary block must cite the canonical file as the source of truth.
    assert re.search(
        r"[Cc]anonical source:.*code-review-norms\.md", template_text
    ), (
        "The Review norms summary must name code-review-norms.md as the canonical "
        "source so the template is a mirror, not a competing authority."
    )
    assert review_norms_link in template_text


def test_canonical_files_cross_reference_each_other() -> None:
    """The two canonical files link to each other so a reader can navigate the pair."""
    quality_text = CODE_QUALITY.read_text(encoding="utf-8")
    norms_text = CODE_REVIEW_NORMS.read_text(encoding="utf-8")
    assert "code-review-norms.md" in quality_text, (
        "code-quality.md should reference code-review-norms.md."
    )
    assert "code-quality.md" in norms_text, (
        "code-review-norms.md should reference code-quality.md."
    )
