# taste-lint: ignore file-size, one suite covers every grader, status, and refusal path.
"""Behavior tests for bootstrap_eval: graders, freeze, and score."""

from __future__ import annotations

import hashlib
import json
import runpy
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from bootstrap_helpers import symlink_or_skip

_SCRIPTS = (
    Path(__file__).resolve().parents[3] / ".claude" / "skills" / "skill-bootstrap" / "scripts"
)
sys.path.insert(0, str(_SCRIPTS))
try:
    import bootstrap_eval
finally:
    sys.path.remove(str(_SCRIPTS))

Capsys = pytest.CaptureFixture[str]
Result = tuple[int, dict[str, Any]]


# --- helpers ----------------------------------------------------------------


def make_case(
    case_id: str = "C1",
    skill: str = "acme-skill",
    grader: Any = None,
    source: Any = "lens:ops",
    prompt: Any = "Do the thing.",
) -> dict[str, Any]:
    default = {"kind": "contains_all", "terms": ["alpha"]}
    return {
        "id": case_id,
        "skill": skill,
        "source": source,
        "prompt": prompt,
        "grader": default if grader is None else grader,
    }


def write_json(path: Path, data: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def run(capsys: Capsys, *argv: str) -> Result:
    code = bootstrap_eval.main(list(argv))
    return code, json.loads(capsys.readouterr().out)


def freeze_cases(
    capsys: Capsys, tmp_path: Path, cases: list[Any], name: str = "frozen.json"
) -> Path:
    cases_file = write_json(tmp_path / f"in-{name}", {"cases": cases})
    out = tmp_path / "out" / name
    code, _ = run(capsys, "freeze", "--cases", str(cases_file), "--out", str(out))
    assert code == 0
    return out


def write_results(path: Path, rows: list[Any]) -> Path:
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    return path


def result(case_id: str, condition: str, output: str) -> dict[str, str]:
    return {"case_id": case_id, "condition": condition, "output": output}


def score(capsys: Capsys, frozen: Path, results: Path, *extra: str) -> Result:
    return run(capsys, "score", "--frozen", str(frozen), "--results", str(results), *extra)


def scored_row(
    capsys: Capsys, tmp_path: Path, baseline: list[str], with_skill: list[str]
) -> tuple[int, dict[str, Any]]:
    """Score one alpha-grader case C1 with the given outputs per condition."""
    frozen = freeze_cases(capsys, tmp_path, [make_case()])
    rows = [result("C1", "baseline", o) for o in baseline]
    rows += [result("C1", "with_skill", o) for o in with_skill]
    code, payload = score(capsys, frozen, write_results(tmp_path / "r.jsonl", rows))
    return code, payload["cases"][0]


def git_init(path: Path) -> Path:
    path.mkdir(parents=True)
    subprocess.run(
        ["git", "-C", str(path), "init", "-q"],
        check=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    return path


def fenced(body: str) -> str:
    return f"```json\n{body}\n```"


# --- graders: contains_all --------------------------------------------------


def test_contains_all_passes_when_every_term_present_ignoring_case() -> None:
    grade = bootstrap_eval.compile_grader({"kind": "contains_all", "terms": ["Alpha", "beta"]})

    assert grade("BETA then alpha") is True


def test_contains_all_fails_when_one_term_missing() -> None:
    grade = bootstrap_eval.compile_grader({"kind": "contains_all", "terms": ["alpha", "beta"]})

    assert grade("only alpha here") is False


def test_contains_all_fails_on_empty_output() -> None:
    grade = bootstrap_eval.compile_grader({"kind": "contains_all", "terms": ["alpha"]})

    assert grade("") is False


@pytest.mark.parametrize(
    "grader",
    [
        {"kind": "contains_all"},
        {"kind": "contains_all", "terms": []},
        {"kind": "contains_all", "terms": "alpha"},
        {"kind": "contains_all", "terms": ["alpha", "  "]},
        {"kind": "contains_all", "terms": ["alpha", 3]},
        {"kind": "contains_all", "terms": ["alpha"], "extra": 1},
    ],
)
def test_contains_all_rejects_bad_spec(grader: dict[str, Any]) -> None:
    with pytest.raises(bootstrap_eval.ConfigError):
        bootstrap_eval.compile_grader(grader)


# --- graders: regex ---------------------------------------------------------


def test_regex_passes_when_pattern_found() -> None:
    grade = bootstrap_eval.compile_grader({"kind": "regex", "pattern": r"v\d+\.\d+"})

    assert grade("release v1.20 ships") is True


def test_regex_fails_when_pattern_absent() -> None:
    grade = bootstrap_eval.compile_grader({"kind": "regex", "pattern": r"v\d+\.\d+"})

    assert grade("no version here") is False


def test_regex_is_case_sensitive_by_default() -> None:
    grade = bootstrap_eval.compile_grader({"kind": "regex", "pattern": "alpha"})

    assert grade("ALPHA") is False


def test_regex_ignore_case_true_matches_other_case() -> None:
    spec = {"kind": "regex", "pattern": "alpha", "ignore_case": True}

    assert bootstrap_eval.compile_grader(spec)("ALPHA") is True


@pytest.mark.parametrize(
    "grader",
    [
        {"kind": "regex"},
        {"kind": "regex", "pattern": ""},
        {"kind": "regex", "pattern": 5},
        {"kind": "regex", "pattern": "("},
        {"kind": "regex", "pattern": "a", "ignore_case": "yes"},
        {"kind": "regex", "pattern": "a", "flags": "i"},
    ],
)
def test_regex_rejects_bad_spec(grader: dict[str, Any]) -> None:
    with pytest.raises(bootstrap_eval.ConfigError):
        bootstrap_eval.compile_grader(grader)


# --- graders: json_set_f1 ---------------------------------------------------

STALE = {"kind": "json_set_f1", "key": "stale", "gold": ["a", "b"]}


def test_json_set_f1_passes_on_exact_set_in_any_order() -> None:
    grade = bootstrap_eval.compile_grader(STALE)

    assert grade("text\n" + fenced('{"stale": ["b", "a"]}')) is True


def test_json_set_f1_fails_below_default_threshold_of_one() -> None:
    grade = bootstrap_eval.compile_grader(STALE)

    assert grade(fenced('{"stale": ["a"]}')) is False


def test_json_set_f1_passes_partial_match_at_or_above_threshold() -> None:
    spec = {"kind": "json_set_f1", "key": "k", "gold": ["a", "b", "c", "d"], "threshold": 0.8}

    assert bootstrap_eval.compile_grader(spec)(fenced('{"k": ["a", "b", "c"]}')) is True


def test_json_set_f1_fails_partial_match_below_threshold() -> None:
    spec = {"kind": "json_set_f1", "key": "k", "gold": ["a", "b", "c", "d"], "threshold": 0.9}

    assert bootstrap_eval.compile_grader(spec)(fenced('{"k": ["a", "b", "c"]}')) is False


def test_json_set_f1_penalizes_extra_items() -> None:
    grade = bootstrap_eval.compile_grader(STALE)

    assert grade(fenced('{"stale": ["a", "b", "c", "d"]}')) is False


def test_json_set_f1_fails_when_output_has_no_block() -> None:
    assert bootstrap_eval.compile_grader(STALE)('{"stale": ["a", "b"]} but not fenced') is False


def test_json_set_f1_ignores_blocks_with_other_language_tag() -> None:
    output = '```python\n{"stale": ["a", "b"]}\n```'

    assert bootstrap_eval.compile_grader(STALE)(output) is False


def test_json_set_f1_fails_when_key_missing() -> None:
    assert bootstrap_eval.compile_grader(STALE)(fenced('{"other": ["a", "b"]}')) is False


@pytest.mark.parametrize("value", ['"a"', "5", "null", '[1, "a"]', '[["a"], "b"]'])
def test_json_set_f1_fails_when_value_is_not_a_list_of_strings(value: str) -> None:
    assert bootstrap_eval.compile_grader(STALE)(fenced(f'{{"stale": {value}}}')) is False


def test_json_set_f1_uses_last_of_several_blocks() -> None:
    output = fenced('{"stale": ["a", "b"]}') + "\nrevised:\n" + fenced('{"stale": ["z"]}')

    assert bootstrap_eval.compile_grader(STALE)(output) is False


def test_json_set_f1_last_block_wins_when_it_is_the_correct_one() -> None:
    output = fenced('{"stale": ["z"]}') + "\nrevised:\n" + fenced('{"stale": ["a", "b"]}')

    assert bootstrap_eval.compile_grader(STALE)(output) is True


def test_json_set_f1_skips_invalid_json_block_after_valid_one() -> None:
    output = fenced('{"stale": ["a", "b"]}') + "\n" + fenced("{not json")

    assert bootstrap_eval.compile_grader(STALE)(output) is True


def test_json_set_f1_fails_when_only_block_is_invalid_json() -> None:
    assert bootstrap_eval.compile_grader(STALE)(fenced("{not json")) is False


def test_json_set_f1_skips_block_that_is_not_an_object() -> None:
    output = fenced('{"stale": ["a", "b"]}') + "\n" + fenced('["a", "b"]')

    assert bootstrap_eval.compile_grader(STALE)(output) is True


def test_json_set_f1_strips_whitespace_around_items() -> None:
    assert bootstrap_eval.compile_grader(STALE)(fenced('{"stale": [" a ", "b"]}')) is True


def test_json_set_f1_empty_gold_passes_on_empty_list() -> None:
    spec = {"kind": "json_set_f1", "key": "stale", "gold": []}

    assert bootstrap_eval.compile_grader(spec)(fenced('{"stale": []}')) is True


def test_json_set_f1_empty_gold_fails_on_non_empty_list() -> None:
    spec = {"kind": "json_set_f1", "key": "stale", "gold": []}

    assert bootstrap_eval.compile_grader(spec)(fenced('{"stale": ["a"]}')) is False


def test_json_set_f1_empty_prediction_fails_non_empty_gold() -> None:
    assert bootstrap_eval.compile_grader(STALE)(fenced('{"stale": []}')) is False


def test_set_f1_values() -> None:
    assert bootstrap_eval.set_f1({"a", "b"}, {"a", "b"}) == 1.0
    assert bootstrap_eval.set_f1(set(), set()) == 1.0
    assert bootstrap_eval.set_f1({"x"}, {"a"}) == 0.0
    assert bootstrap_eval.set_f1({"a"}, {"a", "b"}) == pytest.approx(2 / 3)


@pytest.mark.parametrize(
    "grader",
    [
        {"kind": "json_set_f1", "gold": ["a"]},
        {"kind": "json_set_f1", "key": "", "gold": ["a"]},
        {"kind": "json_set_f1", "key": "k"},
        {"kind": "json_set_f1", "key": "k", "gold": "a"},
        {"kind": "json_set_f1", "key": "k", "gold": ["a", ""]},
        {"kind": "json_set_f1", "key": "k", "gold": ["a"], "threshold": 0},
        {"kind": "json_set_f1", "key": "k", "gold": ["a"], "threshold": 1.5},
        {"kind": "json_set_f1", "key": "k", "gold": ["a"], "threshold": "0.8"},
        {"kind": "json_set_f1", "key": "k", "gold": ["a"], "threshold": True},
        {"kind": "json_set_f1", "key": "k", "gold": ["a"], "extra": 1},
    ],
)
def test_json_set_f1_rejects_bad_spec(grader: dict[str, Any]) -> None:
    with pytest.raises(bootstrap_eval.ConfigError):
        bootstrap_eval.compile_grader(grader)


@pytest.mark.parametrize("grader", ["contains_all", None, {}, {"kind": "fuzzy"}, {"kind": 3}])
def test_compile_grader_rejects_unknown_or_malformed_kind(grader: Any) -> None:
    with pytest.raises(bootstrap_eval.ConfigError):
        bootstrap_eval.compile_grader(grader)


# --- freeze: success --------------------------------------------------------


def test_freeze_writes_sorted_cases_schema_and_digest(capsys: Capsys, tmp_path: Path) -> None:
    cases = [make_case("C2", "acme-b"), make_case("C1", "acme-a")]
    cases_file = write_json(tmp_path / "in.json", {"cases": cases})
    out = tmp_path / "frozen.json"

    code, payload = run(capsys, "freeze", "--cases", str(cases_file), "--out", str(out))

    record = json.loads(out.read_text(encoding="utf-8"))
    assert code == 0
    assert record["schema"] == "skill-bootstrap-eval/1"
    assert [c["id"] for c in record["cases"]] == ["C1", "C2"]
    assert record["frozen_at"].endswith("Z")
    assert payload["examined"] == {"cases": 2}
    assert payload["skills"] == ["acme-a", "acme-b"]
    assert payload["sha256"] == record["sha256"]


def test_freeze_digest_is_sha256_of_canonical_sorted_cases(capsys: Capsys, tmp_path: Path) -> None:
    cases = [make_case("C2"), make_case("C1")]
    cases_file = write_json(tmp_path / "in.json", {"cases": cases})
    out = tmp_path / "frozen.json"

    run(capsys, "freeze", "--cases", str(cases_file), "--out", str(out))

    ordered = sorted(cases, key=lambda c: c["id"])
    canonical = json.dumps(ordered, sort_keys=True, separators=(",", ":"))
    expected = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    assert json.loads(out.read_text(encoding="utf-8"))["sha256"] == expected


def test_freeze_digest_ignores_input_order(capsys: Capsys, tmp_path: Path) -> None:
    a = freeze_cases(capsys, tmp_path, [make_case("C1"), make_case("C2")], "a.json")
    b = freeze_cases(capsys, tmp_path, [make_case("C2"), make_case("C1")], "b.json")

    sha = [json.loads(p.read_text(encoding="utf-8"))["sha256"] for p in (a, b)]
    assert sha[0] == sha[1]


def test_freeze_creates_missing_parent_directories(capsys: Capsys, tmp_path: Path) -> None:
    cases_file = write_json(tmp_path / "in.json", {"cases": [make_case()]})
    out = tmp_path / "a" / "b" / "frozen.json"

    code, _ = run(capsys, "freeze", "--cases", str(cases_file), "--out", str(out))

    assert code == 0
    assert out.is_file()


@pytest.mark.parametrize("source", ["correction:PR-12", "lens:release", "outcome:ISSUE-3"])
def test_freeze_accepts_each_source_prefix(capsys: Capsys, tmp_path: Path, source: str) -> None:
    cases_file = write_json(tmp_path / "in.json", {"cases": [make_case(source=source)]})

    code, _ = run(capsys, "freeze", "--cases", str(cases_file), "--out", str(tmp_path / "f.json"))

    assert code == 0


# --- freeze: refusals -------------------------------------------------------


def test_freeze_refuses_existing_out_and_leaves_it_unchanged(
    capsys: Capsys, tmp_path: Path
) -> None:
    cases_file = write_json(tmp_path / "in.json", {"cases": [make_case()]})
    out = tmp_path / "frozen.json"
    out.write_text("keep me", encoding="utf-8")

    code, payload = run(capsys, "freeze", "--cases", str(cases_file), "--out", str(out))

    assert code == 2
    assert "immutable" in payload["message"]
    assert out.read_text(encoding="utf-8") == "keep me"


def test_freeze_refuses_second_freeze_to_same_path(capsys: Capsys, tmp_path: Path) -> None:
    out = freeze_cases(capsys, tmp_path, [make_case()])
    cases_file = tmp_path / "in-frozen.json"
    before = out.read_text(encoding="utf-8")

    code, _ = run(capsys, "freeze", "--cases", str(cases_file), "--out", str(out))

    assert code == 2
    assert out.read_text(encoding="utf-8") == before


def test_freeze_refuses_out_inside_git_work_tree(capsys: Capsys, tmp_path: Path) -> None:
    repo = git_init(tmp_path / "repo")
    cases_file = write_json(tmp_path / "in.json", {"cases": [make_case()]})
    out = repo / "evals" / "frozen.json"

    code, payload = run(capsys, "freeze", "--cases", str(cases_file), "--out", str(out))

    assert code == 2
    assert "--allow-in-repo" in payload["message"]
    assert not out.exists()
    assert not out.parent.exists()


def test_freeze_allows_out_inside_git_work_tree_with_flag(capsys: Capsys, tmp_path: Path) -> None:
    repo = git_init(tmp_path / "repo")
    cases_file = write_json(tmp_path / "in.json", {"cases": [make_case()]})
    out = repo / "evals" / "frozen.json"

    code, _ = run(
        capsys, "freeze", "--cases", str(cases_file), "--out", str(out), "--allow-in-repo"
    )

    assert code == 0
    assert out.is_file()


def test_freeze_allows_out_outside_git_work_tree(capsys: Capsys, tmp_path: Path) -> None:
    git_init(tmp_path / "repo")
    cases_file = write_json(tmp_path / "in.json", {"cases": [make_case()]})

    code, _ = run(
        capsys,
        "freeze",
        "--cases",
        str(cases_file),
        "--out",
        str(tmp_path / "elsewhere" / "f.json"),
    )

    assert code == 0


def test_freeze_fails_closed_when_git_is_missing(
    capsys: Capsys, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_git(*_args: Any, **_kwargs: Any) -> None:
        raise FileNotFoundError("git")

    monkeypatch.setattr(bootstrap_eval.subprocess, "run", no_git)
    cases_file = write_json(tmp_path / "in.json", {"cases": [make_case()]})
    out = tmp_path / "f.json"

    code, payload = run(capsys, "freeze", "--cases", str(cases_file), "--out", str(out))

    assert code == 3
    assert payload["error"] == "external"
    assert "git" in payload["message"]
    assert not out.exists()


def test_freeze_fails_closed_when_git_fails_for_another_reason(
    capsys: Capsys, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    failed = subprocess.CompletedProcess([], 128, stdout="", stderr="fatal: unsafe repository")
    monkeypatch.setattr(bootstrap_eval.subprocess, "run", lambda *a, **k: failed)
    cases_file = write_json(tmp_path / "in.json", {"cases": [make_case()]})
    out = tmp_path / "f.json"

    code, payload = run(capsys, "freeze", "--cases", str(cases_file), "--out", str(out))

    assert code == 3
    assert payload["error"] == "external"
    assert "unsafe repository" in payload["message"]
    assert not out.exists()


def test_freeze_reports_write_failure_as_exit_three(capsys: Capsys, tmp_path: Path) -> None:
    blocker = tmp_path / "blocker"
    blocker.write_text("a file, not a directory", encoding="utf-8")
    cases_file = write_json(tmp_path / "in.json", {"cases": [make_case()]})

    code, payload = run(
        capsys,
        "freeze",
        "--cases",
        str(cases_file),
        "--out",
        str(blocker / "f.json"),
        "--allow-in-repo",
    )

    assert code == 3
    assert payload["error"] == "external"


def test_freeze_reports_a_denied_write_as_exit_three(
    capsys: Capsys, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def denied(*_args: Any, **_kwargs: Any) -> None:
        raise PermissionError("denied")

    cases_file = write_json(tmp_path / "in.json", {"cases": [make_case()]})
    monkeypatch.setattr(bootstrap_eval.Path, "mkdir", denied)

    code, payload = run(
        capsys, "freeze", "--cases", str(cases_file), "--out", str(tmp_path / "f.json"),
        "--allow-in-repo",
    )  # fmt: skip

    assert code == 3
    assert payload["error"] == "external"
    assert "denied" in payload["message"]


def test_freeze_refuses_a_dangling_symlink_that_appears_after_the_check(
    capsys: Capsys, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cases_file = write_json(tmp_path / "in.json", {"cases": [make_case()]})
    out = tmp_path / "f.json"
    monkeypatch.setattr(
        bootstrap_eval, "_check_out_path", lambda *_: symlink_or_skip(out, tmp_path / "gone")
    )

    code, payload = run(
        capsys, "freeze", "--cases", str(cases_file), "--out", str(out), "--allow-in-repo"
    )

    assert code == 2
    assert payload["error"] == "config"


def test_freeze_reports_git_that_cannot_start_as_exit_three(
    capsys: Capsys, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def not_executable(*_args: Any, **_kwargs: Any) -> None:
        raise PermissionError("git")

    monkeypatch.setattr(bootstrap_eval.subprocess, "run", not_executable)
    cases_file = write_json(tmp_path / "in.json", {"cases": [make_case()]})

    code, payload = run(capsys, "freeze", "--cases", str(cases_file), "--out", str(tmp_path / "f"))

    assert code == 3
    assert payload["error"] == "external"


def test_unexpected_os_error_is_exit_two(capsys: Capsys, monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(_args: Any) -> None:
        raise OSError("disk gone")

    monkeypatch.setattr(bootstrap_eval, "freeze", broken)

    code, payload = run(capsys, "freeze", "--cases", "c", "--out", "o")

    assert code == 2
    assert payload["error"] == "io"


def test_freeze_refuses_an_out_that_appears_after_the_check(
    capsys: Capsys, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cases_file = write_json(tmp_path / "in.json", {"cases": [make_case()]})
    out = tmp_path / "f.json"
    monkeypatch.setattr(bootstrap_eval, "_check_out_path", lambda *_: out.write_text("x"))

    code, payload = run(
        capsys, "freeze", "--cases", str(cases_file), "--out", str(out), "--allow-in-repo"
    )

    assert code == 2
    assert payload["error"] == "config"
    assert out.read_text() == "x"


# --- freeze: malformed cases ------------------------------------------------


def freeze_raw(capsys: Capsys, tmp_path: Path, raw: Any) -> tuple[int, dict[str, Any], Path]:
    cases_file = write_json(tmp_path / "in.json", raw)
    out = tmp_path / "f.json"
    code, payload = run(capsys, "freeze", "--cases", str(cases_file), "--out", str(out))
    return code, payload, out


@pytest.mark.parametrize(
    "raw",
    [
        [],
        {},
        {"cases": []},
        {"cases": "x"},
        {"cases": ["not an object"]},
        {"cases": [{"id": "C1"}]},
        {"cases": [{**make_case(), "note": "extra"}]},
        {"cases": [make_case(prompt="   ")]},
        {"cases": [make_case(prompt=5)]},
        {"cases": [make_case(case_id="")]},
        {"cases": [make_case(skill="")]},
        {"cases": [make_case(source="memory:x")]},
        {"cases": [make_case(source="lens:")]},
        {"cases": [make_case(source="lens")]},
        {"cases": [make_case(source=7)]},
        {"cases": [make_case("C1"), make_case("C1")]},
        {"cases": [make_case(grader={"kind": "fuzzy"})]},
        {"cases": [make_case(grader={"kind": "regex", "pattern": "("})]},
        {"cases": [make_case(grader="contains_all")]},
    ],
)
def test_freeze_rejects_malformed_cases_without_writing(
    capsys: Capsys, tmp_path: Path, raw: Any
) -> None:
    code, payload, out = freeze_raw(capsys, tmp_path, raw)

    assert code == 2
    assert payload["error"] == "config"
    assert not out.exists()


def test_freeze_names_the_duplicate_ids(capsys: Capsys, tmp_path: Path) -> None:
    raw = {"cases": [make_case("C1"), make_case("C1"), make_case("C2")]}

    _, payload, _ = freeze_raw(capsys, tmp_path, raw)

    assert "C1" in payload["message"]
    assert "C2" not in payload["message"]


def test_freeze_names_the_case_with_the_bad_grader(capsys: Capsys, tmp_path: Path) -> None:
    raw = {"cases": [make_case("C9", grader={"kind": "nope"})]}

    _, payload, _ = freeze_raw(capsys, tmp_path, raw)

    assert "C9" in payload["message"]
    assert "nope" in payload["message"]


def test_freeze_rejects_cases_file_that_is_not_json(capsys: Capsys, tmp_path: Path) -> None:
    cases_file = tmp_path / "in.json"
    cases_file.write_text("{oops", encoding="utf-8")

    code, payload = run(
        capsys, "freeze", "--cases", str(cases_file), "--out", str(tmp_path / "f.json")
    )

    assert code == 2
    assert "cannot read cases file" in payload["message"]


def test_freeze_rejects_missing_cases_file(capsys: Capsys, tmp_path: Path) -> None:
    code, _ = run(
        capsys, "freeze", "--cases", str(tmp_path / "none.json"), "--out", str(tmp_path / "f.json")
    )

    assert code == 2


# --- score: statuses --------------------------------------------------------


def test_status_gain_when_with_skill_beats_baseline(capsys: Capsys, tmp_path: Path) -> None:
    code, row = scored_row(capsys, tmp_path, ["nope"], ["alpha"])

    assert code == 0
    assert row["status"] == "gain"
    assert row["baseline_pass_rate"] == 0.0
    assert row["with_skill_pass_rate"] == 1.0
    assert row["delta"] == 1.0


def test_status_no_gap_when_baseline_already_passes(capsys: Capsys, tmp_path: Path) -> None:
    code, row = scored_row(capsys, tmp_path, ["alpha"], ["alpha"])

    assert code == 0
    assert row["status"] == "no_gap"
    assert row["delta"] == 0.0


def test_status_regression_when_with_skill_is_worse(capsys: Capsys, tmp_path: Path) -> None:
    code, row = scored_row(capsys, tmp_path, ["alpha", "nope"], ["nope", "nope"])

    assert code == 1
    assert row["status"] == "regression"
    assert row["delta"] == -0.5


def test_status_regression_wins_over_no_gap_when_baseline_perfect(
    capsys: Capsys, tmp_path: Path
) -> None:
    _, row = scored_row(capsys, tmp_path, ["alpha"], ["nope"])

    assert row["status"] == "regression"


def test_status_flat_when_equal_and_baseline_below_one(capsys: Capsys, tmp_path: Path) -> None:
    _, row = scored_row(capsys, tmp_path, ["nope"], ["nope"])

    assert row["status"] == "flat"
    assert row["delta"] == 0.0


def test_status_flat_when_equal_partial_rates(capsys: Capsys, tmp_path: Path) -> None:
    _, row = scored_row(capsys, tmp_path, ["alpha", "nope"], ["nope", "alpha"])

    assert row["status"] == "flat"


def test_status_incomplete_when_baseline_has_no_results(capsys: Capsys, tmp_path: Path) -> None:
    code, row = scored_row(capsys, tmp_path, [], ["alpha"])

    assert code == 1
    assert row["status"] == "incomplete"
    assert row["baseline_pass_rate"] is None
    assert row["delta"] is None


def test_status_incomplete_when_with_skill_has_no_results(capsys: Capsys, tmp_path: Path) -> None:
    code, row = scored_row(capsys, tmp_path, ["alpha"], [])

    assert code == 1
    assert row["status"] == "incomplete"
    assert row["with_skill_pass_rate"] is None


def test_empty_results_file_makes_every_case_incomplete(capsys: Capsys, tmp_path: Path) -> None:
    frozen = freeze_cases(capsys, tmp_path, [make_case()])
    results = tmp_path / "r.jsonl"
    results.write_text("", encoding="utf-8")

    code, payload = score(capsys, frozen, results)

    assert code == 1
    assert payload["cases"][0]["status"] == "incomplete"
    assert payload["overall"]["capability_delta"] is None
    assert payload["examined"] == {"cases": 1, "results": 0}


# --- score: reps, aggregation -----------------------------------------------


def test_multiple_reps_average_into_a_pass_rate(capsys: Capsys, tmp_path: Path) -> None:
    _, row = scored_row(
        capsys, tmp_path, ["nope", "nope", "alpha", "nope"], ["alpha", "alpha", "alpha", "nope"]
    )

    assert row["baseline_pass_rate"] == 0.25
    assert row["with_skill_pass_rate"] == 0.75
    assert row["delta"] == 0.5
    assert (row["baseline_runs"], row["with_skill_runs"]) == (4, 4)


def test_uneven_rep_counts_are_averaged_per_condition(capsys: Capsys, tmp_path: Path) -> None:
    _, row = scored_row(capsys, tmp_path, ["nope"], ["alpha", "alpha", "nope"])

    assert row["baseline_pass_rate"] == 0.0
    assert row["with_skill_pass_rate"] == pytest.approx(0.6667)


def test_skill_and_overall_summaries(capsys: Capsys, tmp_path: Path) -> None:
    cases = [
        make_case("C1", "acme-a"),
        make_case("C2", "acme-a"),
        make_case("C3", "acme-b"),
        make_case("C4", "acme-b"),
    ]
    frozen = freeze_cases(capsys, tmp_path, cases)
    rows = [
        result("C1", "baseline", "nope"),  # gain
        result("C1", "with_skill", "alpha"),
        result("C2", "baseline", "alpha"),  # no_gap
        result("C2", "with_skill", "alpha"),
        result("C3", "baseline", "nope"),  # flat
        result("C3", "with_skill", "nope"),
        result("C4", "baseline", "alpha"),  # regression
        result("C4", "with_skill", "nope"),
    ]

    code, payload = score(capsys, frozen, write_results(tmp_path / "r.jsonl", rows))

    a, b = payload["skills"]["acme-a"], payload["skills"]["acme-b"]
    assert code == 1  # C4 regresses
    assert (a["baseline"], a["with_skill"], a["capability_delta"]) == (0.5, 1.0, 0.5)
    assert a["statuses"] == {"gain": 1, "no_gap": 1, "regression": 0, "flat": 0, "incomplete": 0}
    assert (b["baseline"], b["with_skill"], b["capability_delta"]) == (0.5, 0.0, -0.5)
    assert b["statuses"] == {"gain": 0, "no_gap": 0, "regression": 1, "flat": 1, "incomplete": 0}
    assert payload["overall"]["baseline"] == 0.5
    assert payload["overall"]["with_skill"] == 0.5
    assert payload["overall"]["capability_delta"] == 0.0
    assert payload["examined"] == {"cases": 4, "results": 8}


def test_incomplete_case_is_excluded_from_means_but_counted(capsys: Capsys, tmp_path: Path) -> None:
    frozen = freeze_cases(capsys, tmp_path, [make_case("C1"), make_case("C2")])
    rows = [
        result("C1", "baseline", "nope"),
        result("C1", "with_skill", "alpha"),
        result("C2", "baseline", "alpha"),
    ]

    code, payload = score(capsys, frozen, write_results(tmp_path / "r.jsonl", rows))

    overall = payload["overall"]
    assert code == 1
    assert overall["capability_delta"] == 1.0
    assert overall["statuses"]["incomplete"] == 1
    assert payload["examined"] == {"cases": 2, "results": 3}


def test_each_case_is_graded_with_its_own_grader(capsys: Capsys, tmp_path: Path) -> None:
    cases = [
        make_case("C1", grader={"kind": "regex", "pattern": "^ok$"}),
        make_case("C2", grader={"kind": "json_set_f1", "key": "k", "gold": ["x"]}),
    ]
    frozen = freeze_cases(capsys, tmp_path, cases)
    rows = [
        result("C1", "baseline", "ok"),
        result("C1", "with_skill", "ok"),
        result("C2", "baseline", fenced('{"k": []}')),
        result("C2", "with_skill", fenced('{"k": ["x"]}')),
    ]

    _, payload = score(capsys, frozen, write_results(tmp_path / "r.jsonl", rows))

    statuses = {row["id"]: row["status"] for row in payload["cases"]}
    assert statuses == {"C1": "no_gap", "C2": "gain"}


def test_blank_lines_in_results_are_skipped(capsys: Capsys, tmp_path: Path) -> None:
    frozen = freeze_cases(capsys, tmp_path, [make_case()])
    results = tmp_path / "r.jsonl"
    lines = [
        json.dumps(result("C1", "baseline", "x")),
        "",
        "   ",
        json.dumps(result("C1", "with_skill", "alpha")),
    ]
    results.write_text("\n".join(lines), encoding="utf-8")

    code, payload = score(capsys, frozen, results)

    assert code == 0
    assert payload["examined"]["results"] == 2


# --- score: --min-delta -----------------------------------------------------


def delta_run(capsys: Capsys, tmp_path: Path, *extra: str) -> Result:
    frozen = freeze_cases(capsys, tmp_path, [make_case()])
    rows = [result("C1", "baseline", "nope"), result("C1", "with_skill", "alpha")]
    return score(capsys, frozen, write_results(tmp_path / "r.jsonl", rows), *extra)


def test_min_delta_met_exits_zero(capsys: Capsys, tmp_path: Path) -> None:
    code, payload = delta_run(capsys, tmp_path, "--min-delta", "0.5")

    assert code == 0
    assert payload["min_delta"] == {"required": 0.5, "met": True}


def test_min_delta_equal_to_overall_delta_is_met(capsys: Capsys, tmp_path: Path) -> None:
    code, _ = delta_run(capsys, tmp_path, "--min-delta", "1.0")

    assert code == 0


def test_min_delta_not_met_exits_one(capsys: Capsys, tmp_path: Path) -> None:
    frozen = freeze_cases(capsys, tmp_path, [make_case()])
    rows = [result("C1", "baseline", "nope"), result("C1", "with_skill", "nope")]

    code, payload = score(
        capsys, frozen, write_results(tmp_path / "r.jsonl", rows), "--min-delta", "0.1"
    )

    assert code == 1
    assert payload["min_delta"]["met"] is False


def test_min_delta_fails_when_nothing_was_measured(capsys: Capsys, tmp_path: Path) -> None:
    frozen = freeze_cases(capsys, tmp_path, [make_case()])
    results = write_results(tmp_path / "r.jsonl", [result("C1", "baseline", "x")])

    code, payload = score(capsys, frozen, results, "--min-delta", "0")

    assert code == 1
    assert payload["min_delta"]["met"] is False


def test_min_delta_met_still_exits_one_when_a_case_is_incomplete(
    capsys: Capsys, tmp_path: Path
) -> None:
    frozen = freeze_cases(capsys, tmp_path, [make_case("C1"), make_case("C2")])
    rows = [result("C1", "baseline", "nope"), result("C1", "with_skill", "alpha")]

    code, payload = score(
        capsys, frozen, write_results(tmp_path / "r.jsonl", rows), "--min-delta", "0.5"
    )

    assert code == 1
    assert payload["min_delta"]["met"] is True


@pytest.mark.parametrize("value", ["nan", "inf", "-inf"])
def test_min_delta_rejects_non_finite_values(capsys: Capsys, tmp_path: Path, value: str) -> None:
    code, payload = delta_run(capsys, tmp_path, f"--min-delta={value}")

    assert code == 2
    assert "finite" in payload["message"]


# --- score: tamper and bad inputs --------------------------------------------


def edit_frozen(path: Path, mutate: Any) -> None:
    record = json.loads(path.read_text(encoding="utf-8"))
    mutate(record)
    path.write_text(json.dumps(record), encoding="utf-8")


def one_result_file(tmp_path: Path) -> Path:
    return write_results(tmp_path / "r.jsonl", [result("C1", "baseline", "alpha")])


def test_score_detects_edited_prompt(capsys: Capsys, tmp_path: Path) -> None:
    frozen = freeze_cases(capsys, tmp_path, [make_case()])
    edit_frozen(frozen, lambda r: r["cases"][0].update(prompt="changed"))

    code, payload = score(capsys, frozen, one_result_file(tmp_path))

    assert code == 2
    assert "frozen file was edited after freezing" in payload["message"]


def test_score_detects_edited_grader(capsys: Capsys, tmp_path: Path) -> None:
    frozen = freeze_cases(capsys, tmp_path, [make_case()])
    edit_frozen(frozen, lambda r: r["cases"][0]["grader"].update(terms=["x"]))

    code, payload = score(capsys, frozen, one_result_file(tmp_path))

    assert code == 2
    assert "edited after freezing" in payload["message"]


def test_score_detects_removed_case(capsys: Capsys, tmp_path: Path) -> None:
    frozen = freeze_cases(capsys, tmp_path, [make_case("C1"), make_case("C2")])
    edit_frozen(frozen, lambda r: r["cases"].pop())

    code, payload = score(capsys, frozen, one_result_file(tmp_path))

    assert code == 2
    assert "edited after freezing" in payload["message"]


def test_score_detects_replaced_digest(capsys: Capsys, tmp_path: Path) -> None:
    frozen = freeze_cases(capsys, tmp_path, [make_case()])
    edit_frozen(frozen, lambda r: r.update(sha256="0" * 64))

    code, payload = score(capsys, frozen, one_result_file(tmp_path))

    assert code == 2
    assert "edited after freezing" in payload["message"]


def test_score_detects_missing_digest(capsys: Capsys, tmp_path: Path) -> None:
    frozen = freeze_cases(capsys, tmp_path, [make_case()])
    edit_frozen(frozen, lambda r: r.pop("sha256"))

    code, _ = score(capsys, frozen, one_result_file(tmp_path))

    assert code == 2


def test_score_accepts_untouched_frozen_file(capsys: Capsys, tmp_path: Path) -> None:
    frozen = freeze_cases(capsys, tmp_path, [make_case()])
    results = write_results(
        tmp_path / "r.jsonl",
        [result("C1", "baseline", "alpha"), result("C1", "with_skill", "alpha")],
    )

    code, _ = score(capsys, frozen, results)

    assert code == 0


def test_score_rejects_frozen_file_with_valid_digest_but_invalid_cases(
    capsys: Capsys, tmp_path: Path
) -> None:
    bad = make_case(grader={"kind": "fuzzy"})
    frozen = write_json(
        tmp_path / "f.json",
        {
            "schema": "skill-bootstrap-eval/1",
            "sha256": bootstrap_eval.cases_digest([bad]),
            "cases": [bad],
        },
    )

    code, _ = score(capsys, frozen, one_result_file(tmp_path))

    assert code == 2


@pytest.mark.parametrize("record", [[], {"schema": "other/1", "cases": []}, {"cases": []}])
def test_score_rejects_wrong_frozen_schema(capsys: Capsys, tmp_path: Path, record: Any) -> None:
    frozen = write_json(tmp_path / "f.json", record)

    code, payload = score(capsys, frozen, one_result_file(tmp_path))

    assert code == 2
    assert "skill-bootstrap-eval/1" in payload["message"]


def test_score_rejects_unknown_case_id(capsys: Capsys, tmp_path: Path) -> None:
    frozen = freeze_cases(capsys, tmp_path, [make_case()])
    results = write_results(tmp_path / "r.jsonl", [result("C9", "baseline", "alpha")])

    code, payload = score(capsys, frozen, results)

    assert code == 2
    assert "C9" in payload["message"]


def test_score_rejects_unknown_condition(capsys: Capsys, tmp_path: Path) -> None:
    frozen = freeze_cases(capsys, tmp_path, [make_case()])
    results = write_results(tmp_path / "r.jsonl", [result("C1", "treatment", "alpha")])

    code, payload = score(capsys, frozen, results)

    assert code == 2
    assert "treatment" in payload["message"]


def test_score_rejects_non_string_output(capsys: Capsys, tmp_path: Path) -> None:
    frozen = freeze_cases(capsys, tmp_path, [make_case()])
    results = write_results(
        tmp_path / "r.jsonl", [{"case_id": "C1", "condition": "baseline", "output": 5}]
    )

    code, _ = score(capsys, frozen, results)

    assert code == 2


def test_score_rejects_result_line_that_is_not_json(capsys: Capsys, tmp_path: Path) -> None:
    frozen = freeze_cases(capsys, tmp_path, [make_case()])
    results = tmp_path / "r.jsonl"
    results.write_text("{oops\n", encoding="utf-8")

    code, payload = score(capsys, frozen, results)

    assert code == 2
    assert "line 1" in payload["message"]


def test_score_rejects_result_line_that_is_not_an_object(capsys: Capsys, tmp_path: Path) -> None:
    frozen = freeze_cases(capsys, tmp_path, [make_case()])
    results = tmp_path / "r.jsonl"
    results.write_text("[1, 2]\n", encoding="utf-8")

    code, _ = score(capsys, frozen, results)

    assert code == 2


def test_score_rejects_missing_results_file(capsys: Capsys, tmp_path: Path) -> None:
    frozen = freeze_cases(capsys, tmp_path, [make_case()])

    code, payload = score(capsys, frozen, tmp_path / "none.jsonl")

    assert code == 2
    assert "cannot read results" in payload["message"]


def test_score_rejects_missing_frozen_file(capsys: Capsys, tmp_path: Path) -> None:
    code, _ = score(capsys, tmp_path / "none.json", one_result_file(tmp_path))

    assert code == 2


# --- CLI entry --------------------------------------------------------------


def test_script_entry_point_exits_with_main_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Capsys
) -> None:
    script = _SCRIPTS / "bootstrap_eval.py"
    monkeypatch.setattr(
        sys, "argv", ["bootstrap_eval", "score", "--frozen", str(tmp_path / "x"), "--results", "y"]
    )

    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(script), run_name="__main__")

    assert exc.value.code == 2
    assert json.loads(capsys.readouterr().out)["error"] == "config"


def test_missing_subcommand_is_an_argparse_error(capsys: Capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        bootstrap_eval.main([])

    assert exc.value.code == 2
    assert "required" in capsys.readouterr().err


def test_no_dash_characters_in_script_text() -> None:
    text = (_SCRIPTS / "bootstrap_eval.py").read_text(encoding="utf-8")

    assert "\u2014" not in text
    assert "\u2013" not in text


# --- regex bounds (security review F1) --------------------------------------


@pytest.mark.parametrize(
    "pattern",
    ["(a+)+$", "(a*)*", "(a+)?", "((a+))+", "(a{2})+", "(x+y)*z", "(a?)+", "(a?)*", "x" * 257]
    + ["(a|a)*$", "(a|b)+", "(a|b)*", "(x|(y|z))+"]
    + ["(?x)(a+) +$", "(?ix)(a+) +$", "(a+)(?#c)+$", "(?x:(a+) +)$", "(?i)(?x)a"],
)
def test_regex_rejects_unbounded_shapes(pattern: str) -> None:
    with pytest.raises(bootstrap_eval.ConfigError):
        bootstrap_eval.compile_grader({"kind": "regex", "pattern": pattern})


@pytest.mark.parametrize(
    "pattern",
    [
        "(ab)+",
        "a|b",
        "(?:ab)|c",
        "([a-z]+)",
        "([+*])+",
        "[]+]+",
        "[^]a]+",
        r"[\]+]+",
        r"\(a+\)+",
        "(?:ab)+",
        "(?P<word>ab)+",
        "colou?r",
        r"\(?a",
        r"\(\?x\)",
        "[(?#]+",
        "(?i)abc",
        "(?P<x>ab)+",
        "x" * 256,
    ],
)
def test_regex_accepts_bounded_shapes(pattern: str) -> None:
    grade = bootstrap_eval.compile_grader({"kind": "regex", "pattern": pattern})

    assert isinstance(grade("zzz"), bool)


def test_regex_unbalanced_close_paren_is_a_config_error() -> None:
    with pytest.raises(bootstrap_eval.ConfigError):
        bootstrap_eval.compile_grader({"kind": "regex", "pattern": "a)+"})


@pytest.mark.parametrize("pattern", ["(a+)+$", "a{99999999999}"])
def test_freeze_rejects_dangerous_regex_with_exit_two(
    capsys: Capsys, tmp_path: Path, pattern: str
) -> None:
    grader = {"kind": "regex", "pattern": pattern}

    code, payload, out = freeze_raw(capsys, tmp_path, {"cases": [make_case(grader=grader)]})

    assert code == 2
    assert payload["error"] == "config"
    assert not out.exists()


def test_freeze_still_accepts_a_normal_regex(capsys: Capsys, tmp_path: Path) -> None:
    grader = {"kind": "regex", "pattern": r"gates?\s+for\s+\w+"}

    code, _, out = freeze_raw(capsys, tmp_path, {"cases": [make_case(grader=grader)]})

    assert code == 0
    assert out.exists()


@pytest.mark.parametrize("error", [OverflowError, RecursionError])
def test_regex_compile_overflow_and_recursion_are_config_errors(
    monkeypatch: pytest.MonkeyPatch, error: type[Exception]
) -> None:
    def boom(*_args: Any) -> None:
        raise error("too big")

    monkeypatch.setattr(bootstrap_eval.re, "compile", boom)

    with pytest.raises(bootstrap_eval.ConfigError):
        bootstrap_eval.compile_grader({"kind": "regex", "pattern": "a"})


def test_regex_grader_searches_only_the_first_100000_characters() -> None:
    grade = bootstrap_eval.compile_grader({"kind": "regex", "pattern": "needle"})

    assert grade("x" * 99_994 + "needle") is True
    assert grade("x" * 100_000 + "needle") is False


# --- result shape (security review F5c) -------------------------------------


@pytest.mark.parametrize("case_id", [["C1"], {"a": 1}, 5, None])
def test_score_rejects_unhashable_or_non_string_case_id(
    capsys: Capsys, tmp_path: Path, case_id: Any
) -> None:
    frozen = freeze_cases(capsys, tmp_path, [make_case()])
    results = write_results(
        tmp_path / "r.jsonl", [{"case_id": case_id, "condition": "baseline", "output": "alpha"}]
    )

    code, payload = score(capsys, frozen, results)

    assert code == 2
    assert payload["error"] == "config"


def test_score_rejects_results_that_are_not_utf8(capsys: Capsys, tmp_path: Path) -> None:
    frozen = freeze_cases(capsys, tmp_path, [make_case()])
    results = tmp_path / "r.jsonl"
    results.write_bytes(b'{"case_id": "C1", "output": "\xff\xfe"}\n')

    code, payload = score(capsys, frozen, results)

    assert code == 2
    assert "cannot read results" in payload["message"]


def test_regression_exits_1_even_when_every_case_is_complete(
    capsys: Capsys, tmp_path: Path
) -> None:
    code, row = scored_row(capsys, tmp_path, ["alpha"], ["nope"])

    assert row["status"] == "regression"
    assert code == 1


# --- review fixes: git timeout in the in-repo check ---------------------------


def test_enclosing_repo_times_out_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def hang(cmd: Any, **kwargs: Any) -> Any:
        assert kwargs["timeout"] == bootstrap_eval.GIT_TIMEOUT_S
        raise subprocess.TimeoutExpired(cmd, kwargs["timeout"])

    monkeypatch.setattr(bootstrap_eval.subprocess, "run", hang)

    with pytest.raises(bootstrap_eval.ExternalError, match="timed out"):
        bootstrap_eval.enclosing_repo(tmp_path)
