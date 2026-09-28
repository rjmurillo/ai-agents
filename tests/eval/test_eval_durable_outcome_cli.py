"""Tests for scripts/eval/eval_durable_outcome.py (REQ-042, DESIGN-040 "CLI").

Drives `main(argv)` against real JSONL files under `tmp_path`, asserting on
the process exit code and the printed JSON, per testing.md MUST-8 (assert on
the process exit code, not on a helper's return value).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tests.eval._durable_outcome_test_support import EVAL_DIR, cli, make_config, make_record

SCRIPT_PATH = EVAL_DIR / "eval_durable_outcome.py"


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")


def test_main_exit_0_on_verified_report(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    records_path = tmp_path / "records.jsonl"
    _write_jsonl(records_path, [make_record()])

    exit_code = cli.main(["--records", str(records_path)])

    assert exit_code == cli.EXIT_OK
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "VERIFIED"


def test_main_exit_1_on_unverified_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = make_record()
    data["durable"] = {**data["durable"], "residual_defects": None}
    records_path = tmp_path / "records.jsonl"
    _write_jsonl(records_path, [data])

    exit_code = cli.main(["--records", str(records_path)])

    assert exit_code == cli.EXIT_UNVERIFIED_OR_WORSE
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "UNVERIFIED"


def test_main_skips_blank_lines(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    records_path = tmp_path / "records.jsonl"
    records_path.write_text(
        "\n" + json.dumps(make_record()) + "\n\n" + json.dumps(make_record(task_id="t2")) + "\n\n",
        encoding="utf-8",
    )

    exit_code = cli.main(["--records", str(records_path)])

    assert exit_code == cli.EXIT_OK
    report = json.loads(capsys.readouterr().out)
    assert len(report["per_task"]) == 2


def test_main_exit_2_on_malformed_json_names_line_number(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    records_path = tmp_path / "records.jsonl"
    records_path.write_text(json.dumps(make_record()) + "\n{not json\n", encoding="utf-8")

    exit_code = cli.main(["--records", str(records_path)])

    assert exit_code == cli.EXIT_INPUT_ERROR
    stderr = capsys.readouterr().err
    assert f"{records_path}:2" in stderr


def test_main_exit_2_on_parse_refusal_names_line_number(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bad = make_record()
    bad["extra"] = 1
    records_path = tmp_path / "records.jsonl"
    _write_jsonl(records_path, [bad])

    exit_code = cli.main(["--records", str(records_path)])

    assert exit_code == cli.EXIT_INPUT_ERROR
    stderr = capsys.readouterr().err
    assert f"{records_path}:1" in stderr
    assert "unknown key" in stderr


def test_main_exit_2_on_missing_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    missing = tmp_path / "does-not-exist.jsonl"

    exit_code = cli.main(["--records", str(missing)])

    assert exit_code == cli.EXIT_INPUT_ERROR
    assert "cannot read" in capsys.readouterr().err


def test_main_exit_2_on_empty_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    records_path = tmp_path / "records.jsonl"
    records_path.write_text("\n\n", encoding="utf-8")

    exit_code = cli.main(["--records", str(records_path)])

    assert exit_code == cli.EXIT_INPUT_ERROR
    assert "no records found" in capsys.readouterr().err


def test_main_exit_0_on_better_comparison(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    baseline_path = tmp_path / "baseline.jsonl"
    candidate_path = tmp_path / "candidate.jsonl"
    baseline = make_record(config=make_config(control="reduced"))
    baseline["economics"] = {**baseline["economics"], "model_cost_usd": 1.0}
    candidate = make_record(config=make_config(control="full"))
    candidate["economics"] = {**candidate["economics"], "model_cost_usd": 0.1}
    _write_jsonl(baseline_path, [baseline])
    _write_jsonl(candidate_path, [candidate])

    exit_code = cli.main(
        ["--records", str(candidate_path), "--baseline", str(baseline_path)]
    )

    assert exit_code == cli.EXIT_OK
    comparison = json.loads(capsys.readouterr().out)
    assert comparison["result"] == "BETTER"


def test_main_exit_1_on_worse_comparison(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    baseline_path = tmp_path / "baseline.jsonl"
    candidate_path = tmp_path / "candidate.jsonl"
    baseline = make_record(config=make_config(control="reduced"))
    baseline["economics"] = {**baseline["economics"], "model_cost_usd": 0.1}
    candidate = make_record(config=make_config(control="full"))
    candidate["economics"] = {**candidate["economics"], "model_cost_usd": 1.0}
    _write_jsonl(baseline_path, [baseline])
    _write_jsonl(candidate_path, [candidate])

    exit_code = cli.main(
        ["--records", str(candidate_path), "--baseline", str(baseline_path)]
    )

    assert exit_code == cli.EXIT_UNVERIFIED_OR_WORSE
    comparison = json.loads(capsys.readouterr().out)
    assert comparison["result"] == "WORSE"


def test_main_exit_0_on_mixed_comparison(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    baseline_path = tmp_path / "baseline.jsonl"
    candidate_path = tmp_path / "candidate.jsonl"
    # Identical apart from `control`: dominates both ways -> MIXED (a tie).
    baseline = make_record(config=make_config(control="reduced"))
    candidate = make_record(config=make_config(control="full"))
    _write_jsonl(baseline_path, [baseline])
    _write_jsonl(candidate_path, [candidate])

    exit_code = cli.main(
        ["--records", str(candidate_path), "--baseline", str(baseline_path)]
    )

    assert exit_code == cli.EXIT_OK
    comparison = json.loads(capsys.readouterr().out)
    assert comparison["result"] == "MIXED"


def test_main_exit_1_on_unverified_comparison(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    baseline_path = tmp_path / "baseline.jsonl"
    candidate_path = tmp_path / "candidate.jsonl"
    baseline = make_record(config=make_config(control="reduced"))
    baseline["durable"] = {**baseline["durable"], "residual_defects": None}
    candidate = make_record(config=make_config(control="full"))
    _write_jsonl(baseline_path, [baseline])
    _write_jsonl(candidate_path, [candidate])

    exit_code = cli.main(
        ["--records", str(candidate_path), "--baseline", str(baseline_path)]
    )

    assert exit_code == cli.EXIT_UNVERIFIED_OR_WORSE
    comparison = json.loads(capsys.readouterr().out)
    assert comparison["result"] == "UNVERIFIED"


def test_main_exit_2_on_comparison_config_mismatch(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    baseline_path = tmp_path / "baseline.jsonl"
    candidate_path = tmp_path / "candidate.jsonl"
    baseline = make_record(config=make_config(control="reduced", harness="claude"))
    candidate = make_record(config=make_config(control="full", harness="codex"))
    _write_jsonl(baseline_path, [baseline])
    _write_jsonl(candidate_path, [candidate])

    exit_code = cli.main(
        ["--records", str(candidate_path), "--baseline", str(baseline_path)]
    )

    assert exit_code == cli.EXIT_INPUT_ERROR
    assert "harness" in capsys.readouterr().err


def test_main_exit_2_on_comparison_task_set_mismatch(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    baseline_path = tmp_path / "baseline.jsonl"
    candidate_path = tmp_path / "candidate.jsonl"
    baseline = make_record(task_id="t1", config=make_config(control="reduced"))
    candidate = make_record(task_id="t2", config=make_config(control="full"))
    _write_jsonl(baseline_path, [baseline])
    _write_jsonl(candidate_path, [candidate])

    exit_code = cli.main(
        ["--records", str(candidate_path), "--baseline", str(baseline_path)]
    )

    assert exit_code == cli.EXIT_INPUT_ERROR
    assert "task sets differ" in capsys.readouterr().err


def test_script_run_as_main_exits_0_on_pass_report(tmp_path: Path) -> None:
    # Drives the `if __name__ == "__main__":` guard through a real
    # subprocess, matching the process boundary an operator actually invokes.
    records_path = tmp_path / "records.jsonl"
    _write_jsonl(records_path, [make_record()])

    completed = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--records", str(records_path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    assert completed.returncode == cli.EXIT_OK
    assert json.loads(completed.stdout)["status"] == "VERIFIED"


def test_main_exit_2_on_invalid_utf8(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    records_path = tmp_path / "records.jsonl"
    records_path.write_bytes(b"\xff\xfe not utf-8\n")

    exit_code = cli.main(["--records", str(records_path)])

    assert exit_code == cli.EXIT_INPUT_ERROR
    assert "cannot read" in capsys.readouterr().err
