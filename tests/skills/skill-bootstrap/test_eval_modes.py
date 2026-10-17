"""bootstrap_eval: knowledge-mode gate and the regex run-time deadline."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

import pytest

_SCRIPTS = (
    Path(__file__).resolve().parents[3] / ".claude" / "skills" / "skill-bootstrap" / "scripts"
)
sys.path.insert(0, str(_SCRIPTS))
try:
    import bootstrap_eval
finally:
    sys.path.remove(str(_SCRIPTS))

Capsys = pytest.CaptureFixture[str]


def _run(capsys: Capsys, *argv: str) -> tuple[int, dict[str, Any]]:
    code = bootstrap_eval.main(list(argv))
    return code, json.loads(capsys.readouterr().out)


def _case(case_id: str) -> dict[str, Any]:
    return {
        "id": case_id,
        "skill": "acme-skill",
        "source": "lens:ops",
        "prompt": "p",
        "grader": {"kind": "contains_all", "terms": ["alpha"]},
    }


def _frozen_and_results(
    capsys: Capsys, tmp_path: Path, rows: list[tuple[str, str, str]]
) -> tuple[Path, Path]:
    cases = tmp_path / "cases.json"
    cases.write_text(json.dumps({"cases": [_case("C1"), _case("C2")]}), encoding="utf-8")
    frozen = tmp_path / "out" / "frozen.json"
    assert _run(capsys, "freeze", "--cases", str(cases), "--out", str(frozen))[0] == 0
    results = tmp_path / "r.jsonl"
    lines = [{"case_id": c, "condition": k, "output": o} for c, k, o in rows]
    results.write_text("\n".join(json.dumps(r) for r in lines) + "\n", encoding="utf-8")
    return frozen, results


# C1 gains, C2 is no_gap (baseline already passes).
ROWS = [
    ("C1", "baseline", "nope"),
    ("C1", "with_skill", "alpha"),
    ("C2", "baseline", "alpha"),
    ("C2", "with_skill", "alpha"),
]


def test_workflow_mode_is_the_default_and_tolerates_no_gap(capsys, tmp_path):
    frozen, results = _frozen_and_results(capsys, tmp_path, ROWS)

    code, payload = _run(capsys, "score", "--frozen", str(frozen), "--results", str(results))

    assert code == 0
    assert payload["mode"] == "workflow"
    assert payload["failing_cases"] == []


def test_knowledge_mode_fails_a_no_gap_case_and_lists_it(capsys, tmp_path):
    frozen, results = _frozen_and_results(capsys, tmp_path, ROWS)

    code, payload = _run(
        capsys, "score", "--frozen", str(frozen), "--results", str(results), "--mode", "knowledge"
    )

    assert code == 1
    assert payload["mode"] == "knowledge"
    assert payload["failing_cases"] == ["C2"]


def test_knowledge_mode_passes_when_every_case_gains(capsys, tmp_path):
    rows = [
        (c, k, "alpha" if k == "with_skill" else "x")
        for c in ("C1", "C2")
        for k in ("baseline", "with_skill")
    ]
    frozen, results = _frozen_and_results(capsys, tmp_path, rows)

    code, payload = _run(
        capsys, "score", "--frozen", str(frozen), "--results", str(results), "--mode", "knowledge"
    )

    assert code == 0
    assert payload["failing_cases"] == []


def test_workflow_mode_lists_regression_in_failing_cases(capsys, tmp_path):
    rows = [
        (c, k, "alpha" if k == "baseline" else "x")
        for c in ("C1", "C2")
        for k in ("baseline", "with_skill")
    ]
    frozen, results = _frozen_and_results(capsys, tmp_path, rows)

    code, payload = _run(capsys, "score", "--frozen", str(frozen), "--results", str(results))

    assert code == 1
    assert payload["failing_cases"] == ["C1", "C2"]


def test_unknown_mode_is_rejected_by_argparse():
    with pytest.raises(SystemExit) as exc:
        bootstrap_eval.main(["score", "--frozen", "f", "--results", "r", "--mode", "other"])

    assert exc.value.code == 2


@pytest.mark.parametrize("flag", ["--min", "--res"])
def test_abbreviated_flags_are_rejected(flag):
    with pytest.raises(SystemExit) as exc:
        bootstrap_eval.main(["score", "--frozen", "f", flag, "x"])

    assert exc.value.code == 2


# --- regex deadline -----------------------------------------------------------


def test_regex_timeout_grades_as_non_match_and_warns(monkeypatch, capsys):
    monkeypatch.setattr(bootstrap_eval, "REGEX_TIMEOUT_S", 0.5)
    grade = bootstrap_eval.compile_grader({"kind": "regex", "pattern": r"\s*\s*\s*x"})

    started = time.monotonic()
    matched = grade(" " * 3000)

    assert matched is False
    assert time.monotonic() - started < 10
    assert "regex timed out after 0.5 s" in capsys.readouterr().err


def test_regex_match_and_miss_through_child_process():
    grade = bootstrap_eval.compile_grader({"kind": "regex", "pattern": "a+b", "ignore_case": True})

    assert grade("xxAAb") is True
    assert grade("xxAA") is False


def test_regex_child_failure_is_a_config_error(monkeypatch):
    monkeypatch.setattr(bootstrap_eval, "REGEX_CHILD", "raise SystemExit(3)")
    grade = bootstrap_eval.compile_grader({"kind": "regex", "pattern": "a"})

    with pytest.raises(bootstrap_eval.ConfigError, match="child failed"):
        grade("a")
