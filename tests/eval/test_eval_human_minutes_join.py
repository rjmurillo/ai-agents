"""Tests for scripts/eval/eval_human_minutes_join.py (issue #5768)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest

EVAL_DIR = Path(__file__).resolve().parents[2] / "scripts" / "eval"
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

import _durable_outcome as durable  # noqa: E402
import _outcome_record as outcome  # noqa: E402
import eval_human_minutes_join as join  # noqa: E402

from tests.eval._durable_outcome_test_support import make_config, make_record  # noqa: E402


def _untimed(task: str, control: str, repeat: int = 0) -> dict[str, Any]:
    data = make_record(task_id=task, repeat=repeat, config=make_config(control=control))
    data["economics"] = {**data["economics"], "human_correction_minutes": None}
    return data


def _write_records(path: Path, rows: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return path


def _minutes(path: Path, rows: list[tuple[str, str, int, float]]) -> Path:
    body = [{"control": c, "task_id": t, "repeat": r, "minutes": m} for c, t, r, m in rows]
    path.write_text(json.dumps(body), encoding="utf-8")
    return path


def _read(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _run(*args: str | Path) -> int:
    return join.main([str(a) for a in args])


def test_a_timed_row_is_written_into_the_matching_record_only(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    records = _write_records(
        tmp_path / "in" / "current.jsonl", [_untimed("t1", "current"), _untimed("t2", "current")]
    )
    minutes = _minutes(tmp_path / "m.json", [("current", "t1", 0, 4.5)])

    code = _run("--records", records, "--minutes", minutes, "--output-dir", tmp_path / "out")

    assert code == join.EXIT_OK
    first, second = _read(tmp_path / "out" / "current.jsonl")
    assert first["economics"]["human_correction_minutes"] == 4.5
    assert second["economics"]["human_correction_minutes"] is None
    summary = json.loads(capsys.readouterr().out)
    assert (summary["records"], summary["timed"], summary["still_null"]) == (2, 1, 1)


def test_zero_minutes_is_written_as_a_timed_zero(tmp_path: Path) -> None:
    records = _write_records(tmp_path / "in" / "r.jsonl", [_untimed("t1", "reduced")])
    minutes = _minutes(tmp_path / "m.json", [("reduced", "t1", 0, 0.0)])

    assert _run("--records", records, "--minutes", minutes, "--output-dir", tmp_path / "o") == 0

    (row,) = _read(tmp_path / "o" / "r.jsonl")
    assert row["economics"]["human_correction_minutes"] == 0.0


def test_the_input_records_are_never_modified(tmp_path: Path) -> None:
    records = _write_records(tmp_path / "in" / "r.jsonl", [_untimed("t1", "reduced")])
    before = records.read_bytes()
    minutes = _minutes(tmp_path / "m.json", [("reduced", "t1", 0, 2.0)])

    _run("--records", records, "--minutes", minutes, "--output-dir", tmp_path / "o")

    assert records.read_bytes() == before


def test_timed_records_classify_through_the_real_report(tmp_path: Path) -> None:
    rows = [_untimed("t1", "current"), _untimed("t2", "current")]
    records = _write_records(tmp_path / "in" / "c.jsonl", rows)
    untimed = durable.build_report([outcome.parse_record(r) for r in rows])
    minutes = _minutes(tmp_path / "m.json", [("current", "t1", 0, 1.0), ("current", "t2", 0, 0.0)])

    _run("--records", records, "--minutes", minutes, "--output-dir", tmp_path / "o")

    timed = durable.build_report(
        [outcome.parse_record(r) for r in _read(tmp_path / "o" / "c.jsonl")]
    )
    assert untimed["durable_signals"]["human_correction_unmeasured"] == 2
    assert timed["durable_signals"]["human_correction_unmeasured"] == 0


def test_two_records_files_join_in_one_call(tmp_path: Path) -> None:
    cur = _write_records(tmp_path / "in" / "current.jsonl", [_untimed("t1", "current")])
    red = _write_records(tmp_path / "in" / "reduced.jsonl", [_untimed("t1", "reduced")])
    minutes = _minutes(tmp_path / "m.json", [("current", "t1", 0, 1.0), ("reduced", "t1", 0, 2.0)])

    code = _run("--records", cur, red, "--minutes", minutes, "--output-dir", tmp_path / "o")

    assert code == 0
    assert (
        _read(tmp_path / "o" / "current.jsonl")[0]["economics"]["human_correction_minutes"] == 1.0
    )
    assert (
        _read(tmp_path / "o" / "reduced.jsonl")[0]["economics"]["human_correction_minutes"] == 2.0
    )


def test_a_minutes_row_that_matches_no_record_exits_2_and_writes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    records = _write_records(tmp_path / "in" / "r.jsonl", [_untimed("t1", "reduced")])
    minutes = _minutes(
        tmp_path / "m.json", [("reduced", "t1", 0, 1.0), ("reduced", "typo", 0, 2.0)]
    )

    code = _run("--records", records, "--minutes", minutes, "--output-dir", tmp_path / "o")

    assert code == join.EXIT_CONFIG
    assert "match no record" in capsys.readouterr().err
    assert not (tmp_path / "o").exists()


def test_the_error_names_the_unmatched_cell(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    records = _write_records(tmp_path / "in" / "r.jsonl", [_untimed("t1", "reduced")])
    minutes = _minutes(tmp_path / "m.json", [("reduced", "typo", 3, 2.0)])

    _run("--records", records, "--minutes", minutes, "--output-dir", tmp_path / "o")

    assert "['reduced', 'typo', 3]" in capsys.readouterr().err


@pytest.mark.parametrize("content", ["not json", "[]", '[{"control": "x"}]'])
def test_a_bad_minutes_file_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], content: str
) -> None:
    records = _write_records(tmp_path / "in" / "r.jsonl", [_untimed("t1", "reduced")])
    bad = tmp_path / "m.json"
    bad.write_text(content, encoding="utf-8")

    assert _run("--records", records, "--minutes", bad, "--output-dir", tmp_path / "o") == 2
    assert capsys.readouterr().err.startswith("error:")


def test_a_missing_minutes_file_exits_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    records = _write_records(tmp_path / "in" / "r.jsonl", [_untimed("t1", "reduced")])

    code = _run("--records", records, "--minutes", tmp_path / "no.json", "--output-dir", tmp_path)

    assert code == 2 and "cannot read" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("content", "needle"),
    [
        ("", "no records"),
        ("{bad\n", "invalid JSON"),
        ("[1]\n", "expected an object"),
        ('{"a": 1}\n', "task_id"),
    ],
)
def test_a_bad_records_file_exits_2_naming_the_problem(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], content: str, needle: str
) -> None:
    records = tmp_path / "in" / "r.jsonl"
    records.parent.mkdir()
    records.write_text(content, encoding="utf-8")
    minutes = _minutes(tmp_path / "m.json", [("reduced", "t1", 0, 1.0)])

    code = _run("--records", records, "--minutes", minutes, "--output-dir", tmp_path / "o")

    assert code == 2 and needle in capsys.readouterr().err


def test_a_missing_records_file_exits_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    minutes = _minutes(tmp_path / "m.json", [("reduced", "t1", 0, 1.0)])

    code = _run(
        "--records", tmp_path / "no.jsonl", "--minutes", minutes, "--output-dir", tmp_path / "o"
    )

    assert code == 2 and "cannot read" in capsys.readouterr().err


def test_a_duplicate_record_cell_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    records = _write_records(
        tmp_path / "in" / "r.jsonl", [_untimed("t1", "reduced"), _untimed("t1", "reduced")]
    )
    minutes = _minutes(tmp_path / "m.json", [("reduced", "t1", 0, 1.0)])

    code = _run("--records", records, "--minutes", minutes, "--output-dir", tmp_path / "o")

    assert code == 2 and "duplicate record" in capsys.readouterr().err


def test_an_output_dir_that_holds_an_input_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    records = _write_records(tmp_path / "in" / "r.jsonl", [_untimed("t1", "reduced")])
    before = records.read_bytes()
    minutes = _minutes(tmp_path / "m.json", [("reduced", "t1", 0, 1.0)])

    code = _run("--records", records, "--minutes", minutes, "--output-dir", records.parent)

    assert code == 2 and "must not replace" in capsys.readouterr().err
    assert records.read_bytes() == before


def test_two_inputs_with_the_same_file_name_are_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    one = _write_records(tmp_path / "a" / "r.jsonl", [_untimed("t1", "current")])
    two = _write_records(tmp_path / "b" / "r.jsonl", [_untimed("t1", "reduced")])
    minutes = _minutes(tmp_path / "m.json", [("reduced", "t1", 0, 1.0)])

    code = _run("--records", one, two, "--minutes", minutes, "--output-dir", tmp_path / "o")

    assert code == 2 and "share a file name" in capsys.readouterr().err


def _timed(task: str, control: str, minutes: float) -> dict[str, Any]:
    data = _untimed(task, control)
    data["economics"] = {**data["economics"], "human_correction_minutes": minutes}
    return data


def test_a_second_join_does_not_replace_an_earlier_timed_value(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    records = _write_records(tmp_path / "in" / "r.jsonl", [_timed("t1", "reduced", 3.0)])
    minutes = _minutes(tmp_path / "m.json", [("reduced", "t1", 0, 9.0)])

    code = _run("--records", records, "--minutes", minutes, "--output-dir", tmp_path / "out")

    assert code == join.EXIT_CONFIG
    assert "--replace" in capsys.readouterr().err
    assert not (tmp_path / "out").exists()


def test_a_legacy_constant_zero_is_not_replaced_without_the_flag(tmp_path: Path) -> None:
    records = _write_records(tmp_path / "in" / "r.jsonl", [_timed("t1", "reduced", 0.0)])
    minutes = _minutes(tmp_path / "m.json", [("reduced", "t1", 0, 6.0)])

    code = _run("--records", records, "--minutes", minutes, "--output-dir", tmp_path / "out")

    assert code == join.EXIT_CONFIG


def test_replace_overwrites_a_held_value(tmp_path: Path) -> None:
    records = _write_records(tmp_path / "in" / "r.jsonl", [_timed("t1", "reduced", 3.0)])
    minutes = _minutes(tmp_path / "m.json", [("reduced", "t1", 0, 9.0)])

    code = _run(
        "--records", records, "--minutes", minutes, "--output-dir", tmp_path / "out", "--replace"
    )

    assert code == join.EXIT_OK
    (row,) = _read(tmp_path / "out" / "r.jsonl")
    assert row["economics"]["human_correction_minutes"] == 9.0


def test_a_record_without_a_minutes_row_keeps_its_held_value_and_needs_no_flag(
    tmp_path: Path,
) -> None:
    records = _write_records(
        tmp_path / "in" / "r.jsonl", [_timed("t1", "reduced", 3.0), _untimed("t2", "reduced")]
    )
    minutes = _minutes(tmp_path / "m.json", [("reduced", "t2", 0, 5.0)])

    code = _run("--records", records, "--minutes", minutes, "--output-dir", tmp_path / "out")

    assert code == join.EXIT_OK
    first, second = _read(tmp_path / "out" / "r.jsonl")
    assert first["economics"]["human_correction_minutes"] == 3.0
    assert second["economics"]["human_correction_minutes"] == 5.0


def test_a_failed_second_write_leaves_no_joined_copy_behind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    first = _write_records(tmp_path / "in" / "a.jsonl", [_untimed("t1", "current")])
    second = _write_records(tmp_path / "in" / "b.jsonl", [_untimed("t1", "reduced")])
    minutes = _minutes(tmp_path / "m.json", [("current", "t1", 0, 1.0), ("reduced", "t1", 0, 2.0)])
    real_fdopen = os.fdopen
    opened = []

    def failing_fdopen(fd: int, *args: Any, **kwargs: Any) -> Any:
        opened.append(fd)
        if len(opened) == 2:
            os.close(fd)
            raise OSError("disk full")
        return real_fdopen(fd, *args, **kwargs)

    monkeypatch.setattr(join.os, "fdopen", failing_fdopen)

    code = _run("--records", first, second, "--minutes", minutes, "--output-dir", tmp_path / "out")

    assert code == join.EXIT_CONFIG
    assert "disk full" in capsys.readouterr().err
    assert list((tmp_path / "out").iterdir()) == []
