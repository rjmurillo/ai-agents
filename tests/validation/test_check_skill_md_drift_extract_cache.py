"""Equivalence tests for the path-extraction cache and guards (issue #6734).

``_extract_paths_from_text`` is called twice for every marked file, and the
mirrored plugin trees repeat marker text, so its result is cached and each
regex is skipped when its literal prefix is absent. These tests pin that the
cache cannot leak state between callers and that the guards never change a
result.
"""

from __future__ import annotations

import random
import re
from collections.abc import Iterator
from types import SimpleNamespace

import pytest

from scripts.validation import check_skill_md_drift as drift


@pytest.fixture(autouse=True)
def _fresh_cache() -> Iterator[None]:
    drift._extract_path_sets.cache_clear()
    yield
    drift._extract_path_sets.cache_clear()


class TestCacheContract:
    def test_each_call_returns_a_fresh_set(self) -> None:
        text = "Read .agents/governance/a.md here.\n"
        first = drift._extract_paths_from_text(text)
        first.add("poison")

        second = drift._extract_paths_from_text(text)

        assert second == {".agents/governance/a.md"}

    def test_unsafe_paths_reach_the_collector_on_a_cache_hit(self) -> None:
        text = "See scripts/../../etc/passwd and /scripts/abs.py\n"
        for _ in range(3):
            unsafe: set[str] = set()
            drift._extract_paths_from_text(text, unsafe_collector=unsafe)
            assert unsafe, "a cache hit dropped the unsafe paths"

        assert drift._extract_path_sets.cache_info().hits == 2

    def test_collector_keeps_entries_the_caller_already_had(self) -> None:
        unsafe = {"already"}
        drift._extract_paths_from_text("x scripts/../a.py\n", unsafe_collector=unsafe)

        assert "already" in unsafe

    def test_no_collector_is_allowed(self) -> None:
        assert drift._extract_paths_from_text("scripts/a.py\n") == {"scripts/a.py"}

    def test_text_without_any_prefix_yields_nothing(self) -> None:
        unsafe: set[str] = set()

        assert drift._extract_paths_from_text("Nothing here.\n", unsafe_collector=unsafe) == set()
        assert unsafe == set()


class TestGuardsKeepCaseSensitivity:
    @pytest.mark.parametrize("text", [".Agents/x.md", "Build/x.py", "SCRIPTS/x.py"])
    def test_upper_case_prefix_is_not_extracted(self, text: str) -> None:
        """The extractor is case-sensitive; the guard must not loosen it."""
        assert drift._extract_paths_from_text(text + "\n") == set()

    def test_word_without_separator_is_not_extracted(self) -> None:
        text = "We build things and write scripts and use templates.\n"

        assert drift._extract_paths_from_text(text) == set()

    def test_single_and_multi_segment_prefixes_are_both_found(self) -> None:
        text = "Run scripts/a.py then read templates/agents/b.md and .claude/lib/c.py\n"

        assert drift._extract_paths_from_text(text) == {
            "scripts/a.py",
            "templates/agents/b.md",
            ".claude/lib/c.py",
        }


class _NoGuardRe:
    """``re`` with ``search`` always succeeding, so every regex runs unguarded."""

    def __getattr__(self, name: str) -> object:
        return getattr(re, name)

    @staticmethod
    def search(*_args: object, **_kwargs: object) -> re.Match[str]:
        match = re.match("", "")
        assert match is not None
        return match


def test_guards_never_change_the_result(monkeypatch: pytest.MonkeyPatch) -> None:
    """Seeded fuzz: the guarded extractor equals the same code with guards off."""
    fragments = [
        " ", "\n", "(", "[", '"', "`", "/", "\\", ".", "../", "x", "a.py", "dir/",
        ".agents/", ".agents", ".project-toolkit/sessions/", "build/", "build", "scripts/",
        "scripts", "templates/agents/", "templates/platforms", ".claude/lib/", ".claude/lib",
        ".claude/review-axes/", "Scripts/", ".Agents/", "buy/partner/defer", "<d>/scripts/y",
    ]  # fmt: skip
    rng = random.Random(6734)
    texts = ["".join(rng.choice(fragments) for _ in range(rng.randint(0, 16))) for _ in range(1500)]
    guarded = []
    for text in texts:
        unsafe: set[str] = set()
        guarded.append((drift._extract_paths_from_text(text, unsafe_collector=unsafe), unsafe))

    drift._extract_path_sets.cache_clear()
    monkeypatch.setattr(drift, "re", _NoGuardRe())
    monkeypatch.setattr(drift, "UPSTREAM_CORES", SimpleNamespace(search=lambda _t: True))
    for text, expected in zip(texts, guarded, strict=True):
        unsafe = set()
        assert (
            drift._extract_paths_from_text(text, unsafe_collector=unsafe),
            unsafe,
        ) == expected, repr(text)
