"""bootstrap_eval: results-file parsing limits, --out name policy, and error names (issue #6666)."""

from __future__ import annotations

import json
import subprocess
import sys
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
DEEP = "[" * 200_000


def _run(capsys: Capsys, *argv: str) -> tuple[int, dict[str, Any]]:
    code = bootstrap_eval.main(list(argv))
    return code, json.loads(capsys.readouterr().out)


def _case(grader: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "id": "C1",
        "skill": "acme-skill",
        "source": "lens:ops",
        "prompt": "p",
        "grader": grader or {"kind": "contains_all", "terms": ["alpha"]},
    }


def _freeze(capsys: Capsys, tmp_path: Path, grader: dict[str, Any] | None = None) -> Path:
    cases = tmp_path / "cases.json"
    cases.write_text(json.dumps({"cases": [_case(grader)]}), encoding="utf-8")
    frozen = tmp_path / "frozen" / "f.json"
    assert _run(capsys, "freeze", "--cases", str(cases), "--out", str(frozen))[0] == 0
    return frozen


def _score(capsys: Capsys, frozen: Path, results_text: str, tmp_path: Path):
    results = tmp_path / "r.jsonl"
    results.write_text(results_text, encoding="utf-8")
    return _run(capsys, "score", "--frozen", str(frozen), "--results", str(results))


def _row(condition: str, output: str, ensure_ascii: bool = True) -> str:
    row = {"case_id": "C1", "condition": condition, "output": output}
    return json.dumps(row, ensure_ascii=ensure_ascii)


# --- splitlines ----------------------------------------------------------------


@pytest.mark.parametrize("separator", [" ", "\u0085", " ", "\x0c", "\x1c"])
def test_results_line_with_a_raw_unicode_separator_is_accepted(capsys, tmp_path, separator):
    frozen = _freeze(capsys, tmp_path)
    text = f"{_row('baseline', 'nope' + separator + 'x', False)}\n"
    text += f"{_row('with_skill', 'alpha' + separator + 'y', False)}\n"

    code, payload = _score(capsys, frozen, text, tmp_path)

    assert code == 0
    assert payload["examined"]["results"] == 2
    assert payload["cases"][0]["status"] == "gain"


def test_results_file_with_crlf_line_endings_still_parses(capsys, tmp_path):
    frozen = _freeze(capsys, tmp_path)
    text = f"{_row('baseline', 'nope')}\r\n{_row('with_skill', 'alpha')}\r\n"

    code, payload = _score(capsys, frozen, text, tmp_path)

    assert code == 0
    assert payload["examined"]["results"] == 2


def test_results_file_without_a_final_newline_still_parses(capsys, tmp_path):
    frozen = _freeze(capsys, tmp_path)
    text = f"{_row('baseline', 'nope')}\n{_row('with_skill', 'alpha')}"

    code, payload = _score(capsys, frozen, text, tmp_path)

    assert code == 0
    assert payload["examined"]["results"] == 2


# --- RecursionError ------------------------------------------------------------


def test_deeply_nested_results_line_is_a_config_error_not_a_crash(capsys, tmp_path):
    frozen = _freeze(capsys, tmp_path)

    code, payload = _score(capsys, frozen, DEEP + "\n", tmp_path)

    assert code == 2
    assert payload["error"] == "config"
    assert "results line 1 is not JSON" in payload["message"]


def test_deeply_nested_cases_file_is_a_config_error_not_a_crash(capsys, tmp_path):
    cases = tmp_path / "cases.json"
    cases.write_text(DEEP, encoding="utf-8")

    code, payload = _run(capsys, "freeze", "--cases", str(cases), "--out", str(tmp_path / "f.json"))

    assert code == 2
    assert payload["error"] == "config"


def test_deeply_nested_frozen_file_is_a_config_error_not_a_crash(capsys, tmp_path):
    frozen = tmp_path / "f.json"
    frozen.write_text(DEEP, encoding="utf-8")
    results = tmp_path / "r.jsonl"
    results.write_text("", encoding="utf-8")

    code, payload = _run(capsys, "score", "--frozen", str(frozen), "--results", str(results))

    assert code == 2
    assert payload["error"] == "config"


def test_deeply_nested_fenced_block_is_skipped_for_an_earlier_valid_one():
    output = '```json\n{"k": ["a"]}\n```\n```json\n' + DEEP + "\n```\n"

    assert bootstrap_eval.extract_last_json_object(output) == {"k": ["a"]}


# --- --out name and parent policy -----------------------------------------------


@pytest.mark.parametrize("name", [".", "..", ""])
def test_freeze_refuses_an_out_without_a_file_name(capsys, tmp_path, monkeypatch, name):
    cases = tmp_path / "cases.json"
    cases.write_text(json.dumps({"cases": [_case()]}), encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    code, payload = _run(capsys, "freeze", "--cases", str(cases), "--out", name)

    assert code == 2
    assert payload["error"] == "config"
    assert "must end in a file name" in payload["message"]


@pytest.mark.parametrize("tail", ["missing/..", "missing/sub/.."])
def test_freeze_with_a_dot_name_creates_no_directory(capsys, tmp_path, tail):
    cases = tmp_path / "cases.json"
    cases.write_text(json.dumps({"cases": [_case()]}), encoding="utf-8")

    code, payload = _run(capsys, "freeze", "--cases", str(cases), "--out", str(tmp_path / tail))

    assert code == 2
    assert payload["error"] == "config"
    assert not (tmp_path / "missing").exists()


def test_freeze_creates_a_missing_parent_for_a_real_name(capsys, tmp_path):
    cases = tmp_path / "cases.json"
    cases.write_text(json.dumps({"cases": [_case()]}), encoding="utf-8")
    out = tmp_path / "a" / "b" / "f.json"

    code, payload = _run(capsys, "freeze", "--cases", str(cases), "--out", str(out))

    assert code == 0
    assert out.is_file()
    assert payload["frozen"] == out.as_posix()


def test_check_out_path_returns_the_resolved_path_and_leaves_a_symlink_unfollowed(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    try:
        link.symlink_to(real, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")

    out = bootstrap_eval._check_out_path(link / "f.json", True)

    assert out == real.resolve() / "f.json"


def test_check_out_path_refuses_a_planted_final_symlink_before_resolving_it(tmp_path):
    target = tmp_path / "elsewhere.json"
    link = tmp_path / "f.json"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")

    with pytest.raises(bootstrap_eval.ConfigError, match="already exists"):
        bootstrap_eval._check_out_path(link, True)

    assert not target.exists()


def test_is_occupied_counts_a_dangling_symlink_and_a_file_but_not_a_gap(tmp_path):
    file = tmp_path / "file"
    file.write_text("x", encoding="utf-8")
    dangling = tmp_path / "dangling"
    try:
        dangling.symlink_to(tmp_path / "gone")
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")

    assert bootstrap_eval._is_occupied(file) is True
    assert bootstrap_eval._is_occupied(dangling) is True
    assert bootstrap_eval._is_occupied(tmp_path / "absent") is False


# --- error names and exit codes -------------------------------------------------


def test_regex_child_failure_is_exit_three_with_the_io_name(capsys, tmp_path, monkeypatch):
    frozen = _freeze(capsys, tmp_path, {"kind": "regex", "pattern": "alpha"})
    failed = subprocess.CompletedProcess([], 1, stdout="", stderr="boom")
    monkeypatch.setattr(bootstrap_eval.subprocess, "run", lambda *a, **k: failed)

    code, payload = _score(capsys, frozen, f"{_row('baseline', 'alpha')}\n", tmp_path)

    assert code == 3
    assert payload["error"] == "io"
    assert "regex grader child failed" in payload["message"]


def test_regex_child_that_cannot_start_is_exit_three(capsys, tmp_path, monkeypatch):
    frozen = _freeze(capsys, tmp_path, {"kind": "regex", "pattern": "alpha"})

    def cannot_start(*_a: Any, **_k: Any) -> None:
        raise OSError("exec format error")

    monkeypatch.setattr(bootstrap_eval.subprocess, "run", cannot_start)

    code, payload = _score(capsys, frozen, f"{_row('baseline', 'alpha')}\n", tmp_path)

    assert code == 3
    assert payload["error"] == "io"


def test_git_timeout_uses_the_git_name_and_exit_three(capsys, tmp_path, monkeypatch):
    cases = tmp_path / "cases.json"
    cases.write_text(json.dumps({"cases": [_case()]}), encoding="utf-8")

    def slow(*_a: Any, **_k: Any) -> None:
        raise subprocess.TimeoutExpired("git", 30)

    monkeypatch.setattr(bootstrap_eval.subprocess, "run", slow)

    code, payload = _run(capsys, "freeze", "--cases", str(cases), "--out", str(tmp_path / "f"))

    assert code == 3
    assert payload["error"] == "git"
    assert "timed out" in payload["message"]


def test_external_error_defaults_to_the_io_kind():
    assert bootstrap_eval.ExternalError("x").kind == "io"
    assert bootstrap_eval.ExternalError("x", "git").kind == "git"
