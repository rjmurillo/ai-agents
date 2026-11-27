"""Review round 2 tests for linear time and bounded corpora: items 7, 8 and 10."""

from __future__ import annotations

import os
import sys
import time
from collections.abc import Callable
from pathlib import Path
from types import CodeType
from typing import Any

import adr_docs
import adr_locate
import adr_log
import adr_reason
import adr_scan
import pytest
from adr_helpers import commit, new_repo, write

# ---------------------------------------------------------------------------
# Item 7: the reason patterns are linear on runs of whitespace
# ---------------------------------------------------------------------------

_HOSTILE: dict[str, str] = {
    "newlines": "\n" * 8000,
    "carriage returns": "\r" * 8000,
    "crlf pairs": "\r\n" * 4000,
    "blank lines with spaces": "  \n" * 3000,
    "blank lines with tabs": "\t\n" * 3000,
    "spaces": " " * 8000,
    "tabs": "\t" * 8000,
    "unclosed fence then newlines": "```\n" + "\n" * 7000,
    "unclosed tilde fence then newlines": "~~~\n" + "\n" * 7000,
    "unclosed fence then blank lines": "```\n" + " \n" * 3000,
    "many open fences": "```\nx\n" * 1500,
    "many tilde fences": "~~~\n" * 1500,
    "bump after newlines": "\n" * 5000 + "bumps lodash from 1 to 2",
    "bump lines": "  \n" * 2000 + "updates x to 3",
    "dependabot after newlines": "\n" * 5000 + "dependabot will resolve this",
    "heading then newlines": "## " + "\n" * 6000,
    "urls": "see http://a.example " * 350,
    "urls on lines": "http://a.example\n" * 450,
    "url then spaces": "because of http://a.example" + " " * 5000 + ".",
    "comment then newlines": "<!-- x -->" + "\n" * 6000,
}


def test_twenty_hostile_bodies_go_through_extract_reason_in_under_a_second() -> None:
    assert len(_HOSTILE) == 20
    started = time.perf_counter()
    for body in _HOSTILE.values():
        adr_reason.extract_reason("Adopt x", body)
    assert time.perf_counter() - started < 1.0


@pytest.mark.parametrize("name", sorted(_HOSTILE))
def test_each_hostile_body_costs_well_under_a_second(name: str) -> None:
    started = time.perf_counter()
    adr_reason.extract_reason("Adopt x", _HOSTILE[name])
    assert time.perf_counter() - started < 0.5, name


def test_the_hole_patterns_are_linear_on_a_long_run_of_blanks() -> None:
    hole = adr_reason._URL_HOLE
    started = time.perf_counter()
    for text in (" " * 20000, " " * 10000 + hole + " " * 10000, hole + " " * 20000):
        adr_reason._HOLE.sub(" ", text)
        adr_reason._HOLE_BEFORE_PUNCT.sub(r"\1", text)
    assert time.perf_counter() - started < 0.3


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("see   ,", "see,"),
        ("see   in", "see  in"),
        ("( ).", "(  )."),
        ("a  b", "a b"),
        (" start", "start"),
        ("end ", "end"),
        ("x   , y", "x , y"),
        ("onetwo", "one two"),
        ("a  \t\t  b", "a b"),
    ],
)
def test_the_hole_patterns_keep_their_results(text: str, expected: str) -> None:
    filled = adr_reason._HOLE_BEFORE_PUNCT.sub(r"\1", adr_reason.flat(text))
    assert adr_reason._HOLE.sub(" ", filled).strip() == expected


@pytest.mark.parametrize(
    "body",
    [
        "\n\n\n  Bumps lodash from 4.17.20 to 4.17.21 because it fixes a leak.",
        "\r\n\r\nUpdates lodash to 4.17.21 because it fixes a leak.",
        "\n\n\t\nThis PR contains the following updates",
        "x\n\n\n   dependabot will resolve any conflicts with this PR",
    ],
)
def test_a_bump_body_after_blank_lines_is_still_not_a_reason(body: str) -> None:
    assert adr_reason.extract_reason("Adopt x", body) is None


def test_a_fenced_block_after_blank_lines_is_still_removed() -> None:
    body = (
        "We moved the parser because the old one was slow on big inputs.\n\n\n\n"
        "```\nbecause this code line is not a reason at all, said nobody\n```\n"
    )
    assert adr_reason.extract_reason("Adopt x", body) == (
        "We moved the parser because the old one was slow on big inputs."
    )


def test_an_unclosed_fence_after_blank_lines_hides_the_rest() -> None:
    body = "We moved the parser because the old one was slow.\n\n\n```\nbecause none counts\n"
    assert adr_reason.extract_reason("Adopt x", body) == (
        "We moved the parser because the old one was slow."
    )


def test_an_indented_fence_still_opens_a_block() -> None:
    body = "   ```\nbecause this is code and not a reason\n   ```\nWe adopt x because it is fast."
    assert adr_reason.extract_reason("Adopt y", body) == "We adopt x because it is fast."


# ---------------------------------------------------------------------------
# Item 8: duplicate decision-log ids are numbered in linear time, and capped per file
# ---------------------------------------------------------------------------


def _log(tmp_path: Path, rel: str, entries: list[str]) -> Path:
    repo = tmp_path / "r"
    if not repo.exists():
        repo = new_repo(repo)
        commit(repo, "Initial work")
    write(repo, rel, "# Decisions\n\n" + "\n".join(entries) + "\n")
    return repo


def _entries(ids: list[str]) -> list[str]:
    return [f"## {ident} - decision number {n} about the build" for n, ident in enumerate(ids)]


def _candidates(repo: Path) -> tuple[list[dict[str, Any]], dict[str, int]]:
    dropped = dict.fromkeys(adr_docs.DROP_KEYS, 0)
    found, _files, _skipped = adr_log.log_candidates(repo, adr_docs.ExistingAdrs([]), dropped)
    return found, dropped


def _bare(ident: str) -> str:
    """A candidate id without its ``--<title hash>`` part."""
    return ident.split("--")[0]


def test_duplicate_ids_get_distinct_title_keys(tmp_path: Path) -> None:
    repo = _log(tmp_path, "decisions.md", _entries(["D-1", "D-1", "D-2", "D-1"]))
    found, _ = _candidates(repo)
    ids = [c["id"] for c in found]
    assert len(set(ids)) == 4 and ids[2].startswith("log-D-2--")
    assert all(ids[n].startswith("log-D-1--") for n in (0, 1, 3))


def test_a_literal_id_that_looks_like_a_suffix_never_collides(tmp_path: Path) -> None:
    repo = _log(tmp_path, "decisions.md", _entries(["D-1", "D-1.2", "D-1"]))
    found, _ = _candidates(repo)
    ids = [c["id"] for c in found]
    assert len(ids) == len(set(ids)) == 3


def _distinct_titles(count: int) -> list[str]:
    return _entries(["D-1"] * count)


def _one_title(count: int) -> list[str]:
    """Twins: one id and one title, so every entry after the first needs a ``-N`` suffix."""
    return ["## D-1 - the one decision about the build"] * count


_SCRIPTS = str(Path(adr_log.__file__).parent) + os.sep
# Twice the entries is twice the steps when numbering is linear, and four times when each twin
# searches the suffixes again. Measured on 250 and 500 twins: 2.0 times as shipped, 3.7 times
# with the search restarted from one, 2.5 times with it restarted on every sixteenth twin.
_LINEAR_GROWTH = 2.2


def _steps(run: Callable[[], object]) -> int:
    """Bytecode instructions the skill's scripts execute during ``run()``.

    A count, not a clock, so a loaded runner cannot change it. Work inside one C call, such as
    a regex match or a scan of a list, is one instruction: a quadratic hidden there is not seen.
    """
    monitoring = sys.monitoring
    # By convention ids 0, 1, 2 and 5 belong to debuggers, coverage, profilers and optimizers.
    free = [i for i in (3, 4) if monitoring.get_tool(i) is None]
    assert free, "monitoring tool ids 3 and 4 are both taken, so the step meter cannot run"
    tool = free[0]
    count = 0

    def on_instruction(code: CodeType, _offset: int) -> None:
        nonlocal count
        if code.co_filename.startswith(_SCRIPTS):
            count += 1

    monitoring.use_tool_id(tool, "adr-step-meter")
    try:
        monitoring.register_callback(tool, monitoring.events.INSTRUCTION, on_instruction)
        monitoring.set_events(tool, monitoring.events.INSTRUCTION)
        run()
    finally:
        monitoring.set_events(tool, monitoring.events.NO_EVENTS)
        monitoring.register_callback(tool, monitoring.events.INSTRUCTION, None)
        monitoring.free_tool_id(tool)
    return count


def _numbering_steps(tmp_path: Path, entries: list[str]) -> int:
    repo = _log(tmp_path, "decisions.md", entries)
    found: list[dict[str, Any]] = []
    steps = _steps(lambda: found.extend(_candidates(repo)[0]))
    assert len({c["id"] for c in found}) == len(entries)
    assert steps >= len(entries), "the meter counted nothing inside the skill's scripts"
    return steps


def _assert_steps_double(tmp_path: Path, corpus: Callable[[int], list[str]]) -> None:
    small, large = (_numbering_steps(tmp_path, corpus(count)) for count in (250, 500))
    assert large <= _LINEAR_GROWTH * small, (
        f"numbering is not linear for {corpus.__name__}: {small} steps for 250 entries, "
        f"{large} steps for 500, over the {_LINEAR_GROWTH} times bound"
    )


@pytest.mark.parametrize("corpus", [_distinct_titles, _one_title])
def test_eight_thousand_entries_sharing_an_id_are_numbered_in_linear_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, corpus: Callable[[int], list[str]]
) -> None:
    # Two checks: all 8000 entries get distinct ids, and twice the entries cost twice the steps.
    # The per-file caps would drop most of the 8000, so lift them. The step check runs on 250
    # and 500 entries, which fit under both caps.
    monkeypatch.setattr(adr_log, "MAX_LOG_CANDIDATES", 10**6, raising=False)
    monkeypatch.setattr(adr_log, "MAX_LOG_ENTRIES", 10**6)
    repo = _log(tmp_path, "decisions.md", corpus(8000))
    found, _ = _candidates(repo)
    assert len({c["id"] for c in found}) == len(found) == 8000
    _assert_steps_double(tmp_path, corpus)


def test_twins_of_one_id_and_title_are_numbered_in_file_order(tmp_path: Path) -> None:
    repo = _log(tmp_path, "decisions.md", _one_title(4))
    found, _ = _candidates(repo)
    first = found[0]["id"]
    assert first.startswith("log-D-1--")
    assert [c["id"] for c in found] == [first, f"{first}-2", f"{first}-3", f"{first}-4"]


def test_the_step_bound_fails_when_each_twin_searches_the_suffixes_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Negative control: the same check, on the shipped module with its counter removed."""
    counter = "following.get(base.lower(), 1)"
    source = Path(adr_log.__file__).read_text(encoding="utf-8")
    assert source.count(counter) == 1, "the counter moved: point this control at it again"
    # The mutant is this repository's own module with that one expression changed.
    mutant: dict[str, Any] = {"__name__": adr_log.__name__, "__file__": adr_log.__file__}
    exec(compile(source.replace(counter, "1"), adr_log.__file__, "exec"), mutant)
    expected = [c["id"] for c in _candidates(_log(tmp_path, "decisions.md", _one_title(40)))[0]]
    monkeypatch.setattr(adr_log, "log_candidates", mutant["log_candidates"])
    slow = [c["id"] for c in _candidates(_log(tmp_path, "decisions.md", _one_title(40)))[0]]
    assert slow == expected  # the mutant changes the cost of numbering, not the numbers
    _assert_steps_double(tmp_path, _distinct_titles)  # distinct titles never search
    # "DID NOT RAISE" below means the meter no longer sees the suffix search: the check is blind.
    with pytest.raises(AssertionError, match="numbering is not linear"):
        _assert_steps_double(tmp_path, _one_title)


def test_a_log_file_keeps_at_most_the_cap_and_counts_the_rest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(adr_log, "MAX_LOG_CANDIDATES", 3)
    repo = _log(tmp_path, "decisions.md", _entries([f"D-{n}" for n in range(1, 6)]))
    found, dropped = _candidates(repo)
    assert [_bare(c["id"]) for c in found] == ["log-D-1", "log-D-2", "log-D-3"]
    assert dropped["log_over_limit"] == 2


def test_the_cap_is_per_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(adr_log, "MAX_LOG_CANDIDATES", 2)
    repo = _log(tmp_path, "decisions.md", _entries(["D-1", "D-2", "D-3"]))
    _log(tmp_path, "docs/decision-log.md", _entries(["X-1", "X-2", "X-3"]))
    found, dropped = _candidates(repo)
    assert sorted(_bare(c["id"]) for c in found) == ["log-D-1", "log-D-2", "log-X-1", "log-X-2"]
    assert dropped["log_over_limit"] == 2


def test_the_default_cap_is_one_thousand(tmp_path: Path) -> None:
    assert adr_log.MAX_LOG_CANDIDATES == 1000
    repo = _log(tmp_path, "decisions.md", _entries([f"D-{n}" for n in range(1, 1003)]))
    found, dropped = _candidates(repo)
    assert len(found) == 1000 and dropped["log_over_limit"] == 2


def test_entries_that_are_documented_or_have_no_id_do_not_count_toward_the_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(adr_log, "MAX_LOG_CANDIDATES", 2)
    idless = "## Replication strategy overview\n\nNotes with enough prose to count as an entry."
    repo = _log(tmp_path, "decisions.md", [idless, *_entries(["D-1", "D-2", "D-3"])])
    dropped = dict.fromkeys(adr_docs.DROP_KEYS, 0)
    existing = adr_docs.ExistingAdrs([("a.md", "see D-1")])
    found, _files, _skipped = adr_log.log_candidates(repo, existing, dropped)
    assert [_bare(c["id"]) for c in found] == ["log-D-2", "log-D-3"]
    assert dropped["log_no_id"] == 1 and dropped["already_documented"] == 1
    assert dropped["log_over_limit"] == 0


def test_scan_reports_log_over_limit_under_dropped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(adr_log, "MAX_LOG_CANDIDATES", 1)
    repo = _log(tmp_path, "decisions.md", _entries(["D-1", "D-2"]))
    payload = adr_scan.scan(repo, "HEAD", 10, None, None)
    assert payload["dropped"]["log_over_limit"] == 1
    assert [_bare(c["id"]) for c in payload["candidates"]] == ["log-D-1"]


# ---------------------------------------------------------------------------
# Item 10: the ADR corpus is capped
# ---------------------------------------------------------------------------


def _record_reads(monkeypatch: pytest.MonkeyPatch, opened: list[str]) -> None:
    real = adr_locate.read_bounded

    def recording(path: Path) -> str | None:
        opened.append(path.name)
        text: str | None = real(path)
        return text

    monkeypatch.setattr(adr_locate, "read_bounded", recording)


def _adr_repo(tmp_path: Path, count: int, size: int = 30) -> Path:
    repo = new_repo(tmp_path / "r")
    for n in range(1, count + 1):
        write(repo, f"docs/adr/{n:04d}-decision-{n}.md", f"# {n}. D{n}\n" + "x" * size)
    commit(repo, "Initial work")
    return repo


def _read(repo: Path) -> tuple[list[tuple[str, str]], adr_locate.AdrTally]:
    tally = adr_locate.AdrTally()
    return list(adr_locate.read_adr_texts(repo, tally=tally)), tally


def test_reading_stops_after_the_file_cap_and_counts_the_oldest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(adr_locate, "MAX_ADR_FILES", 3)
    texts, tally = _read(_adr_repo(tmp_path, 5))
    assert [path for path, _ in texts] == [f"docs/adr/000{n}-decision-{n}.md" for n in (5, 4, 3)]
    assert (tally.read, tally.skipped, tally.cut) == (3, 2, True)


def test_reading_stops_at_the_first_file_that_would_cross_the_text_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Each file holds 38 characters, so a second one would take the total to 76, past 50.
    monkeypatch.setattr(adr_locate, "MAX_ADR_CHARS", 50)
    texts, tally = _read(_adr_repo(tmp_path, 4, size=30))
    assert len(texts) == 1 and (tally.read, tally.skipped, tally.cut) == (1, 3, True)


def test_a_corpus_exactly_at_the_file_cap_is_not_truncated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(adr_locate, "MAX_ADR_FILES", 3)
    texts, tally = _read(_adr_repo(tmp_path, 3))
    assert len(texts) == 3 and (tally.skipped, tally.cut) == (0, False)


def test_an_oversized_file_is_skipped_but_does_not_mark_the_corpus_truncated(
    tmp_path: Path,
) -> None:
    repo = _adr_repo(tmp_path, 2)
    write(repo, "docs/adr/0003-big.md", "x" * (adr_locate.MAX_READ_BYTES + 1))
    texts, tally = _read(repo)
    assert len(texts) == 2 and (tally.skipped, tally.cut) == (1, False)


def test_the_files_over_the_cap_are_listed_not_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(adr_locate, "MAX_ADR_FILES", 2)
    repo = _adr_repo(tmp_path, 6)
    opened: list[str] = []
    _record_reads(monkeypatch, opened)
    _read(repo)
    adr_reads = [name for name in opened if name.endswith(".md")]
    assert adr_reads == ["0006-decision-6.md", "0005-decision-5.md"]


def test_the_stream_reads_one_file_at_a_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _adr_repo(tmp_path, 4)
    opened: list[str] = []
    _record_reads(monkeypatch, opened)
    stream = adr_locate.read_adr_texts(repo)
    next(stream)
    adr_reads = [name for name in opened if name.endswith(".md")]
    assert adr_reads == ["0004-decision-4.md"]


def test_the_scan_payload_says_when_the_corpus_was_truncated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(adr_locate, "MAX_ADR_FILES", 2)
    payload = adr_scan.scan(_adr_repo(tmp_path, 5), "HEAD", 10, None, None)
    assert payload["adr_corpus_truncated"] is True
    assert payload["examined"]["adr_files"] == 2 and payload["examined"]["adr_files_skipped"] == 3


def test_the_scan_payload_is_not_truncated_by_default(tmp_path: Path) -> None:
    payload = adr_scan.scan(_adr_repo(tmp_path, 3), "HEAD", 10, None, None)
    assert payload["adr_corpus_truncated"] is False


def test_the_default_caps_are_two_thousand_files_and_32_mi_characters() -> None:
    assert adr_locate.MAX_ADR_FILES == 2000
    assert adr_locate.MAX_ADR_CHARS == 32 * 1024 * 1024


def test_existing_adrs_gives_the_same_names_from_a_stream_as_from_a_list() -> None:
    texts = [
        ("a.md", "Decided D-7 in abcdef1234567 see https://x.example/p/1 and #12"),
        ("b.md", "More about v1.2 and D-8"),
    ]
    from_list = adr_docs.ExistingAdrs(texts)
    from_stream = adr_docs.ExistingAdrs(iter(texts))
    for name in ("ids", "hashes", "urls", "numbers"):
        assert getattr(from_list, name) == getattr(from_stream, name), name
