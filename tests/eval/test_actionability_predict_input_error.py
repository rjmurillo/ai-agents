"""input_error status and carried-record validation in predict (review round 2, group B).

Plan M1-T14, premortem R2. Shared helpers: _actionability_arms_test_support.py.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests.eval._actionability_arms_test_support import (
    FakeCallApi,
    aa,
    heldout_rows,
    install_call_api,
    make_prediction,
    make_row,
    ok_record,
    pm,
    provider_argv,
    read_jsonl_file,
    row_id_of,
    sc,
    write_corpus_file,
    write_jsonl_file,
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("EVAL_PROVIDER", raising=False)


def _reject_rows(monkeypatch: pytest.MonkeyPatch, *row_ids: str) -> None:
    """Make building the message for these rows raise a local ValueError."""
    real = pm.build_user_message

    def build(row: dict[str, Any], *args: Any, **kwargs: Any) -> str:
        if row["id"] in row_ids:
            raise ValueError("local input problem")
        return real(row, *args, **kwargs)

    monkeypatch.setattr(pm, "build_user_message", build)


class TestInputErrorStatus:
    def test_the_status_is_in_the_shared_vocabulary(self) -> None:
        """labels owns the status names, including the new one."""
        labels = __import__("scripts.eval.actionability_labels", fromlist=["x"])

        assert labels.STATUS_INPUT_ERROR == "input_error"
        assert "input_error" in labels.STATUSES

    def test_a_local_value_error_is_recorded_as_input_error_and_never_calls_the_transport(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A row whose message cannot be built is a local problem, not a transport failure."""
        fake = install_call_api(monkeypatch, FakeCallApi())
        _reject_rows(monkeypatch, "H1")
        out = tmp_path / "pred.jsonl"

        code = aa.main(provider_argv(write_corpus_file(tmp_path, heldout_rows(3)), out))

        records = {r["id"]: r for r in read_jsonl_file(out)}
        assert code == 0
        assert records["H1"]["status"] == "input_error"
        assert records["H1"]["error_type"] == "ValueError"
        assert records["H1"]["is_actionable"] is None
        assert len(fake.calls) == 2
        assert {records["H0"]["status"], records["H2"]["status"]} == {"ok"}

    def test_a_value_error_from_the_transport_is_still_a_call_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Only errors raised before the call count as input errors."""

        def reply(_message: str) -> str:
            raise ValueError("from the provider")

        install_call_api(monkeypatch, FakeCallApi(reply))
        out = tmp_path / "pred.jsonl"

        aa.main(provider_argv(write_corpus_file(tmp_path, heldout_rows(1)), out))

        assert read_jsonl_file(out)[0]["status"] == "call_error"

    def test_five_input_errors_in_a_row_do_not_trip_the_breaker(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The breaker is about the transport being down. Bad rows say nothing about it."""
        fake = install_call_api(monkeypatch, FakeCallApi())
        _reject_rows(monkeypatch, *(f"H{i}" for i in range(6)))
        out = tmp_path / "pred.jsonl"

        code = aa.main(provider_argv(write_corpus_file(tmp_path, heldout_rows(6)), out))

        seen = capsys.readouterr()
        assert code == 3
        assert fake.calls == []
        assert len(read_jsonl_file(out)) == 6
        assert "attempted 6 of 6 selected" in seen.out
        assert "input_error 6" in seen.out
        assert "consecutive" not in seen.out + seen.err

    def test_input_errors_are_neither_counted_nor_resetting_in_the_streak(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Four transport failures, a bad row, and a fifth transport failure make a streak of 5."""
        calls = {"n": 0}

        def reply(_message: str) -> str:
            calls["n"] += 1
            raise RuntimeError("down")

        fake = install_call_api(monkeypatch, FakeCallApi(reply))
        _reject_rows(monkeypatch, "H4")
        out = tmp_path / "pred.jsonl"

        code = aa.main(provider_argv(write_corpus_file(tmp_path, heldout_rows(10)), out))

        statuses = [r["status"] for r in read_jsonl_file(out)]
        assert code == 3
        assert len(fake.calls) == 5
        assert statuses == ["call_error"] * 4 + ["input_error", "call_error"]

    def test_a_rerun_retries_input_error_rows(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """input_error is not ok, so a resume picks the row up again."""
        corpus = write_corpus_file(tmp_path, heldout_rows(2))
        out = write_jsonl_file(
            tmp_path / "pred.jsonl",
            [
                ok_record("H0"),
                ok_record("H1", status="input_error", is_actionable=None, confidence=None),
            ],
        )
        fake = install_call_api(monkeypatch, FakeCallApi())

        assert aa.main(provider_argv(corpus, out)) == 0

        assert [row_id_of(c["messages"][0]["content"]) for c in fake.calls] == ["H1"]
        assert {r["status"] for r in read_jsonl_file(out)} == {"ok"}

    def test_the_summary_line_counts_input_errors(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """input_error appears on the line only when there is one."""
        install_call_api(monkeypatch, FakeCallApi())
        _reject_rows(monkeypatch, "H0")

        aa.main(provider_argv(write_corpus_file(tmp_path, heldout_rows(3)), tmp_path / "p.jsonl"))

        assert "input_error 1" in capsys.readouterr().out

    def test_a_clean_run_does_not_print_input_error(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """No noise when there are none."""
        install_call_api(monkeypatch, FakeCallApi())

        aa.main(provider_argv(write_corpus_file(tmp_path, heldout_rows(2)), tmp_path / "p.jsonl"))

        assert "input_error" not in capsys.readouterr().out


class TestScoreTreatsInputErrorAsNonOk:
    def test_score_counts_it_and_falls_back_to_the_heuristic(self) -> None:
        """Arm C keeps arm A's answer for the row, and the report counts the status."""
        rows = [make_row(f"H{i}", label="actionable") for i in range(4)]
        preds = [
            make_prediction("H0"),
            make_prediction("H1", status="input_error", is_actionable=None, confidence=None),
        ]

        report = sc.build_report(rows, preds, aa.ARM_FUNCTIONS, seed=1, iterations=50)

        assert report["predictions"]["input_error"] == 1
        assert report["predictions"]["ok"] == 1
        assert report["predictions"]["missing"] == 2

    def test_the_score_line_names_input_errors_when_present(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Through main(argv): the stdout line carries input_error."""
        rows = [
            make_row(f"H{i}", label="actionable" if i % 2 else "not_actionable") for i in range(6)
        ]
        preds = [
            make_prediction("H0"),
            make_prediction("H1", status="input_error", is_actionable=None),
        ]
        corpus = write_jsonl_file(tmp_path / "c.jsonl", rows)
        predictions = write_jsonl_file(tmp_path / "p.jsonl", preds)
        argv = ["score", "--corpus", str(corpus), "--predictions", str(predictions)]

        code = aa.main([*argv, "--output", str(tmp_path / "r.json"), "--bootstrap", "50"])

        assert code == 0
        assert "input_error 1" in capsys.readouterr().out


def _prior(tmp_path: Path, **overrides: Any) -> tuple[Path, Path]:
    corpus = write_corpus_file(tmp_path, heldout_rows(3))
    out = write_jsonl_file(tmp_path / "pred.jsonl", [ok_record("H0", **overrides)])
    return corpus, out


class TestCarriedRecordValidation:
    @pytest.mark.parametrize(
        ("key", "value"),
        [
            ("is_actionable", "yes"),
            ("is_actionable", 1),
            ("is_actionable", None),
            ("confidence", "0.9"),
            ("confidence", None),
            ("confidence", float("nan")),
            ("confidence", True),
            ("latency_s", "fast"),
            ("id", ""),
            ("reason", 5),
        ],
    )
    def test_a_malformed_ok_record_exits_two_and_leaves_the_file(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        key: str,
        value: Any,
    ) -> None:
        """A carried 'ok' record has to hold a real verdict, or the resume stops."""
        corpus, out = _prior(tmp_path, **{key: value})
        before = out.read_bytes()
        fake = install_call_api(monkeypatch, FakeCallApi())

        code = aa.main(provider_argv(corpus, out))

        assert code == 2
        assert fake.calls == []
        assert out.read_bytes() == before
        assert key in capsys.readouterr().err

    def test_an_ok_record_without_an_id_exits_two(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """It used to be skipped without a word."""
        corpus = write_corpus_file(tmp_path, heldout_rows(2))
        record = ok_record("H0")
        del record["id"]
        out = write_jsonl_file(tmp_path / "pred.jsonl", [record])
        fake = install_call_api(monkeypatch, FakeCallApi())

        assert aa.main(provider_argv(corpus, out)) == 2
        assert fake.calls == []

    def test_the_error_names_the_file_and_the_field_but_not_the_value(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Values can be anything, so only the key and expectation print."""
        corpus, out = _prior(tmp_path, is_actionable="SECRETLOOKING")
        install_call_api(monkeypatch, FakeCallApi())

        aa.main(provider_argv(corpus, out))

        err = capsys.readouterr().err
        assert "is_actionable" in err
        assert "SECRETLOOKING" not in err

    def test_a_valid_carried_record_still_resumes(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The check narrows, it does not break resume."""
        corpus, out = _prior(tmp_path)
        fake = install_call_api(monkeypatch, FakeCallApi())

        assert aa.main(provider_argv(corpus, out)) == 0

        assert len(fake.calls) == 2
        assert "resuming, 1 done" in capsys.readouterr().out

    def test_failed_records_are_not_held_to_the_ok_standard(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Only ok records are carried, so a failed one with junk fields is just dropped."""
        corpus = write_corpus_file(tmp_path, heldout_rows(2))
        junk = ok_record("H1", status="call_error", is_actionable="no", confidence="x")
        out = write_jsonl_file(tmp_path / "pred.jsonl", [ok_record("H0"), junk])
        install_call_api(monkeypatch, FakeCallApi())

        assert aa.main(provider_argv(corpus, out)) == 0
        assert {r["status"] for r in read_jsonl_file(out)} == {"ok"}
        assert json.dumps(read_jsonl_file(out))
