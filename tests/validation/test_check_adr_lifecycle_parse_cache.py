"""Parse-once equivalence tests for the ADR lifecycle gate (issue #6734).

`check_adr_lifecycle.scan` blanks each record body through a memoized helper so
the markdown-it parse runs once per distinct body instead of up to five
times. The gate's verdict must not move. Each test compares `scan` with the memo
against `scan` with the original uncached function swapped in.
"""

from __future__ import annotations

import sys
import textwrap
from datetime import date
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))

import adr_cited_paths
import check_adr_lifecycle

from scripts.utils import markdown_parser

_TODAY = date(2026, 9, 1)


@pytest.fixture(autouse=True)
def _fresh_memo():
    """Start and end each test with an empty memo so no test sees another's hits."""
    markdown_parser.blank_non_prose_block_lines_cached.cache_clear()
    yield
    markdown_parser.blank_non_prose_block_lines_cached.cache_clear()


_SECTIONS = "\n## Context\n\nWhy.\n\n## Decision\n\nWhat.\n\n## Consequences\n\nSo.\n"


def _adr_dir(tmp_path: Path) -> Path:
    path = tmp_path / ".project-toolkit" / "architecture"
    path.mkdir(parents=True)
    return path


def _write(adr_dir: Path, number: int, status: str, body: str, extra: str = "") -> None:
    front = textwrap.dedent(
        f"""\
        id: ADR-{number:03d}
        status: {status}
        date: 2026-08-21
        supersedes: []
        superseded-by: null
        implemented: true
        {extra}"""
    ).strip()
    (adr_dir / f"ADR-{number:03d}-thing.md").write_text(
        f"---\n{front}\n---\n\n# ADR-{number:03d}: Thing\n{body}",
        encoding="utf-8",
    )


def _corpus(tmp_path: Path) -> Path:
    """Records that exercise all five callers of the blanking helper."""
    adr_dir = _adr_dir(tmp_path)
    # Clean record with a restating status section, a missing cited path, and a
    # review-by date that the prose does not state.
    _write(
        adr_dir,
        1,
        "accepted",
        "\n## Status\n\nAccepted\n" + _SECTIONS.replace("What.", "Use `scripts/missing_file.py`."),
        "review-by: 2026-08-01",
    )
    # Fenced and commented `## Status` samples must stay invisible; the real one
    # says Proposed while the frontmatter says accepted, so prose drift fires.
    _write(
        adr_dir,
        2,
        "accepted",
        "\n```\n## Status\n\nAccepted\n```\n\n<!--\n## Status\nAccepted\n-->\n"
        "\n## Status\n\nProposed\n" + _SECTIONS,
    )
    # Same text as record 3's body below, different frontmatter status.
    shared = "\n## Status\n\nDeprecated, kept for the migration notes.\n" + _SECTIONS
    _write(adr_dir, 3, "accepted", shared)
    _write(adr_dir, 4, "deprecated", shared)
    # No required sections at all: section-structure fires.
    _write(adr_dir, 5, "accepted", "\nJust prose.\n")
    # Nested past maxNesting: every caller must report the parse refusal.
    quote = ">" * 20 + " "
    _write(
        adr_dir,
        6,
        "accepted",
        f"\n{quote}```\n{quote}## Status\n{quote}```\n\n## Status\n\nAccepted\n",
    )
    return adr_dir


def _scan(tmp_path: Path, adr_dir: Path) -> list[check_adr_lifecycle.Violation]:
    markdown_parser.blank_non_prose_block_lines_cached.cache_clear()
    return check_adr_lifecycle.scan(adr_dir, tmp_path, today=_TODAY)


def _scan_uncached(
    tmp_path: Path, adr_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> list[check_adr_lifecycle.Violation]:
    monkeypatch.setattr(
        check_adr_lifecycle,
        "blank_non_prose_block_lines_cached",
        markdown_parser.blank_non_prose_block_lines,
    )
    monkeypatch.setattr(
        adr_cited_paths,
        "blank_non_prose_block_lines_cached",
        markdown_parser.blank_non_prose_block_lines,
    )
    return check_adr_lifecycle.scan(adr_dir, tmp_path, today=_TODAY)


def test_scan_verdict_matches_the_uncached_scan(tmp_path, monkeypatch):
    adr_dir = _corpus(tmp_path)
    cached = _scan(tmp_path, adr_dir)
    with monkeypatch.context() as patch:
        uncached = _scan_uncached(tmp_path, adr_dir, patch)
    assert cached == uncached


def test_corpus_still_reports_every_planted_defect(tmp_path):
    # Guards the equivalence test above against passing on two empty lists.
    found = {(v.check, Path(v.path).name[:7]) for v in _scan(tmp_path, _corpus(tmp_path))}
    assert ("prose-frontmatter-agree", "ADR-001") in found  # restating section
    assert ("prose-frontmatter-agree", "ADR-002") in found  # real section drifts
    assert ("cited-paths-exist", "ADR-001") in found
    assert ("review-by-past-due", "ADR-001") in found
    assert ("section-structure", "ADR-005") in found
    assert ("prose-frontmatter-agree", "ADR-006") in found  # nesting refusal


def test_identical_bodies_with_different_frontmatter_keep_separate_verdicts(tmp_path):
    # The memo is keyed on the body only. Records 3 and 4 share a body and differ
    # in status, so a cache that also reused the verdict would give both the same
    # answer. Accepted vs "Deprecated, ..." prose drifts; deprecated vs the same
    # prose agrees and says more than a bare restatement, so it is clean.
    found = {(v.check, Path(v.path).name[:7]) for v in _scan(tmp_path, _corpus(tmp_path))}
    assert ("prose-frontmatter-agree", "ADR-003") in found
    assert ("prose-frontmatter-agree", "ADR-004") not in found


def test_each_body_is_parsed_exactly_once_per_scan(tmp_path, monkeypatch):
    adr_dir = _adr_dir(tmp_path)
    # Accepted, with a status section, cited paths, structure, and a review-by:
    # all five callers read this one body.
    body = "\n## Status\n\nAccepted\n" + _SECTIONS.replace("What.", "Use `scripts/x.py`.")
    _write(adr_dir, 1, "accepted", body, "review-by: 2026-12-01")
    calls: list[str] = []
    real = markdown_parser.blank_non_prose_block_lines

    def spy(markdown: str) -> str:
        calls.append(markdown)
        return real(markdown)

    monkeypatch.setattr(markdown_parser, "blank_non_prose_block_lines", spy)
    markdown_parser.blank_non_prose_block_lines_cached.cache_clear()
    check_adr_lifecycle.scan(adr_dir, tmp_path, today=_TODAY)
    assert len(calls) == 1


def test_a_refused_body_is_reported_for_every_check_that_reads_it(tmp_path):
    # Not cached on failure, so each of the five callers sees the refusal and
    # reports it rather than inheriting a clean result from an earlier call.
    adr_dir = _adr_dir(tmp_path)
    quote = ">" * 20 + " "
    _write(
        adr_dir,
        1,
        "accepted",
        f"\n{quote}```\n{quote}x\n{quote}```\n" + _SECTIONS,
        "review-by: 2026-12-01",
    )
    found = {v.check for v in _scan(tmp_path, adr_dir)}
    assert {
        "prose-frontmatter-agree",
        "section-structure",
        "cited-paths-exist",
        "review-by-prose-date",
    } <= found
