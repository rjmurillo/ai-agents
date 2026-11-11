"""Tests for failure modes, resume, and rescore in eval_code_review_catch_rate.py (issue #7149)."""

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
)


@pytest.fixture
def repo(tmp_path: Path) -> dict:
    return build_repo(tmp_path)


class TestFailureModes:
    def test_every_call_failing_exits_3(self, tmp_path, repo):
        corpus = _write_corpus(tmp_path, repo)

        def failing(system, user):
            raise RuntimeError("provider down")

        assert cli.main(_argv(corpus), caller=failing, git=_git(repo["root"])) == 3

    def test_errored_calls_are_excluded_from_n_not_counted_as_misses(self, tmp_path, repo):
        corpus = _write_corpus(tmp_path, repo)
        out = tmp_path / "results.json"

        def flaky(system, user):
            if "pkg/mod3.py" in user:
                raise RuntimeError("timed out")
            return _stub()(system, user)

        code = cli.main(_argv(corpus, "--output", str(out)), caller=flaky, git=_git(repo["root"]))

        agg = json.loads(out.read_text(encoding="utf-8"))["aggregate"]
        assert code == 0
        assert (agg["caught_top5"]["hits"], agg["caught_top5"]["n"], agg["errors"]) == (2, 3, 1)

    def test_unknown_entry_id_exits_2(self, tmp_path, repo):
        corpus = _write_corpus(tmp_path, repo)

        assert (
            cli.main(_argv(corpus, "--entries", "CR99", "--dry-run"), git=_git(repo["root"])) == 2
        )

    def test_unreadable_fixing_commit_exits_2_under_validate_corpus(self, tmp_path, repo):
        corpus = _write_corpus(tmp_path, repo)
        git = _git(repo["root"])
        fixes = {fix for _, fix in repo["pairs"]}

        def fix_missing(args):
            return None if fixes & set(args) else git(args)

        assert cli.main(_argv(corpus, "--validate-corpus"), git=fix_missing) == 2

    def test_validate_corpus_reports_the_planned_call_count(self, tmp_path, repo, capsys):
        corpus = _write_corpus(tmp_path, repo)

        cli.main(_argv(corpus, "--validate-corpus", "--trials", "2"), git=_git(repo["root"]))

        assert json.loads(capsys.readouterr().out)["planned_calls"] == 8

    @pytest.mark.parametrize("text", ["[]", "null", '"text"', "{}", '{"meta": {}}'])
    def test_report_from_json_that_is_not_a_results_file_exits_2(self, tmp_path, text):
        bad = tmp_path / "shape.json"
        bad.write_text(text, encoding="utf-8")

        assert cli.main(["--report-from", str(bad)]) == 2

    def test_report_from_a_missing_or_corrupt_file_exits_2(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_bytes(b"\xff\xfe not json")

        assert cli.main(["--report-from", str(tmp_path / "absent.json")]) == 2
        assert cli.main(["--report-from", str(bad)]) == 2

    def test_unreadable_introducer_exits_2(self, tmp_path, repo):
        corpus = _write_corpus(tmp_path, repo)

        assert cli.main(_argv(corpus, "--dry-run"), git=lambda args: None) == 2


class TestCheckpoint:
    def test_a_rerun_with_a_checkpoint_makes_no_new_calls(self, tmp_path, repo):
        corpus = _write_corpus(tmp_path, repo)
        checkpoint = tmp_path / "rows.jsonl"
        cli.main(
            _argv(corpus, "--checkpoint", str(checkpoint)), caller=_stub(), git=_git(repo["root"])
        )

        def forbidden(system, user):
            raise AssertionError("model called on a finished checkpoint")

        code = cli.main(
            _argv(corpus, "--checkpoint", str(checkpoint)), caller=forbidden, git=_git(repo["root"])
        )

        assert code == 0

    def test_rows_outside_the_requested_entries_stay_out_of_the_aggregate(self, tmp_path, repo):
        corpus = _write_corpus(tmp_path, repo)
        checkpoint = tmp_path / "rows.jsonl"
        out = tmp_path / "subset.json"
        cli.main(
            _argv(corpus, "--checkpoint", str(checkpoint)), caller=_stub(), git=_git(repo["root"])
        )

        code = cli.main(
            _argv(corpus, "--entries", "CR01", "--checkpoint", str(checkpoint))
            + ["--output", str(out)],
            caller=_stub(),
            git=_git(repo["root"]),
        )

        result = json.loads(out.read_text(encoding="utf-8"))
        assert code == 0
        assert {r["entry"] for r in result["rows"]} == {"CR01"}
        assert (
            result["aggregate"]["caught_top5"]["hits"],
            result["aggregate"]["caught_top5"]["n"],
        ) == (1, 1)
        assert result["meta"]["entries"] == 1

    def test_a_resumed_run_says_its_counts_cover_this_invocation_only(self, tmp_path, repo):
        corpus = _write_corpus(tmp_path, repo)
        checkpoint = tmp_path / "rows.jsonl"
        out = tmp_path / "resumed.json"
        report_path = tmp_path / "resumed.md"
        cli.main(
            _argv(corpus, "--checkpoint", str(checkpoint)), caller=_stub(), git=_git(repo["root"])
        )

        cli.main(
            _argv(corpus, "--checkpoint", str(checkpoint), "--output", str(out))
            + ["--report", str(report_path)],
            caller=_stub(),
            git=_git(repo["root"]),
        )

        meta = json.loads(out.read_text(encoding="utf-8"))["meta"]
        assert meta["resumed_rows"] == 4
        assert "4 rows were reused from a checkpoint" in report_path.read_text(encoding="utf-8")

    def test_a_half_written_last_line_is_dropped_and_its_job_reruns(self, tmp_path, repo):
        corpus = _write_corpus(tmp_path, repo)
        checkpoint = tmp_path / "rows.jsonl"
        cli.main(
            _argv(corpus, "--checkpoint", str(checkpoint)), caller=_stub(), git=_git(repo["root"])
        )
        lines = checkpoint.read_text(encoding="utf-8").splitlines()
        checkpoint.write_text("\n".join([*lines[:-1], lines[-1][:40]]) + "\n", encoding="utf-8")
        calls: list[str] = []

        def counting(system, user):
            calls.append(user)
            return _stub()(system, user)

        code = cli.main(
            _argv(corpus, "--checkpoint", str(checkpoint)), caller=counting, git=_git(repo["root"])
        )

        assert code == 0 and len(calls) == 1

    def test_a_corrupt_interior_line_or_non_utf8_checkpoint_exits_2(self, tmp_path, repo):
        corpus = _write_corpus(tmp_path, repo)
        checkpoint = tmp_path / "rows.jsonl"
        cli.main(
            _argv(corpus, "--checkpoint", str(checkpoint)), caller=_stub(), git=_git(repo["root"])
        )
        lines = checkpoint.read_text(encoding="utf-8").splitlines()
        checkpoint.write_text("\n".join(["{not json", *lines[1:]]) + "\n", encoding="utf-8")

        interior = cli.main(
            _argv(corpus, "--checkpoint", str(checkpoint)), caller=_stub(), git=_git(repo["root"])
        )
        checkpoint.write_bytes(b"\xff\xfe\n")
        binary = cli.main(
            _argv(corpus, "--checkpoint", str(checkpoint)), caller=_stub(), git=_git(repo["root"])
        )

        assert (interior, binary) == (2, 2)

    def test_rescore_reads_stored_responses_with_no_model_call(self, tmp_path, repo):
        corpus = _write_corpus(tmp_path, repo)
        checkpoint = tmp_path / "rows.jsonl"
        out = tmp_path / "rescored.json"
        cli.main(
            _argv(corpus, "--checkpoint", str(checkpoint)), caller=_stub(), git=_git(repo["root"])
        )

        code = cli.main(
            _argv(corpus, "--rescore", "--checkpoint", str(checkpoint), "--output", str(out))
        )

        caught = json.loads(out.read_text(encoding="utf-8"))["aggregate"]["caught_top5"]
        assert code == 0 and (caught["hits"], caught["n"]) == (2, 4)

    @pytest.mark.parametrize("line", ["[]", "3", "null", '{"entry": "CR01"}'])
    def test_a_checkpoint_line_that_is_not_a_result_row_exits_2(self, tmp_path, repo, line):
        corpus = _write_corpus(tmp_path, repo)
        checkpoint = tmp_path / "rows.jsonl"
        checkpoint.write_text(line + "\n" + line + "\n", encoding="utf-8")

        code = cli.main(
            _argv(corpus, "--checkpoint", str(checkpoint)), caller=_stub(), git=_git(repo["root"])
        )

        assert code == 2

    @pytest.mark.parametrize("trials", ["0", "-1"])
    def test_trials_below_one_is_a_usage_error(self, tmp_path, repo, trials):
        corpus = _write_corpus(tmp_path, repo)

        with pytest.raises(SystemExit) as exit_info:
            cli.main(_argv(corpus, "--trials", trials, "--dry-run"), git=_git(repo["root"]))

        assert exit_info.value.code == 2

    def test_rescore_header_describes_the_selected_rows(self, tmp_path, repo):
        corpus = _write_corpus(tmp_path, repo)
        checkpoint = tmp_path / "rows.jsonl"
        out = tmp_path / "rescored.json"
        report_path = tmp_path / "rescored.md"
        cli.main(
            _argv(corpus, "--checkpoint", str(checkpoint), "--trials", "2"),
            caller=_stub(),
            git=_git(repo["root"]),
        )

        code = cli.main(
            _argv(corpus, "--rescore", "--checkpoint", str(checkpoint), "--entries", "CR01,CR02")
            + ["--output", str(out), "--report", str(report_path)]
        )

        result = json.loads(out.read_text(encoding="utf-8"))
        assert code == 0
        assert (result["meta"]["entries"], result["meta"]["trials"]) == (2, 2)
        assert result["aggregate"]["caught_top5"]["n"] == 4
        assert "rescored from stored responses" in report_path.read_text(encoding="utf-8")

    @pytest.mark.parametrize("entries", ["CR99", "CR01,CR99"])
    def test_rescore_with_an_unknown_entry_id_exits_2(self, tmp_path, repo, entries):
        corpus = _write_corpus(tmp_path, repo)
        checkpoint = tmp_path / "rows.jsonl"
        cli.main(
            _argv(corpus, "--checkpoint", str(checkpoint)), caller=_stub(), git=_git(repo["root"])
        )

        code = cli.main(
            _argv(corpus, "--rescore", "--checkpoint", str(checkpoint), "--entries", entries)
        )

        assert code == 2

    def test_rescore_without_a_checkpoint_exits_2(self, tmp_path, repo):
        assert cli.main(_argv(_write_corpus(tmp_path, repo), "--rescore")) == 2


def test_report_from_renders_saved_results(tmp_path, repo, capsys):
    corpus = _write_corpus(tmp_path, repo)
    out = tmp_path / "results.json"
    cli.main(_argv(corpus, "--output", str(out)), caller=_stub(), git=_git(repo["root"]))
    capsys.readouterr()

    code = cli.main(["--report-from", str(out)])

    assert code == 0 and "Caught in top 5" in capsys.readouterr().out
