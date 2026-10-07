"""Hardening tests for the NL structural debt ratchet (issue #5397).

Split from test_check_nl_structural_debt.py to keep each file under the taste
file-size ceiling.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.validation.test_check_nl_structural_debt import (
    _POLICY,
    _baseline,
    _tree,
    _write,
    card,
    gate,
)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _tree(tmp_path)
    _write(tmp_path, "templates/rules/a.md", "Alpha intro.\n" + _POLICY)
    _baseline(tmp_path)
    return tmp_path


def test_update_baseline_refuses_to_write_from_another_checkout(
    repo: Path,
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (repo / gate.BASELINE_PATH).unlink()
    monkeypatch.chdir(tmp_path_factory.mktemp("elsewhere"))
    assert gate.run(repo, update=True) == 2
    assert "Refusing to write the baseline" in capsys.readouterr().err
    assert not (repo / gate.BASELINE_PATH).exists()


def test_a_repeated_stale_claim_in_one_file_is_new_debt(repo: Path) -> None:
    claim = "Run the three filters: lint, format, types, tests."
    _write(repo, "templates/rules/b.md", claim)
    first = gate.measure(repo)["cardinality"]
    assert list(first) == [f"templates/rules/b.md::{claim.lower()}"]
    _baseline(repo, count=first)
    assert gate.run(repo, update=False) == 0
    _write(repo, "templates/rules/b.md", f"{claim}\n\n{claim}")
    keys = list(gate.measure(repo)["cardinality"])
    assert keys == [
        f"templates/rules/b.md::{claim.lower()}",
        f"templates/rules/b.md::{claim.lower()}#2",
    ]
    assert gate.run(repo, update=False) == 1


def test_an_authored_symlink_that_leaves_the_checkout_is_a_config_error(
    repo: Path, tmp_path_factory: pytest.TempPathFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    outside = tmp_path_factory.mktemp("outside") / "secret.md"
    outside.write_text("Host file that must never be read by the gate.\n", encoding="utf-8")
    (repo / "templates/rules/escape.md").symlink_to(outside)
    assert gate.run(repo, update=False) == 2
    assert "resolves outside the repository" in capsys.readouterr().err


def test_a_wrapped_list_item_is_one_item_not_the_end_of_the_list() -> None:
    text = (
        "Run the four filters:\n\n"
        "- lint, which also\n  covers imports\n"
        "- format\n- types\n- tests\n"
    )
    assert card.derived_count_claims(text) == []


def test_a_wrapped_list_with_a_wrong_count_is_still_flagged() -> None:
    text = (
        "Run the three filters:\n\n"
        "- lint, which also\n  covers imports\n"
        "- format\n- types\n- tests\n"
    )
    assert [(c.stated, c.actual) for c in card.derived_count_claims(text)] == [(3, 4)]


def test_an_unindented_line_ends_the_list() -> None:
    text = "Run the three filters:\n\n- lint\n- format\n- types\nPlain prose ends it.\n- extra\n"
    assert card.derived_count_claims(text) == []


def test_a_position_label_digit_is_not_a_count() -> None:
    text = "Separate what you found in Phase 1 into two buckets:\n\n- Durable\n- Dated\n- Other\n"
    assert card.derived_count_claims(text) == []


def test_skill_resources_are_authored_and_scanned_recursively(repo: Path) -> None:
    _write(repo, ".claude/skills/solo/SKILL.md", "Solo skill.\n")
    _write(repo, ".claude/skills/solo/resources/deep/r.md", "Resource.\n" + _POLICY)
    paths = {p.relative_to(repo).as_posix() for p in gate.authored_files(repo)}
    assert ".claude/skills/solo/resources/deep/r.md" in paths
    assert any(
        ".claude/skills/solo/resources/deep/r.md" in key
        for key in gate.measure(repo)["duplicate_blocks"]
    )


def test_unclosed_frontmatter_is_scanned_whole() -> None:
    body = "\n".join(f"Policy line number {n} that is long enough to count." for n in range(3))
    assert gate._body_lines("---\n" + body) == gate._body_lines(body)


def test_stale_claim_key_survives_a_reflow_only_edit(repo: Path) -> None:
    _write(repo, "templates/rules/b.md", "Run the three filters: lint, format, types, tests.")
    first = list(gate.measure(repo)["cardinality"])
    _write(repo, "templates/rules/b.md", "Run  the three  Filters:   lint, format, types, tests.")
    assert list(gate.measure(repo)["cardinality"]) == first


def test_a_subtotal_decomposition_is_not_judged() -> None:
    text = "There are 30 candidates: 24 cached workflows and 6 uncached ones.\n"
    assert card.derived_count_claims(text) == []


def test_a_partial_example_list_is_not_judged() -> None:
    text = "Read 14 business books (customer discovery, pricing, sales, hiring, ops, legal).\n"
    assert card.derived_count_claims(text) == []
