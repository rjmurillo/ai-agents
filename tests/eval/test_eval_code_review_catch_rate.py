"""Tests for eval_code_review_catch_rate.py: scoring, parallel runs, leak guard (issue #7149)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from code_review_catch_rate_helpers import (  # noqa: E402
    _argv,
    _git,
    _stub,
    _write_corpus,
    build_repo,
    cli,
    wilson_interval,
)


@pytest.fixture
def repo(tmp_path: Path) -> dict:
    return build_repo(tmp_path)


class TestDryRun:
    def test_stub_reviewer_yields_the_known_rate_and_interval(self, tmp_path, repo):
        corpus = _write_corpus(tmp_path, repo)
        out = tmp_path / "results.json"

        code = cli.main(_argv(corpus, "--output", str(out)), caller=_stub(), git=_git(repo["root"]))

        result = json.loads(out.read_text(encoding="utf-8"))
        caught = result["aggregate"]["caught_top5"]
        low, high = wilson_interval(2, 4)
        assert code == 0
        assert (caught["hits"], caught["n"], caught["rate"]) == (2, 4, 0.5)
        assert caught["ci95"] == [round(low, 4), round(high, 4)]

    def test_near_miss_and_empty_findings_are_reported_apart_from_catches(self, tmp_path, repo):
        corpus = _write_corpus(tmp_path, repo)
        out = tmp_path / "results.json"

        cli.main(_argv(corpus, "--output", str(out)), caller=_stub(), git=_git(repo["root"]))

        result = json.loads(out.read_text(encoding="utf-8"))
        by_id = {e["entry"]: e for e in result["entries"]}
        assert result["aggregate"]["file_only_top5"]["hits"] == 3
        assert result["aggregate"]["no_findings"] == 1
        assert (by_id["CR03"]["caught"], by_id["CR03"]["near_miss"]) == (0, 1)
        assert (by_id["CR04"]["caught"], by_id["CR04"]["no_findings"]) == (0, 1)

    def test_report_names_model_date_trials_and_rate(self, tmp_path, repo):
        corpus = _write_corpus(tmp_path, repo)
        report = tmp_path / "report.md"

        cli.main(
            _argv(corpus, "--model", "stub-model", "--report", str(report)),
            caller=_stub(),
            git=_git(repo["root"]),
        )

        text = report.read_text(encoding="utf-8")
        assert "stub-model" in text and "4 entries x 1 trial" in text
        assert "2/4 (50%" in text

    def test_report_states_cost_for_a_subscription_provider(self, tmp_path, repo, monkeypatch):
        monkeypatch.setenv("EVAL_PROVIDER", "claude-cli")
        corpus = _write_corpus(tmp_path, repo)
        out = tmp_path / "results.json"
        report = tmp_path / "report.md"

        cli.main(
            _argv(corpus, "--output", str(out), "--report", str(report)),
            caller=_stub(),
            git=_git(repo["root"]),
        )

        meta = json.loads(out.read_text(encoding="utf-8"))["meta"]
        assert meta["provider"] == "claude-cli" and "subscription" in meta["cost"]
        assert "Cost: subscription" in report.read_text(encoding="utf-8")

    def test_planned_call_count_is_entries_times_trials(self, tmp_path, repo, capsys):
        corpus = _write_corpus(tmp_path, repo)

        code = cli.main(_argv(corpus, "--trials", "3", "--dry-run"), git=_git(repo["root"]))

        assert code == 0
        assert json.loads(capsys.readouterr().out) == {"entries": 4, "planned_calls": 12}

    def test_trials_multiply_calls_and_keep_the_rate(self, tmp_path, repo):
        corpus = _write_corpus(tmp_path, repo)
        out = tmp_path / "results.json"
        calls: list[str] = []

        def counting(system, user):
            calls.append(user)
            return _stub()(system, user)

        cli.main(
            _argv(corpus, "--trials", "2", "--output", str(out)),
            caller=counting,
            git=_git(repo["root"]),
        )

        caught = json.loads(out.read_text(encoding="utf-8"))["aggregate"]["caught_top5"]
        assert len(calls) == 8
        assert (caught["hits"], caught["n"]) == (4, 8)


class TestParallelRun:
    def test_four_workers_write_each_job_once_to_the_checkpoint(self, tmp_path, repo):
        corpus = _write_corpus(tmp_path, repo)
        checkpoint = tmp_path / "rows.jsonl"
        out = tmp_path / "results.json"

        code = cli.main(
            ["--corpus", str(corpus), "--workers", "4", "--trials", "3"]
            + ["--checkpoint", str(checkpoint), "--output", str(out)],
            caller=_stub(),
            git=_git(repo["root"]),
        )

        rows = [json.loads(line) for line in checkpoint.read_text(encoding="utf-8").splitlines()]
        keys = sorted((r["entry"], r["trial"]) for r in rows)
        expected = sorted((f"CR{i:02d}", t) for i in range(1, 5) for t in range(3))
        caught = json.loads(out.read_text(encoding="utf-8"))["aggregate"]["caught_top5"]
        assert code == 0
        assert keys == expected
        assert (caught["hits"], caught["n"]) == (6, 12)


class TestLeakGuard:
    def test_no_prompt_sent_to_the_reviewer_carries_fix_content(self, tmp_path, repo):
        corpus = _write_corpus(tmp_path, repo)
        prompts: list[str] = []

        cli.main(_argv(corpus), caller=_stub(prompts), git=_git(repo["root"]))

        assert len(prompts) == 4
        for prompt in prompts:
            assert "REPAIRED_LINE" not in prompt
            assert "repair module" not in prompt
            assert not any(fix[:12] in prompt for _, fix in repo["pairs"])
            assert "BUGGY_LINE" in prompt

    def test_the_reviewer_sees_only_its_own_introducing_diff(self, tmp_path, repo):
        corpus = _write_corpus(tmp_path, repo)
        prompts: list[str] = []

        cli.main(_argv(corpus), caller=_stub(prompts), git=_git(repo["root"]))

        for prompt in prompts:
            assert sum(f"BUGGY_LINE_{i}_" in prompt for i in range(4)) == 1

    def test_validate_corpus_passes_on_a_clean_corpus(self, tmp_path, repo, capsys):
        corpus = _write_corpus(tmp_path, repo)

        code = cli.main(_argv(corpus, "--validate-corpus"), git=_git(repo["root"]))

        summary = json.loads(capsys.readouterr().out)
        assert code == 0 and summary["leaks"] == {} and summary["entries"] == 4

    def test_validate_corpus_exits_2_when_the_defect_text_is_in_the_prompt(
        self, tmp_path, repo, capsys
    ):
        corpus = _write_corpus(
            tmp_path, repo, defect="return value + 0  # BUGGY_LINE_0_not_checked_at_all"
        )

        code = cli.main(_argv(corpus, "--validate-corpus"), git=_git(repo["root"]))

        assert code == 2
        assert "corpus defect description" in json.dumps(
            json.loads(capsys.readouterr().out)["leaks"]
        )
