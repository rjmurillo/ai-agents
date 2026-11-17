"""Tests for the sol-loop command layer.

No test reaches a model: the agent calls Sol, and these tests drive the
deterministic steps around that call through ``main(argv)``. Covers ordering
after the fresh critic (including a stale critic file), the 2-round cap read
from the run log, recording a reply with dropped findings, the Sol-only log,
the unavailable WARN path, ledger outcomes, totals, and the quiet skips.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script

mod = import_skill_script(
    ".claude/skills/sol-loop/scripts/sol_loop.py", module_name="sol_loop_under_test"
)

CRITIC_TEXT = (
    "## Critical Findings\n1. `src/app/a.py:10` drops the error.\n\nVerdict: NEEDS_REVISION\n"
)
SOL = "gpt-6.1-sol"
REPLY = (
    "VERDICT: CHANGES\n"
    "S1 [should] src/app/a.py:12 swallows the error. "
    "Repro: call f(None) and no error is raised. Fix: re-raise.\n"
    "S2 [blocker] src/app/b.py:5 KeyError on empty input. "
    "Repro: pytest tests/test_b.py::test_empty. Fix: guard.\n"
    "S3 [nit] src/app/b.py:9 rename x. Repro: n/a. Fix: rename.\n"
    "S4 [should] src/app/c.py:3 wrong default. Fix: use 0.\n"
)
_needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git CLI not installed")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in ("AI_AGENTS_ARTIFACT_ROOT", "AI_AGENTS_SOL_PASS"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def critic_file(tmp_path):
    path = tmp_path / "critic.md"
    path.write_text(CRITIC_TEXT, encoding="utf-8")
    return path


def _reply(tmp_path, text=REPLY):
    path = tmp_path / "reply.txt"
    path.write_text(text, encoding="utf-8")
    return path


def _argv(command, tmp_path, critic, *extra, author="anthropic", repo=None):
    return [
        command,
        "--repo",
        str(repo or tmp_path),
        "--log-base",
        str(tmp_path),
        "--critic-findings",
        str(critic),
        "--model",
        SOL,
        "--author-family",
        author,
        *extra,
    ]


def _gate(tmp_path, critic, *extra, **kw):
    return mod.main(_argv("gate", tmp_path, critic, "--route", "t3", *extra, **kw))


def _record(tmp_path, critic, reply, *extra, **kw):
    return mod.main(_argv("record", tmp_path, critic, "--reply", str(reply), *extra, **kw))


def _log_dir(tmp_path):
    return tmp_path / ".project-toolkit" / "metrics" / "sol-loop"


def _logs(tmp_path):
    return [
        json.loads(p.read_text(encoding="utf-8")) for p in sorted(_log_dir(tmp_path).glob("*.json"))
    ]


def _out(capsys):
    return json.loads(capsys.readouterr().out)


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


def _git_repo(path: Path) -> None:
    path.mkdir()
    identity = ["-c", "user.name=Test", "-c", "user.email=test@example.com"]
    for args in (["init", "-q"], [*identity, "commit", "-q", "--allow-empty", "-m", "init"]):
        subprocess.run(["git", *args], cwd=path, check=True, capture_output=True)


def _touch_after_head(path: Path) -> None:
    """Set mtime past HEAD's whole-second commit time, so the order is certain."""
    later = time.time() + 5
    os.utime(path, (later, later))


@_needs_git
def test_gate_refuses_critic_output_older_than_head(tmp_path, critic_file, capsys):
    repo = tmp_path / "repo"
    _git_repo(repo)
    os.utime(critic_file, (1_000_000, 1_000_000))

    code = _gate(tmp_path, critic_file, repo=repo)

    assert code == mod.EXIT_CONFIG
    assert "older than HEAD" in capsys.readouterr().err


@_needs_git
def test_gate_proceeds_when_critic_output_is_newer_than_head(tmp_path, critic_file, capsys):
    repo = tmp_path / "repo"
    _git_repo(repo)
    _touch_after_head(critic_file)

    code = _gate(tmp_path, critic_file, repo=repo)

    assert code == mod.EXIT_OK
    assert _out(capsys)["verdict"] == "PROCEED"


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


@_needs_git
def test_round_count_is_per_branch_even_when_pr_number_appears(tmp_path, critic_file, capsys):
    repo = tmp_path / "repo"
    _git_repo(repo)
    _touch_after_head(critic_file)
    _record(tmp_path, critic_file, _reply(tmp_path), repo=repo)
    _record(tmp_path, critic_file, _reply(tmp_path), "--pr", "7", repo=repo)
    capsys.readouterr()

    code = _gate(tmp_path, critic_file, "--pr", "7", repo=repo)

    assert code == mod.EXIT_ESCALATE
    assert len({log["key"] for log in _logs(tmp_path)}) == 1


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
    (tmp_path / ".project-toolkit").write_text("not a directory", encoding="utf-8")

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


def test_unavailable_warn_prints_when_log_write_fails(tmp_path, critic_file, capsys):
    (tmp_path / ".project-toolkit").write_text("not a directory", encoding="utf-8")

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
    runs, unreadable = mod.load_runs(root / ".project-toolkit" / "metrics" / "sol-loop")

    assert unreadable == 0
    assert len(runs) >= 1
