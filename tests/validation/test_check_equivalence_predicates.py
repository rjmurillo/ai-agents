"""The equivalence predicate gate fails closed on every shape of bad table.

ADR-107 M1, issue #5686. Each failure path is driven through ``main`` or the
typed entry point and asserted on its exit code or state, because a gate that
prints but exits 0 is the silent pass this table exists to prevent.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from scripts.validation.check_equivalence_predicates import (
    BASELINE_PATH,
    BUILD_ALL_PATH,
    COLUMNS,
    EXIT_CONFIG,
    EXIT_LOGIC,
    EXIT_OK,
    GOVERNANCE_PATH,
    REASON_FINDINGS,
    REASON_RATCHET,
    REASON_UNREADABLE,
    ConfigError,
    generator_names,
    main,
    parse_table,
    validate_equivalence_predicates,
)
from scripts.validation.evidence import EvidenceState

REPO_ROOT = Path(__file__).resolve().parents[2]
TODAY = date(2026, 10, 13)
GATE = "tools/check.py"
BUILD_ALL = 'GENERATORS = [\n    ("alpha", _build_alpha),\n    ("beta", _build_beta),\n]\n'


def _row(
    name: str,
    predicate: str = "derived",
    gate: str | None = None,
    issue: str = "-",
    expiry: str = "-",
) -> str:
    gate_cell = f"`{GATE}` with --check" if gate is None else gate
    return f"| `{name}` | `trees/{name}/` | `{predicate}` | {gate_cell} | {issue} | {expiry} |"


def _table(rows: list[str], columns: tuple[str, ...] = COLUMNS) -> str:
    header = "| " + " | ".join(columns) + " |"
    divider = "|" + "|".join("---" for _ in columns) + "|"
    body = "\n".join(rows)
    return (
        f"# Doc\n\n## Equivalence predicates\n\nProse.\n\n{header}\n{divider}\n{body}\n\n## Next\n"
    )


def _repo(
    tmp_path: Path,
    rows: list[str] | None = None,
    *,
    none_rows: int = 0,
    classes: int = 0,
    build_all: str = BUILD_ALL,
) -> Path:
    rows = rows if rows is not None else [_row("alpha"), _row("beta")]
    (tmp_path / GOVERNANCE_PATH).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / GOVERNANCE_PATH).write_text(_table(rows), encoding="utf-8")
    (tmp_path / BUILD_ALL_PATH).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / BUILD_ALL_PATH).write_text(build_all, encoding="utf-8")
    (tmp_path / BASELINE_PATH).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / BASELINE_PATH).write_text(
        json.dumps({"none_rows": none_rows, "classes": classes}), encoding="utf-8"
    )
    (tmp_path / GATE).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / GATE).write_text("print('gate')\n", encoding="utf-8")
    return tmp_path


def _detail(root: Path) -> str:
    return validate_equivalence_predicates(root, TODAY).detail


class TestValidTable:
    def test_a_valid_table_passes(self, tmp_path: Path) -> None:
        root = _repo(tmp_path, classes=2)

        outcome = validate_equivalence_predicates(root, TODAY)

        assert outcome.state is EvidenceState.PASS
        assert outcome.examined == 2

    def test_main_returns_ok_on_a_valid_table(self, tmp_path: Path) -> None:
        root = _repo(tmp_path)

        assert main(["--repo-root", str(root), "--today", "2026-10-13"]) == EXIT_OK

    def test_a_baselined_none_row_with_issue_and_live_expiry_passes(self, tmp_path: Path) -> None:
        rows = [_row("alpha"), _row("beta", "none", issue="#5688", expiry="2026-12-31")]
        root = _repo(tmp_path, rows, none_rows=1)

        assert validate_equivalence_predicates(root, TODAY).state is EvidenceState.PASS

    def test_a_normalized_row_passes(self, tmp_path: Path) -> None:
        root = _repo(tmp_path, [_row("alpha"), _row("beta", "normalized")])

        assert validate_equivalence_predicates(root, TODAY).state is EvidenceState.PASS

    def test_a_none_row_expiring_today_is_still_live(self, tmp_path: Path) -> None:
        rows = [_row("alpha"), _row("beta", "none", issue="#1", expiry="2026-10-13")]
        root = _repo(tmp_path, rows, none_rows=1)

        assert validate_equivalence_predicates(root, TODAY).state is EvidenceState.PASS


class TestPredicateValue:
    @pytest.mark.parametrize("value", ["byte", "Derived", "", "partial"])
    def test_an_unknown_value_fails(self, tmp_path: Path, value: str) -> None:
        root = _repo(tmp_path, [_row("alpha"), _row("beta", value)])

        outcome = validate_equivalence_predicates(root, TODAY)

        assert outcome.state is EvidenceState.FAIL
        assert outcome.reason == REASON_FINDINGS
        assert "not a legal predicate" in outcome.detail

    def test_main_exits_one_on_an_unknown_value(self, tmp_path: Path) -> None:
        root = _repo(tmp_path, [_row("alpha"), _row("beta", "byte")])

        assert main(["--repo-root", str(root), "--today", "2026-10-13"]) == EXIT_LOGIC


class TestNoneRows:
    def test_a_none_row_without_an_issue_fails(self, tmp_path: Path) -> None:
        rows = [_row("alpha"), _row("beta", "none", expiry="2026-12-31")]
        root = _repo(tmp_path, rows, none_rows=1)

        assert "cites no owning issue" in _detail(root)

    def test_a_none_row_with_a_malformed_issue_fails(self, tmp_path: Path) -> None:
        rows = [_row("alpha"), _row("beta", "none", issue="5688", expiry="2026-12-31")]
        root = _repo(tmp_path, rows, none_rows=1)

        assert "cites no owning issue" in _detail(root)

    def test_a_none_row_without_an_expiry_fails(self, tmp_path: Path) -> None:
        rows = [_row("alpha"), _row("beta", "none", issue="#5688")]
        root = _repo(tmp_path, rows, none_rows=1)

        assert "no ISO expiry date" in _detail(root)

    def test_a_none_row_with_a_non_date_expiry_fails(self, tmp_path: Path) -> None:
        rows = [_row("alpha"), _row("beta", "none", issue="#5688", expiry="soon")]
        root = _repo(tmp_path, rows, none_rows=1)

        assert "no ISO expiry date" in _detail(root)

    def test_a_lapsed_none_row_fails_and_is_not_renewed(self, tmp_path: Path) -> None:
        rows = [_row("alpha"), _row("beta", "none", issue="#5688", expiry="2026-10-12")]
        root = _repo(tmp_path, rows, none_rows=1)

        outcome = validate_equivalence_predicates(root, TODAY)

        assert outcome.state is EvidenceState.FAIL
        assert "expired 2026-10-12" in outcome.detail


class TestGateCell:
    def test_a_gate_naming_no_script_fails(self, tmp_path: Path) -> None:
        root = _repo(tmp_path, [_row("alpha"), _row("beta", gate="the build")])

        assert "existing script" in _detail(root)

    def test_a_gate_naming_a_missing_script_fails(self, tmp_path: Path) -> None:
        root = _repo(tmp_path, [_row("alpha"), _row("beta", gate="`tools/ghost.py`")])

        assert "existing script" in _detail(root)


class TestCoverage:
    def test_a_generator_without_a_row_fails(self, tmp_path: Path) -> None:
        root = _repo(tmp_path, [_row("alpha")])

        assert "GENERATORS entry 'beta' has no row" in _detail(root)

    def test_a_duplicate_class_fails(self, tmp_path: Path) -> None:
        root = _repo(tmp_path, [_row("alpha"), _row("beta"), _row("alpha")])

        assert "declared twice" in _detail(root)

    def test_an_extra_class_beyond_generators_is_allowed(self, tmp_path: Path) -> None:
        root = _repo(tmp_path, [_row("alpha"), _row("beta"), _row("trees")], classes=3)

        assert validate_equivalence_predicates(root, TODAY).state is EvidenceState.PASS


class TestRatchet:
    def test_a_new_none_row_over_the_baseline_fails(self, tmp_path: Path) -> None:
        rows = [_row("alpha"), _row("beta", "none", issue="#1", expiry="2026-12-31")]
        root = _repo(tmp_path, rows, none_rows=0)

        outcome = validate_equivalence_predicates(root, TODAY)

        assert outcome.state is EvidenceState.FAIL
        assert outcome.reason == REASON_RATCHET
        assert "closes none to new classes" in outcome.detail

    def test_slack_below_the_baseline_fails_until_it_is_lowered(self, tmp_path: Path) -> None:
        root = _repo(tmp_path, none_rows=1)

        outcome = validate_equivalence_predicates(root, TODAY)

        assert outcome.reason == REASON_RATCHET
        assert "lower none_rows" in outcome.detail

    def test_deleting_a_class_row_fails(self, tmp_path: Path) -> None:
        root = _repo(tmp_path, [_row("alpha"), _row("beta")], classes=3)

        assert "cannot be deleted" in _detail(root)

    def test_main_exits_one_on_a_ratchet_breach(self, tmp_path: Path) -> None:
        root = _repo(tmp_path, none_rows=1)

        assert main(["--repo-root", str(root), "--today", "2026-10-13"]) == EXIT_LOGIC


class TestFailClosed:
    def test_a_missing_table_file_exits_two(self, tmp_path: Path) -> None:
        root = _repo(tmp_path)
        (root / GOVERNANCE_PATH).unlink()

        assert main(["--repo-root", str(root)]) == EXIT_CONFIG

    def test_a_missing_heading_is_unreadable(self, tmp_path: Path) -> None:
        root = _repo(tmp_path)
        (root / GOVERNANCE_PATH).write_text("# Doc\n\nNo section.\n", encoding="utf-8")

        outcome = validate_equivalence_predicates(root, TODAY)

        assert outcome.reason == REASON_UNREADABLE
        assert "heading" in outcome.detail

    def test_a_table_with_no_data_rows_is_unreadable(self, tmp_path: Path) -> None:
        root = _repo(tmp_path, [])

        assert validate_equivalence_predicates(root, TODAY).reason == REASON_UNREADABLE

    def test_wrong_columns_are_unreadable(self, tmp_path: Path) -> None:
        root = _repo(tmp_path)
        text = _table([_row("alpha")], columns=("Class", "Predicate"))
        (root / GOVERNANCE_PATH).write_text(text, encoding="utf-8")

        assert "do not match" in _detail(root)

    def test_a_short_row_is_unreadable(self, tmp_path: Path) -> None:
        root = _repo(tmp_path, ["| `alpha` | `derived` |"])

        assert "cells, expected 6" in _detail(root)

    def test_a_missing_baseline_exits_two(self, tmp_path: Path) -> None:
        root = _repo(tmp_path)
        (root / BASELINE_PATH).unlink()

        assert main(["--repo-root", str(root)]) == EXIT_CONFIG

    @pytest.mark.parametrize(
        "payload",
        [
            "not json",
            "[]",
            '{"none_rows": "0", "classes": 1}',
            '{"none_rows": -1, "classes": 1}',
            '{"none_rows": true, "classes": 1}',
            '{"none_rows": 0}',
        ],
    )
    def test_a_malformed_baseline_exits_two(self, tmp_path: Path, payload: str) -> None:
        root = _repo(tmp_path)
        (root / BASELINE_PATH).write_text(payload, encoding="utf-8")

        assert main(["--repo-root", str(root)]) == EXIT_CONFIG

    def test_a_missing_generators_list_exits_two(self, tmp_path: Path) -> None:
        root = _repo(tmp_path, build_all="OTHER = []\n")

        assert main(["--repo-root", str(root)]) == EXIT_CONFIG

    def test_an_unparseable_build_all_exits_two(self, tmp_path: Path) -> None:
        root = _repo(tmp_path, build_all="GENERATORS = [\n")

        assert main(["--repo-root", str(root)]) == EXIT_CONFIG

    def test_an_empty_generators_list_exits_two(self, tmp_path: Path) -> None:
        root = _repo(tmp_path, build_all="GENERATORS: list = []\n", classes=2)

        assert main(["--repo-root", str(root)]) == EXIT_CONFIG


class TestParsers:
    def test_generator_names_reads_annotated_assignments(self) -> None:
        source = 'GENERATORS: list[tuple[str, object]] = [("a", f), ("b", g)]\n'

        assert generator_names(source) == ["a", "b"]

    def test_generator_names_ignores_non_literal_entries(self) -> None:
        assert generator_names('GENERATORS = [(NAME, f), ("b", g), ("c",)]\n') == ["b", "c"]

    def test_parse_table_stops_at_the_next_heading(self) -> None:
        text = _table([_row("alpha")]) + "\n| `late` | x | y | z | - | - |\n"

        assert [row.name for row in parse_table(text)] == ["alpha"]

    def test_parse_table_raises_on_a_missing_section(self) -> None:
        with pytest.raises(ConfigError):
            parse_table("# nothing\n")


class TestLiveRepository:
    def test_the_committed_table_passes(self) -> None:
        outcome = validate_equivalence_predicates(REPO_ROOT)

        assert outcome.state is EvidenceState.PASS, outcome.detail

    def test_the_committed_table_has_no_none_rows(self) -> None:
        rows = parse_table((REPO_ROOT / GOVERNANCE_PATH).read_text(encoding="utf-8"))

        assert [row.name for row in rows if row.predicate == "none"] == []

    def test_the_committed_baseline_matches_the_table(self) -> None:
        rows = parse_table((REPO_ROOT / GOVERNANCE_PATH).read_text(encoding="utf-8"))
        baseline = json.loads((REPO_ROOT / BASELINE_PATH).read_text(encoding="utf-8"))

        assert baseline == {"none_rows": 0, "classes": len(rows)}
