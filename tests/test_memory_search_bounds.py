"""Candidate cap and recall deadline in the memory search (issue #7493, ADR-109 2026-11-20).

``time.monotonic`` is replaced by a fake clock, so no test waits on real time.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from memory_enhancement import search
from memory_enhancement.hooks import user_prompt_submit_memory as hook
from memory_enhancement.models import VerificationResult


class Clock:
    """A settable replacement for ``time.monotonic``."""

    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Clock:
    fake = Clock()
    monkeypatch.setattr(search.time, "monotonic", fake)
    return fake


def _memories(tmp_path: Path, names: list[str]) -> Path:
    directory = tmp_path / ".serena" / "memories"
    directory.mkdir(parents=True)
    for name in names:
        (directory / f"{name}.md").write_text(
            f"# {name}\n\nMove every service behind the gateway.\n", encoding="utf-8"
        )
    return directory


def _count_loads(monkeypatch: pytest.MonkeyPatch, on_load=None) -> list[Path]:
    loaded: list[Path] = []
    real = search.load_memory

    def counting(file_path: Path, memories_dir: Path | None = None):
        loaded.append(file_path)
        if on_load is not None:
            on_load()
        return real(file_path, memories_dir)

    monkeypatch.setattr(search, "load_memory", counting)
    return loaded


# --- candidate cap -------------------------------------------------------------


def test_the_cap_is_fifty() -> None:
    assert search.MAX_CANDIDATES == 50


def test_sixty_matching_files_load_at_most_fifty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = _memories(tmp_path, [f"note-{i:02d}" for i in range(60)])
    loaded = _count_loads(monkeypatch)

    search.search_memories("gateway", directory, repo_root=tmp_path)

    assert len(loaded) == 50
    assert len(set(loaded)) == 50


def test_the_cut_is_deterministic_path_order_when_relevance_ties(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = _memories(tmp_path, [f"note-{i:02d}" for i in range(60)])
    loaded = _count_loads(monkeypatch)

    search.search_memories("gateway", directory, repo_root=tmp_path)

    expected = sorted(directory.glob("*.md"))[:50]
    assert sorted(path.resolve() for path in loaded) == [p.resolve() for p in expected]


def test_a_better_stem_match_survives_the_cut_even_when_it_sorts_last(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = _memories(tmp_path, [f"note-{i:02d}" for i in range(60)] + ["zzz-gateway"])
    loaded = _count_loads(monkeypatch)

    results = search.search_memories("gateway", directory, repo_root=tmp_path, max_results=1)

    assert len(loaded) == 50
    assert results[0].memory_id == "zzz-gateway"


def test_a_smaller_cap_is_respected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    directory = _memories(tmp_path, [f"note-{i:02d}" for i in range(10)])
    loaded = _count_loads(monkeypatch)

    search.rank_results(sorted(directory.glob("*.md")), tmp_path, max_candidates=4)

    assert len(loaded) == 4


def test_fewer_files_than_the_cap_all_load(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    directory = _memories(tmp_path, [f"note-{i:02d}" for i in range(7)])
    loaded = _count_loads(monkeypatch)

    search.search_memories("gateway", directory, repo_root=tmp_path)

    assert len(loaded) == 7


# --- deadline -------------------------------------------------------------------


def test_no_new_file_loads_once_the_deadline_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, clock: Clock
) -> None:
    directory = _memories(tmp_path, [f"note-{i:02d}" for i in range(20)])
    loaded = _count_loads(monkeypatch, on_load=lambda: clock.advance(3.0))

    results = search.search_memories(
        "gateway", directory, repo_root=tmp_path, deadline=clock.now + 8.0
    )

    assert len(loaded) == 3
    assert isinstance(results, list)
    assert len(results) == 3


def test_control_without_a_deadline_all_candidates_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, clock: Clock
) -> None:
    directory = _memories(tmp_path, [f"note-{i:02d}" for i in range(20)])
    loaded = _count_loads(monkeypatch, on_load=lambda: clock.advance(3.0))

    search.search_memories("gateway", directory, repo_root=tmp_path)

    assert len(loaded) == 20


def test_a_spent_deadline_returns_nothing_without_raising(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, clock: Clock
) -> None:
    directory = _memories(tmp_path, ["note-00"])
    loaded = _count_loads(monkeypatch)

    results = search.search_memories(
        "gateway", directory, repo_root=tmp_path, deadline=clock.now - 1.0
    )

    assert results == []
    assert loaded == []


def test_recall_block_gives_the_search_an_eight_second_deadline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, clock: Clock
) -> None:
    (tmp_path / ".git").mkdir()
    _memories(tmp_path, ["gateway-cutover"])
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    monkeypatch.setattr(hook.time, "monotonic", clock)
    seen: list[float | None] = []
    real = search.search_memories

    def spy(*args, **kwargs):
        seen.append(kwargs.get("deadline"))
        return real(*args, **kwargs)

    monkeypatch.setattr(search, "search_memories", spy)

    out = hook.recall_block("gateway cutover")

    assert hook.RECALL_DEADLINE_SECONDS == 8.0
    assert seen == [clock.now + 8.0]
    assert "<memory-context>" in out


def test_recall_block_never_raises_when_the_search_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / ".git").mkdir()
    _memories(tmp_path, ["gateway-cutover"])
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))

    def boom(*_a, **_k):
        raise RuntimeError("search exploded")

    monkeypatch.setattr(search, "search_memories", boom)

    assert hook.recall_block("gateway cutover") == ""
    assert "memory recall failed" in capsys.readouterr().err


# --- subprocess timeouts fit the remaining budget -------------------------------


def _fake_run(monkeypatch: pytest.MonkeyPatch, outcomes: list) -> list[float]:
    """Replace subprocess.run; record each timeout. *outcomes* items are results or exceptions."""
    timeouts: list[float] = []

    def run(cmd, **kwargs):
        timeouts.append(kwargs["timeout"])
        outcome = outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        if callable(outcome):
            outcome()
        return MagicMock(returncode=1, stdout="")

    monkeypatch.setattr(search.subprocess, "run", run)
    monkeypatch.setattr(search.shutil, "which", lambda name: f"/usr/bin/{name}")
    return timeouts


def test_ripgrep_timeout_is_the_remaining_budget_when_it_is_under_five_seconds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, clock: Clock
) -> None:
    timeouts = _fake_run(monkeypatch, [None])

    search._search_with_ripgrep("gateway", tmp_path, deadline=clock.now + 2.0)

    assert timeouts == [2.0]


def test_ripgrep_timeout_stays_five_seconds_when_more_budget_remains(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, clock: Clock
) -> None:
    timeouts = _fake_run(monkeypatch, [None])

    search._search_with_ripgrep("gateway", tmp_path, deadline=clock.now + 8.0)
    assert timeouts == [5]


def test_the_grep_fallback_gets_only_what_ripgrep_left(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, clock: Clock
) -> None:
    memories = _memories(tmp_path, ["gateway-cutover"])
    timeouts = _fake_run(
        monkeypatch,
        [
            lambda: (clock.advance(5.0), (_ for _ in ()).throw(subprocess.TimeoutExpired("rg", 5)))[
                1
            ],
            None,
        ],
    )

    search.search_memories("gateway", memories, repo_root=tmp_path, deadline=clock.now + 8.0)

    assert timeouts == [5, 3.0]
    assert sum(timeouts) <= 8.0


def test_no_subprocess_starts_when_the_budget_is_spent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, clock: Clock
) -> None:
    timeouts = _fake_run(monkeypatch, [None, None])
    memories = _memories(tmp_path, ["gateway-cutover"])

    results = search.search_memories(
        "gateway", memories, repo_root=tmp_path, deadline=clock.now - 0.1
    )

    assert results == []
    assert timeouts == []


# --- citation verification honors the deadline ----------------------------------


def _memory_with_citations(tmp_path: Path, count: int) -> Path:
    directory = tmp_path / ".serena" / "memories"
    directory.mkdir(parents=True)
    lines = "\n".join(f"[cite:file](src/f{i}.py)" for i in range(count))
    path = directory / "gateway-cutover.md"
    path.write_text(f"# Gateway cutover\n\nBody.\n\n{lines}\n", encoding="utf-8")
    return path


def _ok(citation) -> VerificationResult:
    return VerificationResult(citation=citation, is_valid=True, reason="ok")


def test_citations_are_verified_while_time_remains(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, clock: Clock
) -> None:
    path = _memory_with_citations(tmp_path, 3)
    monkeypatch.setattr(search, "verify_citation", lambda c, root: _ok(c))

    (result,) = search.rank_results([path], tmp_path, deadline=clock.now + 8.0)

    assert result.citation_status == "verified"


def test_verification_is_skipped_and_unverified_once_the_deadline_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, clock: Clock
) -> None:
    path = _memory_with_citations(tmp_path, 3)
    calls: list[object] = []

    def slow_verify(citation, root):
        calls.append(citation)
        clock.advance(5.0)
        return _ok(citation)

    monkeypatch.setattr(search, "verify_citation", slow_verify)

    (result,) = search.rank_results([path], tmp_path, deadline=clock.now + 8.0)

    assert len(calls) == 2
    assert result.citation_status == "unverified"


def test_a_spent_deadline_before_verification_makes_no_verify_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, clock: Clock
) -> None:
    path = _memory_with_citations(tmp_path, 2)
    verify = MagicMock()
    monkeypatch.setattr(search, "verify_citation", verify)
    real_load = search.load_memory

    def load_then_expire(file_path, memories_dir=None):
        memory = real_load(file_path, memories_dir)
        clock.advance(100.0)
        return memory

    monkeypatch.setattr(search, "load_memory", load_then_expire)

    (result,) = search.rank_results([path], tmp_path, deadline=clock.now + 8.0)

    verify.assert_not_called()
    assert result.citation_status == "unverified"
