"""Tests for scripts/eval/eval_adr_review_catch_rate.py (issue #5248).

The hyphenated CLI is loaded with importlib. The model seam is a plain callable,
so every path runs with no API spend and no network.
"""

from __future__ import annotations

import importlib.util
import json
import runpy
import subprocess
import sys
import threading
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
EVAL_DIR = _REPO / "scripts" / "eval"
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

import _adr_catch_rate_core as core  # noqa: E402


def _load_cli():
    spec = importlib.util.spec_from_file_location(
        "eval_adr_review_catch_rate", EVAL_DIR / "eval_adr_review_catch_rate.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


cli = _load_cli()

BASE, FIX = "b" * 40, "f" * 40
REVIEW_HIT = (
    "### Weaknesses/Gaps\n\n- The sky colour claim is wrong, it is blue.\n\n"
    "### Blocking Concerns\n\n| Issue | Priority | Description |\n|---|---|---|\n"
    "| Sky | P0 | The sky is blue |\n"
)
REVIEW_MISS = "### Weaknesses/Gaps\n\n- Nothing relevant here.\n"


def _entry(entry_id="T01", evidence=None):
    return {
        "id": entry_id,
        "fix_commit": FIX,
        "base_commit": BASE,
        "doc_path": "docs/adr.md",
        "anchor": "the sky is green",
        "kind": "factual-overclaim",
        "defect": "The sky is blue.",
        "match": {"all_of": [["sky"], ["blue"]]},
        "topic": ["the sky"],
        "evidence": evidence or [],
    }


def _write_corpus(tmp_path, *entries):
    path = tmp_path / "corpus.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "selection": {"rule": "every fix commit"},
                "entries": list(entries) or [_entry()],
            }
        ),
        encoding="utf-8",
    )
    return path


@pytest.fixture
def fake_git(monkeypatch):
    files = {
        (BASE, "docs/adr.md"): "intro the sky is green end",
        (FIX, "docs/adr.md"): "intro the sky is blue end",
        (BASE, "src/x.py"): "pre\ndef f():\n    return 1\n",
    }
    monkeypatch.setattr(cli, "git_show", lambda commit, path: files.get((commit, path)))
    return files


def _materialized(entry_id="T01", evidence=None):
    entry = core.parse_entry(_entry(entry_id, evidence))
    return core.Materialized(entry, "base text", "fixed text", "EVIDENCE" if evidence else "")


@pytest.fixture(scope="module")
def prompts_md():
    return (_REPO / cli.PROMPTS_PATH).read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def systems():
    return cli.load_role_systems(core.ROLES)


# --- git and templates -------------------------------------------------------


def test_git_show_reads_a_tracked_file():
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=_REPO, check=True
    ).stdout.strip()
    text = cli.git_show(head, "scripts/eval/_anthropic_api.py")
    assert text is not None and "def call_api" in text


def test_git_show_returns_none_for_an_unknown_object():
    assert cli.git_show("0" * 40, "README.md") is None


def test_load_role_systems_strips_frontmatter(systems):
    assert set(systems) == set(core.ROLES)
    assert all(not text.startswith("---") for text in systems.values())


# --- planning ----------------------------------------------------------------


def _plan(items, arms, roles=("critic", "security"), trials=1, prompts=None, systems_=None):
    return cli.plan_jobs(items, arms, roles, trials, prompts, {r: f"system {r}" for r in roles})


def test_plan_counts_one_job_per_entry_arm_role_trial(prompts_md):
    jobs = _plan([_materialized()], ("unassisted", "control"), trials=2, prompts=prompts_md)
    assert len(jobs) == 1 * 2 * 2 * 2


def test_plan_runs_assisted_only_for_entries_with_evidence(prompts_md):
    plain, with_evidence = (
        _materialized("T01"),
        _materialized("T02", [{"path": "src/x.py", "find": "def f", "lines": 2}]),
    )
    jobs = _plan([plain, with_evidence], ("assisted",), prompts=prompts_md)
    assert {j.entry for j in jobs} == {"T02"}


def test_plan_feeds_control_the_post_fix_text(prompts_md):
    jobs = _plan([_materialized()], ("unassisted", "control"), ("critic",), prompts=prompts_md)
    by_arm = {j.arm: j.user for j in jobs}
    assert "base text" in by_arm["unassisted"] and "fixed text" not in by_arm["unassisted"]
    assert "fixed text" in by_arm["control"]


def test_plan_appends_evidence_only_in_the_assisted_arm(prompts_md):
    item = _materialized("T02", [{"path": "src/x.py", "find": "def f", "lines": 2}])
    jobs = _plan([item], ("unassisted", "assisted"), ("critic",), prompts=prompts_md)
    by_arm = {j.arm: j.user for j in jobs}
    assert "EVIDENCE" in by_arm["assisted"] and "EVIDENCE" not in by_arm["unassisted"]


# --- running -----------------------------------------------------------------


def _job(entry="T01", arm="unassisted", role="critic", trial=0):
    return cli.Job(
        entry, arm, role, trial, "sys", "user", core.MatchRule((("sky",), ("blue",))), ("the sky",)
    )


def test_run_job_scores_a_hit():
    row = cli.run_job(_job(), lambda system, user: REVIEW_HIT)
    assert row["flagged"] and row["blocked"] and "blue" in row["matched"].lower()
    assert row["raw_chars"] == len(REVIEW_HIT) and len(row["raw_sha256"]) == 64


def test_run_job_scores_a_miss():
    row = cli.run_job(_job(), lambda system, user: REVIEW_MISS)
    assert not row["flagged"] and not row["blocked"] and "error" not in row


def test_run_job_records_a_provider_error_instead_of_a_miss():
    def boom(system, user):
        raise RuntimeError("provider down")

    row = cli.run_job(_job(), boom)
    assert row["error"] == "provider down" and not row["flagged"]


def test_run_job_keeps_the_whole_response_and_records_topic_mention():
    row = cli.run_job(_job(), lambda s, u: REVIEW_HIT)
    assert row["raw"] == REVIEW_HIT and row["mentioned"]
    quiet = cli.run_job(_job(), lambda s, u: REVIEW_MISS)
    assert not quiet["mentioned"]


def test_checkpoint_retries_rows_whose_stored_response_is_truncated(tmp_path):
    ckpt = tmp_path / "rows.jsonl"
    whole = cli.run_job(_job(trial=0), lambda s, u: REVIEW_HIT)
    cut = {**cli.run_job(_job(trial=1), lambda s, u: REVIEW_HIT)}
    cut["raw"] = cut["raw"][:20]
    ckpt.write_text(json.dumps(whole) + "\n" + json.dumps(cut) + "\n", encoding="utf-8")
    kept = cli.load_checkpoint(ckpt)
    assert [row["trial"] for row in kept] == [0]


def test_rescore_rows_applies_the_current_rules(tmp_path):
    corpus = core.parse_corpus(
        {"schema_version": 1, "selection": {"rule": "r"}, "entries": [_entry("T01")]}
    )
    row = cli.run_job(_job(), lambda s, u: REVIEW_MISS)
    assert not row["flagged"]
    row["raw"] = REVIEW_HIT
    (out,) = cli.rescore_rows([row], corpus)
    assert out["flagged"] and out["blocked"] and out["mentioned"]


def test_rescore_rows_rejects_an_unknown_entry():
    corpus = core.parse_corpus(
        {"schema_version": 1, "selection": {"rule": "r"}, "entries": [_entry("T01")]}
    )
    row = cli.run_job(_job(entry="T99"), lambda s, u: REVIEW_HIT)
    with pytest.raises(core.CorpusError, match="unknown entry"):
        cli.rescore_rows([row], corpus)


def test_run_jobs_runs_everything_in_parallel():
    jobs = [_job(trial=i) for i in range(8)]
    rows = cli.run_jobs(jobs, lambda s, u: REVIEW_HIT, workers=4)
    assert len(rows) == 8 and all(r["flagged"] for r in rows)


def test_run_jobs_floors_workers_at_one():
    rows = cli.run_jobs([_job()], lambda s, u: REVIEW_MISS, workers=0)
    assert len(rows) == 1


def test_checkpoint_resumes_without_repeating_finished_rows(tmp_path):
    ckpt = tmp_path / "rows.jsonl"
    calls: list[int] = []
    lock = threading.Lock()

    def caller(system, user):
        with lock:
            calls.append(1)
        return REVIEW_HIT

    jobs = [_job(trial=i) for i in range(3)]
    first = cli.run_jobs(jobs, caller, 1, [], ckpt)
    assert len(first) == 3 and len(calls) == 3
    again = cli.run_jobs(jobs, caller, 1, cli.load_checkpoint(ckpt), ckpt)
    assert len(again) == 3 and len(calls) == 3


def test_checkpoint_retries_errored_rows(tmp_path):
    ckpt = tmp_path / "rows.jsonl"

    def flaky(system, user):
        raise RuntimeError("once")

    cli.run_jobs([_job()], flaky, 1, [], ckpt)
    assert cli.load_checkpoint(ckpt) == []
    rows = cli.run_jobs([_job()], lambda s, u: REVIEW_HIT, 1, cli.load_checkpoint(ckpt), ckpt)
    assert len(rows) == 1 and rows[0]["flagged"]


def test_load_checkpoint_handles_absent_and_none(tmp_path):
    assert cli.load_checkpoint(None) == []
    assert cli.load_checkpoint(tmp_path / "absent.jsonl") == []


def test_make_caller_passes_system_and_user_to_the_provider(monkeypatch):
    seen = {}

    def fake_call_api(api_key, messages, system, model, max_tokens):
        seen.update(key=api_key, messages=messages, system=system, model=model, mt=max_tokens)
        return "text"

    monkeypatch.setattr(cli, "call_api", fake_call_api)
    slept: list[float] = []
    monkeypatch.setattr(cli.time, "sleep", slept.append)
    out = cli.make_caller("k", "m", 0.5)("SYS", "USER")
    assert out == "text" and slept == [0.5]
    assert seen["system"] == "SYS" and seen["messages"][0]["content"] == "USER"
    assert seen["model"] == "m" and seen["mt"] == cli.MAX_TOKENS


def test_make_caller_skips_sleep_without_a_pause(monkeypatch):
    monkeypatch.setattr(cli, "call_api", lambda *a, **k: "t")
    monkeypatch.setattr(cli.time, "sleep", lambda s: pytest.fail("slept"))
    assert cli.make_caller("k", "m", 0)("s", "u") == "t"


def test_summarize_drops_raw_text_and_aggregates():
    rows = [cli.run_job(_job(), lambda s, u: REVIEW_HIT)]
    result = cli.summarize(rows, {"model": "m"})
    assert "raw" not in result["rows"][0] and "raw_sha256" in result["rows"][0]
    assert result["table"]["unassisted"]["critic"]["flagged"]["hits"] == 1
    assert result["unions"]["unassisted"]["flagged"]["hits"] == 1


# --- argument and entry handling --------------------------------------------


def test_parse_args_defaults():
    args = cli.parse_args([])
    assert args.corpus == cli.DEFAULT_CORPUS and args.trials == 1
    assert args.arms == "unassisted,assisted"


def test_select_entries_filters_and_rejects_unknown_ids():
    corpus = core.parse_corpus(
        {
            "schema_version": 1,
            "selection": {"rule": "r"},
            "entries": [_entry("T01"), _entry("T02")],
        }
    )
    assert [e.id for e in cli.select_entries(corpus, ())] == ["T01", "T02"]
    assert [e.id for e in cli.select_entries(corpus, ("T02",))] == ["T02"]
    with pytest.raises(core.CorpusError, match="unknown entry ids"):
        cli.select_entries(corpus, ("T99",))


def test_prepare_rejects_unknown_arms_and_roles(tmp_path, fake_git):
    corpus = _write_corpus(tmp_path)
    for flag, value in (("--arms", "bogus"), ("--roles", "intern")):
        args = cli.parse_args(["--corpus", str(corpus), flag, value])
        with pytest.raises(core.CorpusError, match="unknown"):
            cli.prepare(args)


# --- main --------------------------------------------------------------------


def test_main_validate_corpus_prints_the_planned_calls(tmp_path, fake_git, capsys):
    corpus = _write_corpus(tmp_path)
    code = cli.main(["--corpus", str(corpus), "--validate-corpus", "--arms", "unassisted,control"])
    assert code == 0
    assert json.loads(capsys.readouterr().out) == {"entries": 1, "planned_calls": 12}


def test_main_dry_run_makes_no_calls(tmp_path, fake_git, capsys, monkeypatch):
    monkeypatch.setattr(cli, "make_caller", lambda *a: pytest.fail("called the model"))
    corpus = _write_corpus(tmp_path)
    assert cli.main(["--corpus", str(corpus), "--dry-run", "--roles", "critic"]) == 0
    assert json.loads(capsys.readouterr().out)["planned_calls"] == 1


def test_main_reports_a_corpus_error_with_exit_two(tmp_path, capsys):
    assert cli.main(["--corpus", str(tmp_path / "absent.json"), "--dry-run"]) == 2
    assert "ERROR" in capsys.readouterr().err


def test_main_reports_an_unreadable_commit_with_exit_two(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "git_show", lambda commit, path: None)
    corpus = _write_corpus(tmp_path)
    assert cli.main(["--corpus", str(corpus), "--dry-run"]) == 2
    assert "fetch_hint" in capsys.readouterr().err


def test_main_runs_end_to_end_and_writes_results(tmp_path, fake_git, monkeypatch, capsys):
    monkeypatch.setattr(cli, "load_api_key_for_selected_provider", lambda: "key")
    monkeypatch.setattr(cli, "make_caller", lambda key, model, pause: lambda s, u: REVIEW_HIT)
    corpus = _write_corpus(tmp_path)
    out, report = tmp_path / "out.json", tmp_path / "report.md"
    ckpt = tmp_path / "rows.jsonl"
    code = cli.main(
        [
            "--corpus",
            str(corpus),
            "--arms",
            "unassisted",
            "--roles",
            "critic,security",
            "--output",
            str(out),
            "--report",
            str(report),
            "--checkpoint",
            str(ckpt),
            "--workers",
            "2",
        ]
    )
    assert code == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["table"]["unassisted"]["critic"]["blocked"]["hits"] == 1
    assert "## Arm: unassisted" in report.read_text(encoding="utf-8")
    assert len(ckpt.read_text(encoding="utf-8").splitlines()) == 2
    assert "adr-review catch rate" in capsys.readouterr().out


def test_main_exits_three_when_every_call_fails(tmp_path, fake_git, monkeypatch):
    def down(system, user):
        raise RuntimeError("down")

    monkeypatch.setattr(cli, "load_api_key_for_selected_provider", lambda: "key")
    monkeypatch.setattr(cli, "make_caller", lambda key, model, pause: down)
    corpus = _write_corpus(tmp_path)
    assert cli.main(["--corpus", str(corpus), "--arms", "unassisted", "--roles", "critic"]) == 3


def test_main_exits_two_without_a_credential(tmp_path, fake_git, monkeypatch, capsys):
    def no_key():
        raise RuntimeError("no key")

    monkeypatch.setattr(cli, "load_api_key_for_selected_provider", no_key)
    corpus = _write_corpus(tmp_path)
    assert cli.main(["--corpus", str(corpus), "--roles", "critic"]) == 2
    assert "no key" in capsys.readouterr().err


def test_main_renders_a_report_from_saved_results(tmp_path, capsys):
    rows = [cli.run_job(_job(), lambda s, u: REVIEW_HIT)]
    saved = tmp_path / "saved.json"
    saved.write_text(json.dumps(cli.summarize(rows, {"model": "m", "trials": 1, "entries": 1})))
    assert cli.main(["--report-from", str(saved)]) == 0
    assert "| critic | 1/1" in capsys.readouterr().out


def test_script_entry_point_exits_with_the_main_code(tmp_path, monkeypatch, capsys):
    rows = [cli.run_job(_job(), lambda s, u: REVIEW_HIT)]
    saved = tmp_path / "saved.json"
    saved.write_text(json.dumps(cli.summarize(rows, {"model": "m", "trials": 1, "entries": 1})))
    monkeypatch.setattr(sys, "argv", ["eval", "--report-from", str(saved)])
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(EVAL_DIR / "eval_adr_review_catch_rate.py"), run_name="__main__")
    assert exc.value.code == 0
    assert "adr-review catch rate" in capsys.readouterr().out


def _checkpoint_with(tmp_path, reply):
    ckpt = tmp_path / "rows.jsonl"
    row = cli.run_job(_job(), lambda s, u: reply)
    ckpt.write_text(json.dumps(row) + "\n", encoding="utf-8")
    return ckpt


def test_main_rescore_reads_the_checkpoint_without_calling_a_model(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "make_caller", lambda *a: pytest.fail("called the model"))
    corpus = _write_corpus(tmp_path)
    ckpt = _checkpoint_with(tmp_path, REVIEW_HIT)
    out = tmp_path / "rescored.json"
    code = cli.main(
        ["--corpus", str(corpus), "--rescore", "--checkpoint", str(ckpt), "--output", str(out)]
    )
    assert code == 0
    assert json.loads(out.read_text(encoding="utf-8"))["table"]["unassisted"]["critic"]
    assert "| critic | 1/1" in capsys.readouterr().out


def test_main_rescore_filters_entries(tmp_path, capsys):
    corpus = _write_corpus(tmp_path, _entry("T01"), _entry("T02"))
    ckpt = _checkpoint_with(tmp_path, REVIEW_HIT)
    assert (
        cli.main(
            ["--corpus", str(corpus), "--rescore", "--checkpoint", str(ckpt), "--entries", "T02"]
        )
        == 0
    )
    assert "critic" not in capsys.readouterr().out


def test_main_rescore_requires_a_checkpoint(tmp_path, capsys):
    corpus = _write_corpus(tmp_path)
    assert cli.main(["--corpus", str(corpus), "--rescore"]) == 2
    assert "--checkpoint" in capsys.readouterr().err


def test_main_rescore_reports_a_bad_corpus(tmp_path, capsys):
    ckpt = _checkpoint_with(tmp_path, REVIEW_HIT)
    code = cli.main(
        ["--corpus", str(tmp_path / "absent.json"), "--rescore", "--checkpoint", str(ckpt)]
    )
    assert code == 2 and "ERROR" in capsys.readouterr().err


def test_dump_results_is_valid_json_with_one_line_per_row_and_arm():
    rows = [cli.run_job(_job(trial=i), lambda s, u: REVIEW_HIT) for i in range(3)]
    text = cli.dump_results(cli.summarize(rows, {"model": "m", "trials": 1, "entries": 1}))
    parsed = json.loads(text)
    assert len(parsed["rows"]) == 3 and parsed["meta"]["model"] == "m"
    assert len([line for line in text.splitlines() if '"trial"' in line]) == 3
    assert len(text.splitlines()) < 40


def test_dump_results_handles_scalars_and_empty_lists():
    parsed = json.loads(cli.dump_results({"note": "x", "rows": [], "meta": {}}))
    assert parsed == {"note": "x", "rows": [], "meta": {}}
