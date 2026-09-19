"""Guard always-on membership without preserving volatile measurements."""

from __future__ import annotations

import pytest

from tests.validation.always_on_corpus_helpers import (
    _TABLE_HEADER,
    BOOK_RULES,
    CORPUS_PROSE_DOCS,
    DOCTRINE,
    LIBRARY_SKILL,
    MIRROR_DIR,
    PLUGIN_DIR,
    generated_always_on,
    measured_always_on,
    parse_corpus_membership,
    parse_doctrine_table,
    parse_library_sentence,
)


def test_generated_trees_preserve_the_same_membership() -> None:
    mirror = generated_always_on(MIRROR_DIR)
    plugin = generated_always_on(PLUGIN_DIR)
    assert mirror
    assert mirror == plugin
    assert "universal" in mirror


def test_doctrine_table_matches_generated_membership() -> None:
    listed = parse_doctrine_table(DOCTRINE.read_text(encoding="utf-8"))
    assert listed == measured_always_on()


def test_doctrine_does_not_publish_volatile_measurements() -> None:
    text = DOCTRINE.read_text(encoding="utf-8").lower()
    assert "bytes" not in text
    assert "instruction_budget" not in text
    assert "8kb" not in text


def test_doctrine_table_parser_rejects_a_missing_table() -> None:
    with pytest.raises(ValueError, match="not found"):
        parse_doctrine_table("# doc with no table\n\nprose only.\n")


def test_doctrine_table_parser_rejects_a_header_with_no_rows() -> None:
    with pytest.raises(ValueError, match="no rule rows"):
        parse_doctrine_table(f"{_TABLE_HEADER}\n|---|---|\n\nprose.\n")


def test_doctrine_table_parser_reads_every_row() -> None:
    doc = (
        f"{_TABLE_HEADER}\n|---|---|\n"
        "| `applyTo: '**'` | `alpha`, `beta` |\n"
        "| `alwaysApply: true` | `gamma` |\n"
        '| `paths: ["**"]` | `delta` |\n'
    )
    assert parse_doctrine_table(doc) == {"alpha", "beta", "gamma", "delta"}


def test_library_skill_loading_sentence_matches_reality() -> None:
    always, code = parse_library_sentence(LIBRARY_SKILL.read_text(encoding="utf-8"))
    measured = measured_always_on()
    assert always | code == BOOK_RULES
    assert always == BOOK_RULES & measured
    assert not code & measured


def test_library_sentence_parser_rejects_an_unexpected_shape() -> None:
    with pytest.raises(ValueError, match="expected shape"):
        parse_library_sentence("For the everyday default, read whatever you like.")


def test_library_sentence_parser_splits_both_groups() -> None:
    parsed = parse_library_sentence(
        "For the everyday default, alpha loads on every turn and beta and "
        "gamma load on code files; open a reference here only when needed."
    )
    assert parsed == ({"alpha"}, {"beta", "gamma"})


def test_library_sentence_parser_reads_none_as_an_empty_group() -> None:
    parsed = parse_library_sentence(
        "For the everyday default, none loads on every turn and alpha and "
        "beta load on code files; open a reference here only when needed."
    )
    assert parsed == (set(), {"alpha", "beta"})


@pytest.mark.parametrize(("doc", "path"), CORPUS_PROSE_DOCS)
def test_corpus_prose_membership_matches_generated_trees(doc: str, path) -> None:
    members = parse_corpus_membership(path.read_text(encoding="utf-8"), doc)
    assert members == measured_always_on()


def test_corpus_prose_parser_rejects_divergent_membership() -> None:
    text = CORPUS_PROSE_DOCS[0][1].read_text(encoding="utf-8")
    shortened = text.replace("`universal`, `voice`", "`universal`", 1)
    with pytest.raises(ValueError, match="divergent membership"):
        parse_corpus_membership(shortened, "shortened")
