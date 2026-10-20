"""Tests for the routing verdict CLI and the Amendment 1 pooling guard (issue #5426)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests.eval._routing_verdicts_test_support import (
    ORDINARY,
    REAL_RESULTS,
    cli,
    full_dataset,
    row,
    v,
)

# ----------------------------------------------------------------------------- CLI


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return path


def run_cli(*args: str) -> int:
    return cli.main(list(args))


def test_cli_scores_and_writes_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    results = write_jsonl(tmp_path / "run" / "rows.jsonl", full_dataset())
    out = tmp_path / "report.json"
    assert run_cli("--results", str(results), "--output", str(out)) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed == json.loads(out.read_text(encoding="utf-8"))
    assert printed["decision"] == v.DECISION_KEEP


def test_cli_accepts_several_result_files(tmp_path: Path) -> None:
    rows = full_dataset()
    first = write_jsonl(tmp_path / "a.jsonl", rows[:100])
    second = write_jsonl(tmp_path / "b.jsonl", rows[100:])
    assert run_cli("--results", str(first), str(second)) == 0


def test_cli_exit_2_without_arguments() -> None:
    assert run_cli() == 2


def test_cli_exit_2_on_missing_file(tmp_path: Path) -> None:
    assert run_cli("--results", str(tmp_path / "nope.jsonl")) == 2


def test_cli_exit_2_on_invalid_json(tmp_path: Path) -> None:
    bad = tmp_path / "bad.jsonl"
    bad.write_text("{not json\n", encoding="utf-8")
    assert run_cli("--results", str(bad)) == 2


def test_cli_exit_2_on_non_object_row(tmp_path: Path) -> None:
    bad = tmp_path / "bad.jsonl"
    bad.write_text("[1]\n", encoding="utf-8")
    assert run_cli("--results", str(bad)) == 2


def test_cli_exit_2_on_unknown_scenario(tmp_path: Path) -> None:
    results = write_jsonl(tmp_path / "r.jsonl", [row("RB-99", "A", 1)])
    assert run_cli("--results", str(results)) == 2


def test_cli_exit_2_on_bad_corpus(tmp_path: Path) -> None:
    results = write_jsonl(tmp_path / "r.jsonl", full_dataset())
    assert run_cli("--results", str(results), "--corpus", str(tmp_path / "missing")) == 2


def test_cli_exit_1_when_every_row_is_not_run(tmp_path: Path) -> None:
    results = write_jsonl(tmp_path / "r.jsonl", [row(ORDINARY[0], "A", 1, "NOT_RUN")])
    assert run_cli("--results", str(results)) == 1


def test_cli_blank_lines_are_skipped(tmp_path: Path) -> None:
    path = tmp_path / "r.jsonl"
    path.write_text("\n" + json.dumps(row(ORDINARY[0], "A", 1)) + "\n\n", encoding="utf-8")
    assert run_cli("--results", str(path)) == 0


# ---------------------------------------------------------- Amendment 1 pooling guard


def test_pooling_guard_refuses_mixed_old_and_new(tmp_path: Path) -> None:
    old = write_jsonl(tmp_path / v.SUPERSEDED_DIR / "old.jsonl", [row(ORDINARY[0], "A", 1)])
    new = write_jsonl(tmp_path / "results-2026-11-01" / "new.jsonl", [row(ORDINARY[0], "A", 2)])
    with pytest.raises(v.VerdictInputError, match="Amendment 1"):
        cli.check_pooling([old, new])
    assert run_cli("--results", str(old), str(new)) == 2


def test_pooling_guard_allows_new_runs_only(tmp_path: Path) -> None:
    new = write_jsonl(tmp_path / "results-2026-11-01" / "new.jsonl", [row(ORDINARY[0], "A", 1)])
    assert cli.check_pooling([new]) is False


def test_superseded_alone_is_scored_but_every_verdict_is_insufficient(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    old = write_jsonl(tmp_path / v.SUPERSEDED_DIR / "old.jsonl", full_dataset())
    assert run_cli("--results", str(old)) == 0
    printed = json.loads(capsys.readouterr().out)
    assert {h["status"] for h in printed["hypotheses"].values()} == {v.INSUFFICIENT}
    assert printed["decision"] == v.INSUFFICIENT
    assert printed["decision_floor"]["pre_amendment_inputs"] is True


def test_real_results_2026_10_03_are_insufficient_for_all_four(
    capsys: pytest.CaptureFixture[str],
) -> None:
    files = sorted(REAL_RESULTS.glob("*.jsonl"))
    assert len(files) == 3
    assert run_cli("--results", *map(str, files)) == 0
    printed = json.loads(capsys.readouterr().out)
    assert {k: h["status"] for k, h in printed["hypotheses"].items()} == dict.fromkeys(
        ("H1", "H2", "H3", "H4"), v.INSUFFICIENT
    )
    assert printed["decision"] == v.INSUFFICIENT
    assert printed["rows_scored"] == 36
    assert printed["rows_not_run"] == 0


def test_real_results_cannot_pool_with_a_later_file(tmp_path: Path) -> None:
    later = write_jsonl(tmp_path / "later.jsonl", [row(ORDINARY[0], "A", 2)])
    first = next(iter(sorted(REAL_RESULTS.glob("*.jsonl"))))
    assert run_cli("--results", str(first), str(later)) == 2
