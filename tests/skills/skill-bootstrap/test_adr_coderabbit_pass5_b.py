"""Tests for the PR #7527 CodeRabbit pass 5 findings, group B: decision logs (``adr_log``).

Each section names the finding it pins. ``test_adr_coderabbit_pass5_b_part2.py`` holds the
``adr_docs`` and ``adr_locate`` findings.
"""

from __future__ import annotations

import os
from hashlib import sha256
from pathlib import Path
from typing import Any

import adr_docs
import adr_log
import pytest
from adr_helpers import write

LONG = "Adopt the shared build cache for every service " + "x" * 120


def _hash(title: str) -> str:
    return sha256(title.encode()).hexdigest()[:8]


def _candidates(root: Path, *adrs: str) -> tuple[list[dict[str, Any]], dict[str, int]]:
    dropped = dict.fromkeys(adr_docs.DROP_KEYS, 0)
    existing = adr_docs.ExistingAdrs((f"a{n}.md", text) for n, text in enumerate(adrs))
    found, _files, _skipped = adr_log.log_candidates(root, existing, dropped)
    return found, dropped


# ---------------------------------------------------------------------------
# B1: the key hashes the full title, and only the display is cut to 120 characters
# ---------------------------------------------------------------------------


def test_titles_that_differ_after_the_display_cut_get_their_own_hashes() -> None:
    log = f"id: D-1\n{LONG} alpha\n\nid: D-1\n{LONG} beta\n"
    flipped = f"id: D-1\n{LONG} beta\n\nid: D-1\n{LONG} alpha\n"

    keys = adr_log._entry_keys([("L.md", e) for e in adr_log.split_decision_log(log)])
    again = adr_log._entry_keys([("L.md", e) for e in adr_log.split_decision_log(flipped)])

    assert keys == [f"D-1--{_hash(LONG + ' alpha')}", f"D-1--{_hash(LONG + ' beta')}"]
    assert again == keys[::-1]


def test_a_long_log_title_is_cut_to_120_characters_only_for_display(tmp_path: Path) -> None:
    write(tmp_path, "DECISIONS.md", f"id: D-1\n{LONG} alpha\n")

    (candidate,), _ = _candidates(tmp_path)

    assert candidate["title"] == f"{LONG} alpha"[:120]
    assert candidate["source"]["entry_id"] == f"D-1--{_hash(LONG + ' alpha')}"


def test_a_display_cut_at_a_space_leaves_no_trailing_blank(tmp_path: Path) -> None:
    write(tmp_path, "DECISIONS.md", f"id: D-1\n{'a' * 119} b\n")

    (candidate,), _ = _candidates(tmp_path)

    assert candidate["title"] == "a" * 119


# ---------------------------------------------------------------------------
# B12: a title line that cleans to nothing falls back to the id
# ---------------------------------------------------------------------------


def test_a_title_line_of_only_nul_falls_back_to_the_id(tmp_path: Path) -> None:
    write(tmp_path, "DECISIONS.md", "# Log\n\nid: D-1\n\x00\n")

    (entry,) = adr_log.split_decision_log("# Log\n\nid: D-1\n\x00\n")
    (candidate,), _ = _candidates(tmp_path)

    assert entry.title == "D-1" and candidate["title"] == "D-1"


def test_an_ordinary_title_is_unchanged_by_the_cleaning() -> None:
    (entry,) = adr_log.split_decision_log("id: D-1\n\x00\nAdopt trunk-based development\n")
    (plain,) = adr_log.split_decision_log("- D-2: Use Renovate for dependency updates\n")

    assert entry.title == "Adopt trunk-based development"
    assert plain.title == "D-2: Use Renovate for dependency updates"


# ---------------------------------------------------------------------------
# B6: a log reached twice through a docs link is read once
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="no symlinks")
def test_a_docs_link_to_the_root_lists_the_root_log_once(tmp_path: Path) -> None:
    write(tmp_path, "decision-log.md", "- D-1: Adopt trunk-based development for every repo\n")
    try:
        (tmp_path / "docs").symlink_to(tmp_path, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks not permitted")

    found, dropped = _candidates(tmp_path, "See D-1.")

    assert adr_log.find_log_files(tmp_path) == ["decision-log.md"]
    assert found == [] and dropped["already_documented"] == 1


# ---------------------------------------------------------------------------
# B7: one log that fails its metadata check does not hide its siblings
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("method", ["is_file", "resolve"])
def test_a_log_that_fails_its_check_leaves_its_siblings_listed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, method: str
) -> None:
    write(tmp_path, "a-ledger.md", "id: D-1\nAdopt x\n")
    write(tmp_path, "decision-log.md", "- D-2: Use Renovate for dependency updates\n")
    real = getattr(Path, method)

    def failing(self: Path, *args: Any, **kwargs: Any) -> Any:
        if self.name == "a-ledger.md":
            raise PermissionError(13, "denied", str(self))
        return real(self, *args, **kwargs)

    monkeypatch.setattr(Path, method, failing)

    assert adr_log.find_log_files(tmp_path) == ["decision-log.md"]


# ---------------------------------------------------------------------------
# B14: a record section heading at the ledger's depth stays with its record
# ---------------------------------------------------------------------------


def test_a_level_two_rationale_keeps_the_ledger_records_reason_and_date() -> None:
    log = (
        "# Ledger\n\nid: D-1 | status: test\nWe chose the x runtime.\n\n## Rationale\n\n"
        "Because it is fast in CI runs.\n\ndate: 2026-03-04\n"
    )

    entries = adr_log.split_decision_log(log)

    assert [entry.id for entry in entries] == ["D-1"]
    assert "fast in CI runs" in entries[0].text
    assert adr_log.entry_date(entries[0].text) == "2026-03-04"


@pytest.mark.parametrize("heading", ["How to add a decision", "Notes", "References"])
@pytest.mark.parametrize("record", ["id: D-1 | status: test", "- D-1: Adopt x"])
def test_an_unrelated_section_after_a_ledger_record_still_splits(record: str, heading: str) -> None:
    log = (
        f"# Ledger\n\n{record}\nWe chose the x runtime.\n\n"
        f"## {heading}\n\nAdd one line per decision because reviewers read it.\n"
    )

    entries = adr_log.split_decision_log(log)

    assert [entry.id for entry in entries] == ["D-1", None]
    assert "reviewers read" not in entries[0].text


# ---------------------------------------------------------------------------
# B15: literal ids reserve keys, and a citation that names two entries documents neither
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("spell", [str, str.upper])
def test_a_generated_key_never_equals_another_entrys_literal_id(spell: Any) -> None:
    literal = spell(f"D-1--{_hash('Adopt x')}")
    entries = [
        ("L.md", adr_log.LogEntry("D-1", None, "Adopt x", "Adopt x")),
        ("L.md", adr_log.LogEntry(literal, None, "Keep y", "Keep y")),
    ]

    keys = adr_log._entry_keys(entries)

    assert keys[0] == f"D-1--{_hash('Adopt x')}-2"
    assert keys[0].lower() != literal.lower() and keys[1].lower() != literal.lower()


def test_a_citation_of_a_legacy_key_that_is_also_a_literal_id_documents_neither(
    tmp_path: Path,
) -> None:
    legacy = f"D-1--{_hash('Adopt x for builds')}"
    write(tmp_path, "DECISIONS.md", f"id: D-1\nAdopt x for builds\n\nid: {legacy}\nKeep y\n")

    found, dropped = _candidates(tmp_path, f"Recorded as {legacy}.")

    assert [c["source"]["entry_id"] for c in found] == [
        f"{legacy}-2",
        f"{legacy}--{_hash('Keep y')}",
    ]
    assert dropped["already_documented"] == 0


def test_a_literal_id_equal_to_a_suffixed_twin_key_is_ambiguous_too(tmp_path: Path) -> None:
    twin = f"D-1--{_hash('Adopt x')}-2"
    write(tmp_path, "DECISIONS.md", f"id: D-1\nAdopt x\n\nid: D-1\nAdopt x\n\nid: {twin}\nKeep y\n")

    found, dropped = _candidates(tmp_path, f"Recorded as {twin}.")

    assert len(found) == 3 and dropped["already_documented"] == 0


def test_a_current_key_documents_its_entry_even_when_it_was_another_twins_old_key(
    tmp_path: Path,
) -> None:
    key = f"D-1--{_hash('Adopt x')}"
    write(tmp_path, "DECISIONS.md", f"id: D-1\nAdopt x\n\nid: D-1\nAdopt x\n\nid: {key}\nKeep y\n")

    found, dropped = _candidates(tmp_path, f"Recorded as {key}-2.")

    assert [c["source"]["entry_id"] for c in found] == [f"{key}-3", f"{key}--{_hash('Keep y')}"]
    assert dropped["already_documented"] == 1


def test_an_unambiguous_citation_still_documents_only_its_entry(tmp_path: Path) -> None:
    legacy = f"D-1--{_hash('Adopt x for builds')}"
    write(tmp_path, "DECISIONS.md", f"id: D-1\nAdopt x for builds\n\nid: {legacy}\nKeep y\n")

    by_key, _ = _candidates(tmp_path, f"Recorded as {legacy}-2.")
    by_literal_key, _ = _candidates(tmp_path, f"Recorded as {legacy}--{_hash('Keep y')}.")

    assert [c["source"]["entry_id"] for c in by_key] == [f"{legacy}--{_hash('Keep y')}"]
    assert [c["source"]["entry_id"] for c in by_literal_key] == [f"{legacy}-2"]
