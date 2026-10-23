"""Claude rows score under Amendment 3, per harness, never pooled (issue #5426)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests.eval._routing_verdicts_test_support import (
    ALL_IDS,
    CLASSES,
    ORDINARY,
    arm_rows,
    cli,
    fail_all,
    full_dataset,
    row,
    v,
)


def as_harness(rows: list[dict[str, Any]], name: str) -> list[dict[str, Any]]:
    """The same rows relabeled to another harness (NOT_RUN rows carry a bare name)."""
    relabeled: list[dict[str, Any]] = []
    for item in rows:
        copy = json.loads(json.dumps(item))
        if isinstance(copy["harness"], dict):
            copy["harness"]["name"] = name
        else:
            copy["harness"] = name
        relabeled.append(copy)
    return relabeled


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return path


def _run_cli(capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, dict[str, Any]]:
    code = cli.main(list(args))
    out = capsys.readouterr().out
    return code, json.loads(out) if out.strip() else {}


# --- library: one verdict, one harness -----------------------------------------------


def test_claude_rows_parse_and_carry_their_harness() -> None:
    runs = v.parse_runs(as_harness(full_dataset(), "claude"), CLASSES)

    assert runs and {run.harness for run in runs} == {"claude"}


def test_a_run_defaults_to_codex_so_existing_callers_are_unchanged() -> None:
    assert {run.harness for run in v.parse_runs(full_dataset(), CLASSES)} == {"codex"}


def test_one_verdict_refuses_rows_from_two_harnesses() -> None:
    mixed = full_dataset() + as_harness(full_dataset(), "claude")

    with pytest.raises(v.VerdictInputError, match=r"more than one harness.*\['claude', 'codex'\]"):
        v.parse_runs(mixed, CLASSES)


def test_the_scorer_refuses_claude_runs_in_a_codex_verdict_and_the_reverse() -> None:
    claude_runs = v.parse_runs(as_harness(full_dataset(), "claude"), CLASSES)
    codex_runs = v.parse_runs(full_dataset(), CLASSES)

    with pytest.raises(v.VerdictInputError, match=r"cannot score \['claude'\].*'codex' verdict"):
        v.score(claude_runs, CLASSES)
    with pytest.raises(v.VerdictInputError, match=r"cannot score \['codex'\].*'claude' verdict"):
        v.score(codex_runs, CLASSES, harness="claude")


def test_a_hand_pooled_run_list_is_refused_by_the_scorer() -> None:
    pooled = v.parse_runs(full_dataset(), CLASSES) + v.parse_runs(
        as_harness(full_dataset(), "claude"), CLASSES
    )

    with pytest.raises(v.VerdictInputError, match="never pooled"):
        v.score(pooled, CLASSES)


def test_claude_scores_under_amendment_3_with_the_same_rules_and_its_role_models() -> None:
    codex = v.score(v.parse_runs(full_dataset(), CLASSES), CLASSES)
    claude = v.score(
        v.parse_runs(as_harness(full_dataset(), "claude"), CLASSES), CLASSES, harness="claude"
    )

    assert claude["decision_rule"] == "predictions-v1 amendment 3"
    assert codex["decision_rule"] == "predictions-v1 amendment 2"
    assert claude["role_models"] == {
        "sol": "claude-opus-5-5",
        "luna": "claude-haiku-5-5",
        "terra": "claude-sonnet-5-5",
    }
    assert claude["hypotheses"] == codex["hypotheses"] and claude["decision"] == codex["decision"]
    assert claude["predictions_version"] == codex["predictions_version"] == "predictions-v1"


def test_interpretation_i11_states_per_harness_scoring() -> None:
    i11 = next(i for i in v.INTERPRETATIONS if i["id"] == "I11")

    assert "Amendment 3" in str(i11["reading"]) and "never pooled" in str(i11["reading"])
    assert "Only Codex rows are scorable" not in str(i11["reading"])


def test_the_claude_token_convention_is_listed() -> None:
    assert any(
        i["id"] == "I14" and "cache_creation_input_tokens" in str(i["reading"])
        for i in v.INTERPRETATIONS
    )


# --- CLI: keyed by harness -------------------------------------------------------------


def test_the_report_is_keyed_by_harness_with_each_harness_decision_and_floor(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rows = full_dataset() + as_harness(full_dataset(), "claude")
    results = write_jsonl(tmp_path / "rows.jsonl", rows)

    code, report = _run_cli(capsys, "--results", str(results))

    assert code == 0 and report["pooled_across_harnesses"] is False
    assert list(report["harnesses"]) == ["claude", "codex"]
    for name, block in report["harnesses"].items():
        assert block["harness"] == name and set(block["hypotheses"]) == {"H1", "H2", "H3", "H4"}
        assert {"decision", "base_decision", "decision_floor", "decision_rule"} <= set(block)
        assert "interpretations" not in block
    assert report["interpretations"]


def test_each_harness_is_scored_on_its_own_rows_and_never_pooled(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    thin = [r for r in as_harness(full_dataset(), "claude") if r["repetition"] == 1]
    results = write_jsonl(tmp_path / "rows.jsonl", full_dataset() + thin)

    code, report = _run_cli(capsys, "--results", str(results))

    codex, claude = report["harnesses"]["codex"], report["harnesses"]["claude"]
    assert code == 0
    assert codex["rows_scored"] == 108 and claude["rows_scored"] == 36
    assert codex["decision"] == v.DECISION_KEEP and claude["decision"] == v.INSUFFICIENT
    assert claude["decision_floor"]["arms_short"]


def test_the_same_scenario_arm_and_repetition_on_two_harnesses_is_not_a_duplicate(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rows = [row(ORDINARY[0], "A", 1)] + as_harness([row(ORDINARY[0], "A", 1)], "claude")

    code, report = _run_cli(capsys, "--results", str(write_jsonl(tmp_path / "r.jsonl", rows)))

    assert code == 0 and set(report["harnesses"]) == {"codex", "claude"}


def test_a_duplicate_within_claude_is_still_refused(tmp_path: Path) -> None:
    twice = as_harness([row(ORDINARY[0], "A", 1), row(ORDINARY[0], "A", 1)], "claude")

    assert cli.main(["--results", str(write_jsonl(tmp_path / "r.jsonl", twice))]) == 2


def test_a_claude_only_file_scores_without_a_codex_block(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    results = write_jsonl(tmp_path / "r.jsonl", as_harness(full_dataset(), "claude"))

    code, report = _run_cli(capsys, "--results", str(results))

    assert code == 0 and list(report["harnesses"]) == ["claude"]


def test_a_harness_that_is_neither_codex_nor_claude_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    results = write_jsonl(tmp_path / "r.jsonl", as_harness(full_dataset(), "copilot"))

    assert cli.main(["--results", str(results)]) == 2
    assert "not scorable" in capsys.readouterr().err


def test_a_harness_with_only_failures_is_reported_insufficient_beside_a_scored_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    failed = as_harness([row(ORDINARY[0], arm, 1, "HARNESS_FAILED") for arm in "ABCDEF"], "claude")
    results = write_jsonl(tmp_path / "r.jsonl", full_dataset() + failed)

    code, report = _run_cli(capsys, "--results", str(results))

    claude = report["harnesses"]["claude"]
    assert code == 0 and claude["decision"] == v.INSUFFICIENT
    assert {h["status"] for h in claude["hypotheses"].values()} == {v.INSUFFICIENT}


def test_exit_1_when_no_harness_has_a_scorable_row(tmp_path: Path) -> None:
    rows = [row(ORDINARY[0], "A", 1, "NOT_RUN")] + as_harness(
        [row(ORDINARY[0], "A", 1, "HARNESS_FAILED")], "claude"
    )

    assert cli.main(["--results", str(write_jsonl(tmp_path / "r.jsonl", rows))]) == 1


def test_the_pre_amendment_guard_still_refuses_old_codex_with_new_claude(tmp_path: Path) -> None:
    old = write_jsonl(tmp_path / v.SUPERSEDED_DIR / "old.jsonl", full_dataset())
    new = write_jsonl(
        tmp_path / "results-2026-11-01" / "new.jsonl", as_harness(full_dataset(), "claude")
    )

    assert cli.main(["--results", str(old), str(new)]) == 2


def test_a_claude_arm_that_never_accepts_is_scored_on_claude_alone(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    claude = as_harness(full_dataset(C=arm_rows("C", ALL_IDS, fail_all)), "claude")
    results = write_jsonl(tmp_path / "r.jsonl", full_dataset() + claude)

    code, report = _run_cli(capsys, "--results", str(results))

    def c_ordinary(name: str) -> float:
        tables = report["harnesses"][name]["tables"]
        return next(
            t["acceptance_rate"]
            for t in tables
            if t["arm"] == "C" and t["class"] == v.CLASS_ORDINARY
        )

    assert code == 0 and c_ordinary("codex") == 1.0 and c_ordinary("claude") == 0.0
