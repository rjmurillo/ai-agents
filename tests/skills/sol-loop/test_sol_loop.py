"""Tests for the sol-loop command layer.

No test reaches a model: the agent calls Sol, and these tests drive the
deterministic steps around that call through ``main(argv)``. Covers ordering
after the fresh critic, the 2-round cap read from the run log, recording a
reply with dropped findings, the Sol-only log, the unavailable WARN path,
ledger outcomes, totals, and the quiet skips. Git-backed staleness checks are
in ``test_sol_loop_staleness.py``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from _sol_loop_helpers import (
    SOL,
    _argv,
    _artifact_root,
    _gate,
    _log_dir,
    _logs,
    _out,
    _record,
    _reply,
    mod,
)

# Ordering after the fresh critic


def test_gate_refuses_without_critic_output(tmp_path, capsys):
    code = _gate(tmp_path, tmp_path / "missing.md")

    assert code == mod.EXIT_CONFIG
    assert "cannot read critic output" in capsys.readouterr().err
    assert not _log_dir(tmp_path).exists()


def test_gate_refuses_empty_critic_output(tmp_path):
    empty = tmp_path / "critic.md"
    empty.write_text("  \n", encoding="utf-8")

    assert _gate(tmp_path, empty) == mod.EXIT_CONFIG


def test_non_utf8_critic_output_is_config_error(tmp_path):
    binary = tmp_path / "critic.md"
    binary.write_bytes(b"\xff\xfe\x00bad")

    assert _gate(tmp_path, binary) == mod.EXIT_CONFIG


def test_record_also_requires_critic_output(tmp_path):
    assert _record(tmp_path, tmp_path / "missing.md", _reply(tmp_path)) == mod.EXIT_CONFIG
    assert not _log_dir(tmp_path).exists()


# Two-round cap read from the run log


def test_gate_reports_round_and_frozen_contract(tmp_path, critic_file, capsys):
    _gate(tmp_path, critic_file)
    first = _out(capsys)
    _record(tmp_path, critic_file, _reply(tmp_path))
    capsys.readouterr()

    _gate(tmp_path, critic_file)
    second = _out(capsys)

    assert (first["round"], first["frozen"]) == (1, False)
    assert (second["round"], second["frozen"]) == (2, True)


def test_third_round_escalates(tmp_path, critic_file, capsys):
    for _ in range(2):
        assert _record(tmp_path, critic_file, _reply(tmp_path)) == mod.EXIT_OK
    capsys.readouterr()

    gate_code = _gate(tmp_path, critic_file)
    gate_out = _out(capsys)
    record_code = _record(tmp_path, critic_file, _reply(tmp_path))

    assert (gate_code, gate_out["verdict"]) == (mod.EXIT_ESCALATE, "ESCALATE")
    assert record_code == mod.EXIT_ESCALATE
    statuses = [log["status"] for log in _logs(tmp_path)]
    assert (statuses.count("ok"), statuses.count("escalated")) == (2, 2)


def test_unavailable_and_skipped_runs_do_not_use_a_round(
    tmp_path, critic_file, monkeypatch, capsys
):
    mod.main(_argv("unavailable", tmp_path, critic_file, "--failure-class", "timeout"))
    monkeypatch.setenv("AI_AGENTS_SOL_PASS", "off")
    _gate(tmp_path, critic_file)
    monkeypatch.delenv("AI_AGENTS_SOL_PASS")
    capsys.readouterr()

    _gate(tmp_path, critic_file)

    assert _out(capsys)["round"] == 1


def test_round_count_without_branch_is_per_pr(tmp_path, critic_file, capsys):
    for _ in range(2):
        _record(tmp_path, critic_file, _reply(tmp_path), "--pr", "7")
    capsys.readouterr()

    assert _gate(tmp_path, critic_file, "--pr", "8") == mod.EXIT_OK


# Recording a round and the Sol-only log


def test_record_keeps_defects_drops_nits_and_missing_repro(tmp_path, critic_file, capsys):
    code = _record(tmp_path, critic_file, _reply(tmp_path), "--pr", "123")

    out = _out(capsys)
    log = _logs(tmp_path)[0]
    assert code == mod.EXIT_OK
    assert out["verdict"] == "CHANGES"
    assert [f["id"] for f in log["findings"]] == ["S1", "S2"]
    assert sorted(d["reason"] for d in log["dropped"]) == ["missing-repro", "nit"]
    assert log["counts"] == {"raw": 4, "kept": 2, "dropped": 2, "sol_only": 1, "overlap": 1}


def test_record_logs_sol_only_flags_and_ledger_fields(tmp_path, critic_file):
    _record(tmp_path, critic_file, _reply(tmp_path), "--pr", "123")

    log = _logs(tmp_path)[0]
    assert (log["status"], log["pr"], log["round"], log["model"]) == ("ok", "123", 1, SOL)
    assert (log["verdict"], log["author_family"], log["schema_version"]) == (
        "CHANGES",
        "anthropic",
        2,
    )
    assert {f["id"]: f["sol_only"] for f in log["findings"]} == {"S1": False, "S2": True}
    assert {f["outcome"] for f in log["findings"]} == {"open"}
    assert all(f["severity"] in ("blocker", "should") for f in log["findings"])
    assert len(log["critic_sha256"]) == 64


def test_approve_with_no_findings_still_logs(tmp_path, critic_file, capsys):
    _record(tmp_path, critic_file, _reply(tmp_path, "VERDICT: APPROVE\n"))

    assert _out(capsys)["verdict"] == "APPROVE"
    assert _logs(tmp_path)[0]["counts"]["kept"] == 0


def test_each_round_gets_its_own_log_file(tmp_path, critic_file):
    _record(tmp_path, critic_file, _reply(tmp_path), "--pr", "1")
    _record(tmp_path, critic_file, _reply(tmp_path), "--pr", "2")

    assert len(_logs(tmp_path)) == 2


def test_artifact_root_override_redirects_log(tmp_path, critic_file, monkeypatch):
    durable = tmp_path / "durable"
    monkeypatch.setenv("AI_AGENTS_ARTIFACT_ROOT", str(durable))
    argv = _argv("record", tmp_path, critic_file, "--reply", str(_reply(tmp_path)))
    argv.remove("--log-base")
    argv.remove(str(tmp_path))
    argv[argv.index("--repo") + 1] = str(tmp_path)

    mod.main(argv)

    assert len(list((durable / "metrics" / "sol-loop").glob("*.json"))) == 1


def test_log_write_failure_exits_2_after_printing_verdict(tmp_path, critic_file, capsys):
    _artifact_root(tmp_path).write_text("not a directory", encoding="utf-8")

    code = _record(tmp_path, critic_file, _reply(tmp_path))

    captured = capsys.readouterr()
    assert code == mod.EXIT_CONFIG
    assert json.loads(captured.out)["verdict"] == "CHANGES"
    assert "run log not written" in captured.err


# Unavailable path: WARN, never another model


@pytest.mark.parametrize("failure", mod.FAILURE_CLASSES)
def test_unavailable_warns_and_logs(tmp_path, critic_file, capsys, failure):
    code = mod.main(
        _argv("unavailable", tmp_path, critic_file, "--failure-class", failure, "--detail", "boom")
    )

    out = _out(capsys)
    assert code == mod.EXIT_UNAVAILABLE
    assert (out["verdict"], out["reason"]) == ("WARN", "review-model-unavailable")
    assert out["message"].startswith("Review model unavailable, deferring to human.")
    assert f"Model: {SOL} | Failure: {failure}" in out["message"]
    log = _logs(tmp_path)[0]
    assert (log["status"], log["failure_class"], log["model"]) == ("unavailable", failure, SOL)


def test_unavailable_rejects_unknown_failure_class(tmp_path, critic_file):
    with pytest.raises(SystemExit) as exc:
        mod.main(
            _argv("unavailable", tmp_path, critic_file, "--failure-class", "fell-back-to-claude")
        )
    assert exc.value.code == 2


@pytest.mark.parametrize("text", ["S1 [should] a.py:1 bug. Repro: x.\n", "Looks good to me.\n"])
def test_reply_without_verdict_takes_warn_path(tmp_path, critic_file, capsys, text):
    code = _record(tmp_path, critic_file, _reply(tmp_path, text))

    assert code == mod.EXIT_UNAVAILABLE
    assert _out(capsys)["reason"] == "review-model-unavailable"
    assert _logs(tmp_path)[0]["failure_class"] == "invalid-output"


def test_empty_reply_takes_warn_path(tmp_path, critic_file, capsys):
    code = _record(tmp_path, critic_file, _reply(tmp_path, "   \n"))

    assert code == mod.EXIT_UNAVAILABLE
    assert _logs(tmp_path)[0]["status"] == "unavailable"


def test_changes_verdict_with_no_finding_lines_takes_warn_path(tmp_path, critic_file, capsys):
    code = _record(
        tmp_path, critic_file, _reply(tmp_path, "VERDICT: CHANGES\n1) the cache is wrong\n")
    )

    assert code == mod.EXIT_UNAVAILABLE
    assert _out(capsys)["reason"] == "review-model-unavailable"
    assert _logs(tmp_path)[0]["failure_class"] == "invalid-output"


def test_unavailable_warn_prints_when_log_write_fails(tmp_path, critic_file, capsys):
    _artifact_root(tmp_path).write_text("not a directory", encoding="utf-8")

    code = mod.main(_argv("unavailable", tmp_path, critic_file, "--failure-class", "timeout"))

    out = _out(capsys)
    assert code == mod.EXIT_UNAVAILABLE
    assert (out["reason"], out["log"]) == ("review-model-unavailable", None)


# Quiet skips


def test_no_sol_route_skips_quietly_with_no_log(tmp_path, critic_file, capsys):
    code = mod.main(_argv("gate", tmp_path, critic_file, "--route", "none"))

    out = _out(capsys)
    assert code == mod.EXIT_OK
    assert (out["verdict"], out["log"]) == ("SKIPPED", None)
    assert "WARN" not in json.dumps(out)
    assert not _log_dir(tmp_path).exists()


def test_gpt_authored_change_is_skipped_as_same_family(tmp_path, critic_file, capsys):
    code = _gate(tmp_path, critic_file, author="openai")

    out = _out(capsys)
    assert code == mod.EXIT_OK
    assert out["verdict"] == "SKIPPED"
    assert "same-family" in out["reason"]
    assert _logs(tmp_path)[0]["skip_reason"].startswith("same-family")


def test_unknown_author_family_proceeds_with_flag(tmp_path, critic_file, capsys):
    _gate(tmp_path, critic_file, author="unknown")

    out = _out(capsys)
    assert out["verdict"] == "PROCEED"
    assert "unknown author family" in out["author_family_flag"]


# Ledger outcomes and totals


def test_outcome_updates_one_finding(tmp_path, critic_file, capsys):
    _record(tmp_path, critic_file, _reply(tmp_path))
    run = sorted(_log_dir(tmp_path).glob("*.json"))[0]
    capsys.readouterr()

    code = mod.main(
        ["outcome", "--run", str(run), "--id", "S2", "--outcome", "fixed", "--evidence", "abc123"]
    )

    log = json.loads(run.read_text(encoding="utf-8"))
    by_id = {f["id"]: f for f in log["findings"]}
    assert code == mod.EXIT_OK
    assert (by_id["S2"]["outcome"], by_id["S2"]["evidence"], by_id["S1"]["outcome"]) == (
        "fixed",
        "abc123",
        "open",
    )


def test_outcome_with_unknown_id_is_config_error(tmp_path, critic_file):
    _record(tmp_path, critic_file, _reply(tmp_path))
    run = sorted(_log_dir(tmp_path).glob("*.json"))[0]

    assert (
        mod.main(["outcome", "--run", str(run), "--id", "S9", "--outcome", "fixed"])
        == mod.EXIT_CONFIG
    )


def test_outcome_with_unreadable_run_is_config_error(tmp_path):
    assert (
        mod.main(
            ["outcome", "--run", str(tmp_path / "nope.json"), "--id", "S1", "--outcome", "fixed"]
        )
        == 2
    )


def test_summarize_totals_runs_and_sol_only_outcomes(tmp_path, critic_file, capsys):
    _record(tmp_path, critic_file, _reply(tmp_path))
    run = sorted(_log_dir(tmp_path).glob("*.json"))[0]
    mod.main(["outcome", "--run", str(run), "--id", "S2", "--outcome", "fixed"])
    mod.main(_argv("unavailable", tmp_path, critic_file, "--failure-class", "timeout"))
    (_log_dir(tmp_path) / "broken.json").write_text("{", encoding="utf-8")
    capsys.readouterr()

    code = mod.main(["summarize", "--repo", str(tmp_path), "--log-base", str(tmp_path)])

    totals = _out(capsys)
    assert code == mod.EXIT_OK
    assert (totals["runs"], totals["ok"], totals["unavailable"], totals["unreadable"]) == (
        2,
        1,
        1,
        1,
    )
    assert (totals["sol_only"], totals["overlap"]) == (1, 1)
    assert totals["sol_only_outcomes"] == {"fixed": 1, "disagree": 0, "declined": 0, "open": 0}


def test_summarize_reads_the_committed_first_run():
    root = Path(__file__).resolve().parents[3]
    totals = mod.summarize(root / ".project-toolkit" / "metrics" / "sol-loop")

    assert totals["unreadable"] == 0
    assert totals["runs"] >= 1


# Skips come before validation; the WARN does not depend on the critic file


def test_same_family_skip_needs_no_critic_file(tmp_path, capsys):
    code = mod.main(
        _argv("gate", tmp_path, tmp_path / "missing.md", "--route", "t3", author="openai")
    )

    assert code == mod.EXIT_OK
    assert _out(capsys)["verdict"] == "SKIPPED"


def test_off_switch_skips_even_with_a_bad_model(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("AI_AGENTS_SOL_PASS", "off")
    argv = _argv("gate", tmp_path, tmp_path / "missing.md", "--route", "t3")
    argv[argv.index("--model") + 1] = "claude-opus-5-5"

    code = mod.main(argv)

    assert code == mod.EXIT_OK
    assert _out(capsys)["verdict"] == "SKIPPED"


def test_unavailable_warns_even_when_critic_file_is_unreadable(tmp_path, capsys):
    argv = _argv("unavailable", tmp_path, tmp_path / "missing.md", "--failure-class", "timeout")

    code = mod.main(argv)

    assert code == mod.EXIT_UNAVAILABLE
    assert _out(capsys)["reason"] == "review-model-unavailable"
    assert "cannot read critic output" in _logs(tmp_path)[0]["critic_error"]
