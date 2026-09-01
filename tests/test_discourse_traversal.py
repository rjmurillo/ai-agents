"""Tests for checkpointed recursive discourse traversal.

Covers: positive traversal, negative (inaccessible items), edge cases
(interruption-resume, parser-change detection, invariant violation,
max-items cap, exclusion recording).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from scripts.github_core.discourse_traversal import (
    Checkpoint,
    DefaultParser,
    InvariantError,
    ParserVersionMismatchError,
    load_checkpoint,
    save_checkpoint,
    traverse,
)

# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

REPO = "owner/repo"


@dataclass
class StubFetcher:
    """In-memory fetcher for testing."""

    bodies: dict[str, str | None]
    call_log: list[str] | None = None

    def __post_init__(self) -> None:
        if self.call_log is None:
            self.call_log = []

    def fetch_body(self, ref: str) -> str | None:
        assert self.call_log is not None
        self.call_log.append(ref)
        return self.bodies.get(ref)


@dataclass
class InterruptingFetcher:
    """Fetcher that raises after N calls to simulate interruption."""

    bodies: dict[str, str | None]
    max_calls: int
    call_count: int = 0

    def fetch_body(self, ref: str) -> str | None:
        self.call_count += 1
        if self.call_count > self.max_calls:
            raise KeyboardInterrupt("simulated interruption")
        return self.bodies.get(ref)


@dataclass
class VersionedParser:
    """Parser with configurable version for testing parser-change detection."""

    version: str
    _delegate: DefaultParser | None = None

    def __post_init__(self) -> None:
        self._delegate = DefaultParser()

    def extract(self, text: str, repo: str) -> set[str]:
        assert self._delegate is not None
        return self._delegate.extract(text, repo)


# ---------------------------------------------------------------------------
# Positive tests
# ---------------------------------------------------------------------------


class TestPositiveTraversal:
    """Tests for successful traversal scenarios."""

    def test_single_seed_no_links(self, tmp_path: Path) -> None:
        """Single seed with no outgoing links completes immediately."""
        fetcher = StubFetcher(bodies={f"{REPO}#1": "No links here."})
        result = traverse(
            seeds=[f"{REPO}#1"],
            repo=REPO,
            fetcher=fetcher,
            checkpoint_path=tmp_path / "cp.json",
        )
        assert result.visited == {f"{REPO}#1"}
        assert result.edges == []
        assert result.discovered_count == 1

    def test_linear_chain(self, tmp_path: Path) -> None:
        """Traversal follows a linear chain of references."""
        fetcher = StubFetcher(
            bodies={
                f"{REPO}#1": f"See #{2}",
                f"{REPO}#2": f"See #{3}",
                f"{REPO}#3": "End.",
            }
        )
        result = traverse(
            seeds=[f"{REPO}#1"],
            repo=REPO,
            fetcher=fetcher,
            checkpoint_path=tmp_path / "cp.json",
        )
        assert result.visited == {f"{REPO}#1", f"{REPO}#2", f"{REPO}#3"}
        assert result.discovered_count == 3

    def test_full_url_references(self, tmp_path: Path) -> None:
        """Traversal recognizes full GitHub URLs."""
        fetcher = StubFetcher(
            bodies={
                f"{REPO}#1": "See https://github.com/owner/repo/issues/2",
                f"{REPO}#2": "Done.",
            }
        )
        result = traverse(
            seeds=[f"{REPO}#1"],
            repo=REPO,
            fetcher=fetcher,
            checkpoint_path=tmp_path / "cp.json",
        )
        assert f"{REPO}#2" in result.visited

    def test_cycle_detection(self, tmp_path: Path) -> None:
        """Cycles do not cause infinite traversal."""
        fetcher = StubFetcher(
            bodies={
                f"{REPO}#1": "See #2",
                f"{REPO}#2": "See #1",
            }
        )
        result = traverse(
            seeds=[f"{REPO}#1"],
            repo=REPO,
            fetcher=fetcher,
            checkpoint_path=tmp_path / "cp.json",
        )
        assert result.visited == {f"{REPO}#1", f"{REPO}#2"}

    def test_checkpoint_written(self, tmp_path: Path) -> None:
        """Checkpoint file is written after traversal."""
        cp_path = tmp_path / "cp.json"
        fetcher = StubFetcher(bodies={f"{REPO}#1": "No links."})
        traverse(
            seeds=[f"{REPO}#1"],
            repo=REPO,
            fetcher=fetcher,
            checkpoint_path=cp_path,
        )
        assert cp_path.exists()
        data = json.loads(cp_path.read_text())
        assert data["discovered_count"] == 1
        assert data["parser_version"] == "1"


# ---------------------------------------------------------------------------
# Negative tests
# ---------------------------------------------------------------------------


class TestNegativeTraversal:
    """Tests for failure and inaccessible item scenarios."""

    def test_inaccessible_item_excluded(self, tmp_path: Path) -> None:
        """Items that return None are marked as exclusions."""
        fetcher = StubFetcher(
            bodies={
                f"{REPO}#1": "See #2",
                f"{REPO}#2": None,  # not accessible
            }
        )
        result = traverse(
            seeds=[f"{REPO}#1"],
            repo=REPO,
            fetcher=fetcher,
            checkpoint_path=tmp_path / "cp.json",
        )
        assert f"{REPO}#2" in result.exclusions
        assert result.exclusions[f"{REPO}#2"] == "not_accessible"

    def test_cross_repo_excluded(self, tmp_path: Path) -> None:
        """Cross-repo references are not followed."""
        fetcher = StubFetcher(
            bodies={
                f"{REPO}#1": "See https://github.com/other/repo/issues/99",
            }
        )
        result = traverse(
            seeds=[f"{REPO}#1"],
            repo=REPO,
            fetcher=fetcher,
            checkpoint_path=tmp_path / "cp.json",
        )
        assert result.visited == {f"{REPO}#1"}
        assert result.discovered_count == 1


# ---------------------------------------------------------------------------
# Edge case tests
# ---------------------------------------------------------------------------


class TestInterruptionResume:
    """Tests for checkpoint resume after interruption."""

    def test_resume_after_interruption(self, tmp_path: Path) -> None:
        """Traversal resumes from checkpoint after interruption."""
        cp_path = tmp_path / "cp.json"
        bodies = {
            f"{REPO}#1": "See #2 #3",
            f"{REPO}#2": "See #4",
            f"{REPO}#3": "Done.",
            f"{REPO}#4": "Done.",
        }

        # First run: interrupts after 2 fetches
        fetcher1 = InterruptingFetcher(bodies=bodies, max_calls=2)
        with pytest.raises(KeyboardInterrupt):
            traverse(
                seeds=[f"{REPO}#1"],
                repo=REPO,
                fetcher=fetcher1,
                checkpoint_path=cp_path,
                batch_size=1,
            )

        assert cp_path.exists()

        # Second run: resumes and completes
        fetcher2 = StubFetcher(bodies=bodies)
        result = traverse(
            seeds=[f"{REPO}#1"],
            repo=REPO,
            fetcher=fetcher2,
            checkpoint_path=cp_path,
            batch_size=1,
        )
        assert result.visited == {
            f"{REPO}#1",
            f"{REPO}#2",
            f"{REPO}#3",
            f"{REPO}#4",
        }

    def test_resume_does_not_refetch_visited(self, tmp_path: Path) -> None:
        """Resumed traversal skips already-visited items."""
        cp_path = tmp_path / "cp.json"
        # Pre-populate checkpoint with #1 visited, #2 pending
        cp = Checkpoint(
            parser_version="1",
            repo=REPO,
            visited={f"{REPO}#1"},
            pending=[f"{REPO}#2"],
            discovered_count=2,
            edges=[],
            exclusions={},
        )
        save_checkpoint(cp, cp_path)

        fetcher = StubFetcher(bodies={f"{REPO}#2": "Done."})
        result = traverse(
            seeds=[f"{REPO}#1"],
            repo=REPO,
            fetcher=fetcher,
            checkpoint_path=cp_path,
        )
        # Should NOT have fetched #1 again
        assert fetcher.call_log == [f"{REPO}#2"]
        assert result.visited == {f"{REPO}#1", f"{REPO}#2"}


class TestParserChange:
    """Tests for parser version mismatch detection."""

    def test_parser_version_mismatch_raises(self, tmp_path: Path) -> None:
        """Loading checkpoint with different parser version raises."""
        cp_path = tmp_path / "cp.json"
        cp = Checkpoint(
            parser_version="1",
            repo=REPO,
            visited={f"{REPO}#1"},
            pending=[],
            discovered_count=1,
        )
        save_checkpoint(cp, cp_path)

        new_parser = VersionedParser(version="2")
        with pytest.raises(ParserVersionMismatchError, match="'1'.*'2'"):
            load_checkpoint(cp_path, new_parser)

    def test_same_parser_version_loads(self, tmp_path: Path) -> None:
        """Loading checkpoint with same parser version succeeds."""
        cp_path = tmp_path / "cp.json"
        cp = Checkpoint(
            parser_version="1",
            repo=REPO,
            visited={f"{REPO}#1"},
            pending=[],
            discovered_count=1,
        )
        save_checkpoint(cp, cp_path)

        parser = VersionedParser(version="1")
        loaded = load_checkpoint(cp_path, parser)
        assert loaded.visited == {f"{REPO}#1"}


class TestInvariantViolation:
    """Tests for checkpoint invariant enforcement."""

    def test_corrupted_checkpoint_raises(self, tmp_path: Path) -> None:
        """Checkpoint with broken invariant raises InvariantError."""
        cp_path = tmp_path / "cp.json"
        bad_data = {
            "schema_version": 1,
            "parser_version": "1",
            "repo": REPO,
            "visited": [f"{REPO}#1"],
            "pending": [f"{REPO}#2"],
            "discovered_count": 5,  # Should be 2, not 5
            "edges": [],
            "exclusions": {},
        }
        cp_path.write_text(json.dumps(bad_data))

        parser = DefaultParser()
        with pytest.raises(InvariantError, match="2 != .*5"):
            load_checkpoint(cp_path, parser)


class TestMaxItems:
    """Tests for max-items safety cap."""

    def test_max_items_stops_discovery(self, tmp_path: Path) -> None:
        """Traversal stops discovering new items at max_items."""
        # Create a graph where #1 links to #2..#20
        bodies = {f"{REPO}#1": " ".join(f"#{i}" for i in range(2, 21))}
        for i in range(2, 21):
            bodies[f"{REPO}#{i}"] = "Done."

        fetcher = StubFetcher(bodies=bodies)
        result = traverse(
            seeds=[f"{REPO}#1"],
            repo=REPO,
            fetcher=fetcher,
            checkpoint_path=tmp_path / "cp.json",
            max_items=5,
        )
        # Should cap at 5 discovered
        assert result.discovered_count == 5
        # Some refs should be in exclusions with max_items_reached
        assert any(
            v == "max_items_reached" for v in result.exclusions.values()
        )
