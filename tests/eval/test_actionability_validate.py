"""Row validation shared by score, predict, and fetch-hunks (review finding 5).

A corpus row with a missing or wrong-typed field must exit 2 naming the row and the field,
never raise a KeyError or TypeError from deep inside the scan or the message builder.
Plan M1-T9 and M1-T14.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import pytest

from tests.eval._actionability_arms_test_support import (
    FakeCallApi,
    aa,
    heldout_rows,
    install_call_api,
    make_row,
    provider_argv,
    sc,
    write_corpus_file,
)
from tests.eval._actionability_corpus_test_support import (
    FakeGraphql,
    cc,
    corpus_row,
    write_corpus,
)

validate = importlib.import_module("scripts.eval.actionability_validate")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("EVAL_PROVIDER", raising=False)


class TestValidateRecords:
    def test_valid_rows_pass(self) -> None:
        """Rows with every field pass without a message."""
        validate.validate_records([make_row("A")], validate.SENT_ROW_CHECKS, "corpus")

    def test_error_names_the_position_the_id_and_the_field(self) -> None:
        """The message says which row and which field."""
        rows = [make_row("A"), make_row("B", body=None)]

        with pytest.raises(validate.RecordError) as raised:
            validate.validate_records(rows, validate.SENT_ROW_CHECKS, "corpus")

        text = str(raised.value)
        assert "corpus row 2" in text
        assert "(B)" in text
        assert "body" in text

    def test_a_row_with_no_usable_id_is_named_by_position_only(self) -> None:
        """No id to print, so the position carries the identity."""
        rows = [make_row("A"), {"body": "x", "thread_replies": []}]

        with pytest.raises(validate.RecordError, match=r"corpus row 2: id"):
            validate.validate_records(rows, validate.SENT_ROW_CHECKS, "corpus")

    def test_the_message_never_carries_the_bad_value(self) -> None:
        """A field value may be a secret, so only the key and the expectation print."""
        rows = [make_row("A", body="SECRETVALUE" * 3)]
        rows[0]["thread_replies"] = "SECRETVALUE"

        with pytest.raises(validate.RecordError) as raised:
            validate.validate_records(rows, validate.SENT_ROW_CHECKS, "corpus")

        assert "SECRETVALUE" not in str(raised.value)

    def test_score_uses_the_shared_corpus_checks(self) -> None:
        """Single source: score imports the tables instead of defining its own."""
        assert sc.SCORE_CORPUS_CHECKS is validate.SCORE_CORPUS_CHECKS
        assert sc.PREDICTION_CHECKS is validate.PREDICTION_CHECKS


_BAD_ROWS = [
    ("body", None),
    ("body", 5),
    ("thread_replies", None),
    ("thread_replies", "a plain string"),
    ("thread_replies", ["ok", 7]),
    ("path", 3),
    ("id", None),
    ("id", ""),
    ("id", 12),
]


class TestPredictValidatesRows:
    @pytest.mark.parametrize(("key", "value"), _BAD_ROWS)
    def test_a_bad_selected_row_exits_two_before_any_call(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        key: str,
        value: Any,
    ) -> None:
        """Plan M1-T14: a malformed row is a config error, not a KeyError traceback."""
        fake = install_call_api(monkeypatch, FakeCallApi())
        rows = heldout_rows(3)
        rows[1][key] = value
        out = tmp_path / "pred.jsonl"

        code = aa.main(provider_argv(write_corpus_file(tmp_path, rows), out))

        err = capsys.readouterr().err
        assert code == 2
        assert fake.calls == []
        assert not out.exists()
        assert key in err
        assert "corpus row 2" in err

    @pytest.mark.parametrize("key", ["body", "thread_replies", "id"])
    def test_a_missing_key_exits_two_naming_it(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        key: str,
    ) -> None:
        """The reproduced case: a row with no body raised KeyError at the scan."""
        install_call_api(monkeypatch, FakeCallApi())
        rows = heldout_rows(2)
        del rows[0][key]

        code = aa.main(provider_argv(write_corpus_file(tmp_path, rows), tmp_path / "p.jsonl"))

        assert code == 2
        assert key in capsys.readouterr().err

    def test_the_error_names_the_row_id(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The coordinator's contract: name the row id and the field."""
        install_call_api(monkeypatch, FakeCallApi())
        rows = heldout_rows(3)
        rows[2]["body"] = None

        code = aa.main(provider_argv(write_corpus_file(tmp_path, rows), tmp_path / "p.jsonl"))

        err = capsys.readouterr().err
        assert code == 2
        assert "(H2)" in err
        assert "body" in err

    def test_rows_outside_the_selection_are_not_validated(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Predict only uses in-band rows of the split, so a dev row's gaps are not its problem."""
        fake = install_call_api(monkeypatch, FakeCallApi())
        rows = [*heldout_rows(2), make_row("D0", split="dev", body=None)]

        code = aa.main(provider_argv(write_corpus_file(tmp_path, rows), tmp_path / "p.jsonl"))

        assert code == 0
        assert len(fake.calls) == 2

    def test_a_valid_corpus_still_runs(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Validation does not change the happy path."""
        fake = install_call_api(monkeypatch, FakeCallApi())

        code = aa.main(
            provider_argv(write_corpus_file(tmp_path, heldout_rows(3)), tmp_path / "p.jsonl")
        )

        assert code == 0
        assert len(fake.calls) == 3


class TestFetchHunksValidatesRows:
    @pytest.mark.parametrize(
        ("key", "value"),
        [*_BAD_ROWS, ("diff_hunk", 4), ("hunk_status", 4), ("hunk_status", ["fetched"])],
    )
    def test_a_bad_row_exits_two_before_any_call(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        key: str,
        value: Any,
    ) -> None:
        """Plan M1-T8: the scan runs on every row, so every row is checked first."""
        fake = FakeGraphql({"A": "@@ a", "B": "@@ b"})
        monkeypatch.setattr(cc, "gh_graphql", fake)
        rows = [corpus_row("A"), corpus_row("B")]
        rows[1][key] = value
        corpus = write_corpus(tmp_path / "c.jsonl", rows)
        out = tmp_path / "o.jsonl"

        code = cc.main(["fetch-hunks", "--corpus", str(corpus), "--output", str(out)])

        err = capsys.readouterr().err
        assert code == 2
        assert fake.calls == []
        assert not out.exists()
        assert key in err

    def test_a_missing_body_is_exit_two_not_a_key_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The reproduced KeyError, through fetch-hunks."""
        monkeypatch.setattr(cc, "gh_graphql", FakeGraphql({"A": "@@ a"}))
        row = corpus_row("A")
        del row["body"]
        corpus = write_corpus(tmp_path / "c.jsonl", [row])

        code = cc.main(
            ["fetch-hunks", "--corpus", str(corpus), "--output", str(tmp_path / "o.jsonl")]
        )

        assert code == 2
