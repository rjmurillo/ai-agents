"""Tests for the second batch of PR #7527 CodeRabbit minor findings (the review summary)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, BinaryIO

import adr_commits
import adr_docs
import adr_locate
import adr_reason
import adr_shape
import pytest

F3 = "`" * 3


@pytest.mark.parametrize(
    ("title", "kept"),
    [
        ("Allow at most 5 retries per request", True),
        ("feat: cap retry attempts at most 5 per request", True),
        ("fix: allow at most 5 retries per request", False),
    ],
)
def test_a_numeric_bound_title_survives_the_final_filter(title: str, kept: bool) -> None:
    assert adr_shape.is_decision_shaped_title(title) is kept


def test_a_promoted_merge_keeps_the_description_its_own_paragraph() -> None:
    body = (
        "Use the primary for every write in the order service\n\n"
        "Route writes through the primary because replicas lag."
    )
    shape = adr_shape.resolve_commit_shape("Merge pull request #78 from x/y", body)

    assert "Merge pull request #78" in shape.body and "\n\n" in shape.body
    reason = adr_reason.extract_reason(shape.subject, shape.body)
    assert reason is not None and "replicas lag" in reason


@pytest.mark.parametrize(
    ("body", "stated"),
    [("Fixes #123", False), ("Fixes a crash because the cache was never cleared.", True)],
)
def test_a_bare_issue_pointer_is_not_rationale(body: str, stated: bool) -> None:
    assert adr_shape.has_stated_rationale("Switch to a primary write path", body) is stated


@pytest.mark.parametrize(
    "body",
    [
        "Body.\n\nBREAKING CHANGE: clients must read the new field.\n\nRefs #123",
        "Body.\n\nBREAKING CHANGE: clients must\n  read the new field.\nRefs: #12",
    ],
)
def test_a_breaking_footer_is_found_before_later_footers(body: str) -> None:
    assert adr_reason.breaking_change("feat: add the field", body)


def test_a_breaking_line_in_a_fenced_example_is_not_a_footer() -> None:
    body = f"Body.\n\n{F3}\nBREAKING CHANGE: demo only\n{F3}"

    assert not adr_reason.breaking_change("feat: add the field", body)


def test_a_label_qualifies_only_the_sentence_it_introduces() -> None:
    body = "Why: Replicas lose writes during failover. The badge appears on the dashboard."

    reason = adr_reason.extract_reason("Move writes to the primary", body)

    assert reason is not None and "failover" in reason and "badge" not in reason


def test_a_bump_line_in_a_fence_does_not_discard_the_reason() -> None:
    body = (
        f"{F3}\nUpdates library from v1 to v2\n{F3}\n\n"
        "We moved writes to the primary because replicas lag behind."
    )

    reason = adr_reason.extract_reason("Move writes to the primary", body)

    assert reason is not None and "replicas lag" in reason


def test_a_changelog_heading_in_a_fence_does_not_cut_the_reason() -> None:
    body = (
        f"{F3}\n## Changelog\n- old\n{F3}\n\n"
        "We moved writes to the primary because replicas lag behind."
    )

    reason = adr_reason.extract_reason("Move writes to the primary", body)

    assert reason is not None and "replicas lag" in reason


def test_issue_prose_reaches_scoring_and_an_issue_pointer_does_not() -> None:
    prose = adr_reason.extract_reason(
        "Move writes to the primary", "Issue: Replicas lose writes because failover resets it."
    )
    pointer = adr_reason.extract_reason("Move writes to the primary", "Issue: #123")

    assert prose is not None and "failover" in prose
    assert pointer is None


def test_a_cut_sentence_never_hides_its_marker() -> None:
    cap = adr_reason.REASON_MAX_CHARS
    lead = "word " * ((cap - len(" because,")) // 5)
    sentence = (lead[: cap - len(" because,")] + " because,more text follows here " * 4).strip()

    shown = adr_reason._fit(sentence, False)

    assert shown is None or "because" in shown


def test_a_whitespace_only_line_ends_the_subject() -> None:
    assert adr_commits._subject_and_body("Adopt Rust\n  \nBecause it is fast.") == (
        "Adopt Rust",
        "Because it is fast.",
    )


def test_a_shorter_fence_inside_an_adr_fence_stays_text() -> None:
    text = f"````\n{F3}\n## Example\n````\n## Real"

    assert adr_docs.lines_outside_fences(text) == ["## Real"]


class _ReadSpy:
    """A file handle that records every size passed to ``read``."""

    def __init__(self, handle: BinaryIO, sizes: list[int]) -> None:
        self._handle, self._sizes = handle, sizes

    def __enter__(self) -> _ReadSpy:
        return self

    def __exit__(self, *_exc: object) -> None:
        self._handle.close()

    def read(self, size: int = -1) -> bytes:
        self._sizes.append(size)
        return self._handle.read(size)


def test_read_bounded_reads_at_most_one_byte_past_the_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    big = tmp_path / "big.md"
    big.write_bytes(b"x" * (adr_locate.MAX_READ_BYTES + 1))
    exact = tmp_path / "exact.md"
    exact.write_bytes(b"x\r\n" + b"x" * (adr_locate.MAX_READ_BYTES - 3))
    sizes: list[int] = []

    def spy_open(*args: Any, **kwargs: Any) -> _ReadSpy:
        return _ReadSpy(open(*args, **kwargs), sizes)

    # read_bounded wraps the descriptor it checked with the module's ``open``.
    monkeypatch.setattr(adr_locate, "open", spy_open, raising=False)

    assert adr_locate.read_bounded(big) is None
    text = adr_locate.read_bounded(exact)
    assert text is not None and text.startswith("x\nx")
    # A read of the whole file would ask for -1 bytes, or more than one past the cap.
    assert sizes and all(0 <= size <= adr_locate.MAX_READ_BYTES + 1 for size in sizes)
