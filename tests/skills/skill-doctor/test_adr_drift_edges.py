"""adr_drift.py supersession edges: frontmatter shapes, prose labels, links, dedupe, lines."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import adr_checks
import adr_corpus
import adr_text as text_module
import pytest
from adr_drift_helpers import adr_path, adr_text, kinds, scan, seeded_repo

NNNN_DIR = "docs/adr"


def _raw(number: int, front: str = "", status: str = "accepted", extra: str = "") -> str:
    head = f"---\n{front}---\n\n" if front else ""
    return f"{head}# ADR-{number:03d}: T\n\n## Status\n\n{status}\n\n## Context\n\n{extra}\n"


def _scan(tmp_path: Path, capsys, files: dict[str, str]) -> dict[str, Any]:
    return scan(capsys, seeded_repo(tmp_path / "repo", files))


def _missing(result: dict[str, Any]) -> list[dict[str, Any]]:
    return kinds(result, "adr-supersedes-missing-target")


def _numbers(result: dict[str, Any]) -> list[int]:
    return sorted(f["evidence"]["number"] for f in _missing(result))


@pytest.mark.parametrize(
    "front",
    [
        "supersedes: ADR-777\n",
        "supersedes: [ADR-777]\n",
        "supersedes:\n  - ADR-777\n",
        "supersedes: [777]\n",
        "supersedes:\n  - 777\n",
        "supersedes: ADR-777-old.md\n",
        "supersedes: ../architecture/ADR-777-old.md\n",
        "supersedes: [ADR-777](ADR-777-old.md)\n",
    ],
    ids=[
        "scalar",
        "flow-list",
        "block-list",
        "flow-bare-int",
        "block-bare-int",
        "filename",
        "relative-path",
        "markdown-link",
    ],
)
def test_frontmatter_shapes_each_yield_one_edge_to_777(tmp_path, capsys, front):
    files = {adr_path(1): _raw(1, front)}

    assert _numbers(_scan(tmp_path, capsys, files)) == [777]


@pytest.mark.parametrize(
    "front",
    ["supersedes: 2024-01-15\n", "date: 2025-03-04\nsupersedes: []\n", "supersedes: null\n"],
    ids=["date-value", "date-key", "null"],
)
def test_dates_and_null_in_frontmatter_are_not_edges(tmp_path, capsys, front):
    files = {adr_path(1): _raw(1, front)}

    assert _numbers(_scan(tmp_path, capsys, files)) == []


def test_unclosed_frontmatter_is_read_as_prose_and_does_not_crash(tmp_path, capsys):
    files = {adr_path(1): "---\nsupersedes: ADR-777\n# ADR-001: T\n\n## Status\n\naccepted\n"}

    found = _missing(_scan(tmp_path, capsys, files))

    assert [(f["evidence"]["number"], f["evidence"]["line"]) for f in found] == [(777, 2)]


def test_madr_frontmatter_status_superseded_by_is_an_edge_on_the_status_line(tmp_path, capsys):
    front = "title: x\nstatus: superseded by ADR-777\n"
    files = {adr_path(1): _raw(1, front, status="superseded by ADR-777")}

    found = _missing(_scan(tmp_path, capsys, files))

    assert [f["evidence"]["number"] for f in found] == [777]
    assert found[0]["evidence"]["line"] == 3


def test_a_frontmatter_finding_carries_the_line_of_its_key(tmp_path, capsys):
    front = "title: x\ndate: 2025-01-01\nsupersedes: ADR-777\n"
    files = {adr_path(1): _raw(1, front)}

    found = _missing(_scan(tmp_path, capsys, files))

    assert found[0]["evidence"]["line"] == 4


@pytest.mark.parametrize(
    "line",
    ["Supersedes: ADR-777", "- **Supersedes:** ADR-777", "Status: Superseded by ADR-777"],
    ids=["label", "bold-list-label", "inline-status"],
)
def test_prose_labels_are_edges(tmp_path, capsys, line):
    files = {adr_path(1): _raw(1, extra=line)}

    found = _missing(_scan(tmp_path, capsys, files))

    assert [f["evidence"]["number"] for f in found] == [777]
    assert found[0]["evidence"]["line"] is not None


def test_a_linked_status_line_gives_one_finding_not_two(tmp_path, capsys):
    files = {adr_path(1): _raw(1, status="Superseded by [ADR-777](ADR-777-x.md)")}

    assert len(_missing(_scan(tmp_path, capsys, files))) == 1


def test_the_same_edge_in_frontmatter_and_prose_is_one_finding(tmp_path, capsys):
    files = {adr_path(1): _raw(1, "supersedes: ADR-777\n", extra="Supersedes: ADR-777")}

    assert len(_missing(_scan(tmp_path, capsys, files))) == 1


def _plain(number: int, title: str, status: str) -> str:
    return f"# {number}. {title}\n\n## Status\n\n{status}\n\n## Context\n\nc\n"


def test_adr_tools_link_form_is_reciprocal_when_both_sides_link(tmp_path, capsys):
    files = {
        f"{NNNN_DIR}/0001-use-x.md": _plain(1, "Use X", "Superseded by [2. Use Y](0002-use-y.md)"),
        f"{NNNN_DIR}/0002-use-y.md": _plain(
            2, "Use Y", "Accepted\n\nSupersedes [1. Use X](0001-use-x.md)"
        ),
    }

    result = _scan(tmp_path, capsys, files)

    assert not kinds(result, "adr-supersession-not-reciprocal") and not _missing(result)


def test_adr_tools_link_form_one_sided_is_not_reciprocal(tmp_path, capsys):
    files = {
        f"{NNNN_DIR}/0001-use-x.md": _plain(1, "Use X", "Accepted"),
        f"{NNNN_DIR}/0002-use-y.md": _plain(
            2, "Use Y", "Accepted\n\nSupersedes [1. Use X](0001-use-x.md)"
        ),
    }

    found = kinds(_scan(tmp_path, capsys, files), "adr-supersession-not-reciprocal")

    assert len(found) == 1 and found[0]["evidence"]["path"].endswith("0001-use-x.md")


def test_a_plain_link_to_an_unrelated_record_is_not_an_edge(tmp_path, capsys):
    files = {
        adr_path(1): adr_text(1, body="See [ADR-002](ADR-002-decision.md)."),
        adr_path(2): adr_text(2),
    }

    result = _scan(tmp_path, capsys, files)

    assert not kinds(result, "adr-supersession-not-reciprocal") and not _missing(result)


def test_edges_lists_one_edge_per_kind_and_number(tmp_path):
    files = {
        adr_path(1): _raw(
            1,
            "supersedes: ADR-777\n",
            status="Superseded by [ADR-5](ADR-005-x.md)",
            extra="Supersedes: ADR-777",
        )
    }
    repo = seeded_repo(tmp_path / "repo", files)
    survey = adr_corpus.find_adr_dirs(repo)

    (doc,) = adr_corpus.read_docs(survey)

    found = adr_checks.edges(doc)
    assert sorted((e.kind, e.number) for e in found) == [("superseded_by", 5), ("supersedes", 777)]


def test_a_one_line_html_comment_is_not_prose():
    lines = ["<!-- Supersedes [1. Old](0001-old.md) -->", "Live text"]

    assert [text for _, text in text_module.prose_lines(lines)] == ["Live text"]


def test_frontmatter_edges_win_over_a_longer_prose_chain(tmp_path, capsys):
    old = adr_text(1, status="superseded").replace("superseded-by: null", "superseded-by: ADR-002")
    old = old.replace(
        "## Status\n\nsuperseded\n",
        "## Status\n\nSuperseded by ADR-002, which ADR-003 later replaced.\n",
    )
    repo = seeded_repo(
        tmp_path / "repo",
        {
            adr_path(1): old,
            adr_path(2): adr_text(2, status="superseded").replace(
                "supersedes: []", "supersedes: [ADR-001]"
            ),
            adr_path(3): adr_text(3).replace("supersedes: []", "supersedes: [ADR-002]"),
        },
    )

    found = kinds(scan(capsys, repo), "adr-supersession-not-reciprocal")

    assert [f["evidence"]["path"] for f in found] == [adr_path(2)]


@pytest.mark.parametrize(
    "front",
    ["supersedes: []\n", "supersedes: [ ]\n"],
    ids=["empty-list", "spaced-empty-list"],
)
def test_an_empty_frontmatter_list_clears_a_prose_edge_of_that_kind(tmp_path, capsys, front):
    files = {adr_path(1): _raw(1, front, extra="**Supersedes**: ADR-777 (pending validation)")}

    assert _numbers(_scan(tmp_path, capsys, files)) == []


@pytest.mark.parametrize(
    "front",
    ["", "supersedes: null\n", "supersedes:\n", "superseded-by: []\n"],
    ids=["absent", "null", "blank", "other-kind-cleared"],
)
def test_a_prose_edge_survives_when_frontmatter_does_not_clear_its_kind(tmp_path, capsys, front):
    files = {adr_path(1): _raw(1, front, extra="Supersedes: ADR-777")}

    assert _numbers(_scan(tmp_path, capsys, files)) == [777]


def test_a_blank_key_with_list_items_declares_its_edges_over_prose(tmp_path, capsys):
    files = {adr_path(1): _raw(1, "supersedes:\n  - ADR-777\n", extra="Supersedes: ADR-888")}

    assert _numbers(_scan(tmp_path, capsys, files)) == [777]
