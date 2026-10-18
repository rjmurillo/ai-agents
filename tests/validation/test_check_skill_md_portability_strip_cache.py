"""Tests for the ``_strip_code`` cache in check_skill_md_portability (issue #5382).

One scanned file reaches ``_strip_code`` from ``has_portability_marker``,
``count_file_refs``, ``count_marker_suppressed_refs``, and the drift check. The
cache lets those calls share one CommonMark parse for an unmarked file and two
for a marked file. These tests pin three things: the parse count drops, the
results are the same as an uncached run, and a parser failure is neither
swallowed nor cached.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from scripts.utils.markdown_parser import MarkdownNestingError
from scripts.validation import check_skill_md_portability as cmp

_UNMARKED = "Run .agents/tool.py first.\n\n```bash\ncp scripts/validation/x.py .\n```\n"
_MARKED = (
    "<!-- vendor-portability: contributor guide, cites .agents/governance/a.md -->\n"
    "\n"
    "Read .agents/governance/a.md and .agents/missing/gone.md.\n"
)


@pytest.fixture(autouse=True)
def _fresh_cache() -> Iterator[None]:
    """Start and end each test with an empty cache so call counts are exact."""
    cache = cmp._strip_code
    cache.cache_clear()
    yield
    cache.cache_clear()


@pytest.fixture
def parse_calls(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record every text that reaches the CommonMark parser."""
    calls: list[str] = []
    real = cmp.blank_code_block_lines

    def counting(markdown: str) -> str:
        calls.append(markdown)
        return real(markdown)

    monkeypatch.setattr(cmp, "blank_code_block_lines", counting)
    return calls


def _per_file_pipeline(text: str, root: Path, rel: str) -> None:
    """The calls ``scan_all._process_file`` makes for one file."""
    cmp.count_file_refs(text)
    cmp.count_marker_suppressed_refs(text)
    if cmp.has_portability_marker(text):
        cmp.marker_path_drift(text, root, rel)


class TestParseCount:
    def test_same_text_is_parsed_once(self, parse_calls: list[str]) -> None:
        results = {cmp._strip_code(_UNMARKED) for _ in range(5)}

        assert len(results) == 1
        assert len(parse_calls) == 1

    def test_unmarked_file_is_parsed_once_across_the_whole_pipeline(
        self, parse_calls: list[str], tmp_path: Path
    ) -> None:
        _per_file_pipeline(_UNMARKED, tmp_path, "a.md")

        assert len(parse_calls) == 1

    def test_marked_file_is_parsed_at_most_twice(
        self, parse_calls: list[str], tmp_path: Path
    ) -> None:
        """Once for the file, once for the file with its marker removed."""
        _per_file_pipeline(_MARKED, tmp_path, "a.md")

        assert len(parse_calls) <= 2
        assert _MARKED in parse_calls

    def test_different_texts_do_not_share_an_entry(self, parse_calls: list[str]) -> None:
        first = cmp._strip_code("one .agents/a\n")
        second = cmp._strip_code("two .agents/b\n")

        assert first != second
        assert len(parse_calls) == 2

    def test_cache_is_bounded(self) -> None:
        assert cmp._strip_code.cache_info().maxsize == 128


class TestParserFailure:
    def test_failure_propagates_and_is_not_cached(self, monkeypatch: pytest.MonkeyPatch) -> None:
        attempts: list[int] = []
        real = cmp.blank_code_block_lines

        def failing(markdown: str) -> str:
            attempts.append(1)
            raise MarkdownNestingError("too deep")

        monkeypatch.setattr(cmp, "blank_code_block_lines", failing)
        for _ in range(2):
            with pytest.raises(MarkdownNestingError):
                cmp._strip_code("ok\n")
        assert len(attempts) == 2, "a failed parse was served from the cache"

        monkeypatch.setattr(cmp, "blank_code_block_lines", real)
        assert cmp._strip_code("ok\n") == "ok\n"

    def test_scan_still_refuses_an_unparseable_file(self, tmp_path: Path) -> None:
        skills = tmp_path / ".claude" / "skills" / "a"
        skills.mkdir(parents=True)
        (skills / "SKILL.md").write_text("> " * 40 + "x\n", encoding="utf-8")

        with pytest.raises(MarkdownNestingError):
            cmp.scan_all(tmp_path)


def _seed(root: Path) -> None:
    """A tree with unmarked offenders, a marked file with drift, and code-only refs."""
    skills = root / ".claude" / "skills"
    for index in range(5):
        path = skills / f"offender-{index}" / "SKILL.md"
        path.parent.mkdir(parents=True)
        path.write_text(f"Step {index}: write to .agents/out-{index}.md\n", encoding="utf-8")
    marked = skills / "marked" / "SKILL.md"
    marked.parent.mkdir(parents=True)
    marked.write_text(_MARKED, encoding="utf-8")
    code_only = skills / "code-only" / "SKILL.md"
    code_only.parent.mkdir(parents=True)
    code_only.write_text("```bash\ncp .agents/x .\n```\n\nClean prose.\n", encoding="utf-8")
    clean = skills / "clean" / "SKILL.md"
    clean.parent.mkdir(parents=True)
    clean.write_text("Nothing upstream here.\n", encoding="utf-8")


class TestEquivalence:
    def test_cached_scan_equals_uncached_scan(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _seed(tmp_path)

        cached = cmp.scan_all(tmp_path, check_drift=True)

        uncached_strip: Callable[[str], str] = cmp._strip_code.__wrapped__
        monkeypatch.setattr(cmp, "_strip_code", uncached_strip)
        uncached = cmp.scan_all(tmp_path, check_drift=True)

        assert cached == uncached

    def test_every_injected_violation_is_reported(self, tmp_path: Path) -> None:
        """Batching must not stop at the first offender."""
        _seed(tmp_path)

        ref_counts, marker_counts, _, drift = cmp.scan_all(tmp_path, check_drift=True)

        offenders = {f".claude/skills/offender-{i}/SKILL.md" for i in range(5)}
        assert offenders <= set(ref_counts)
        assert ".claude/skills/code-only/SKILL.md" not in ref_counts
        assert ".claude/skills/clean/SKILL.md" not in ref_counts
        assert ".claude/skills/marked/SKILL.md" in marker_counts
        assert any("gone.md" in failure for failure in drift)
