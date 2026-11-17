"""Tests for council_steps.py, the delegate route used with T3 or harness subagents.

Drives init, rank, chair, and finish through main(argv) on a run directory,
writing the replies a delegate would return.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_SUPPORT_SPEC = importlib.util.spec_from_file_location(
    "llm_council_support", Path(__file__).with_name("_support.py")
)
if _SUPPORT_SPEC is None or _SUPPORT_SPEC.loader is None:
    raise ImportError("llm-council _support.py is missing")
support = importlib.util.module_from_spec(_SUPPORT_SPEC)
_SUPPORT_SPEC.loader.exec_module(support)

steps = support.load_script("council_steps.py", "council_steps_t")
core = sys.modules["council_core"]


@pytest.fixture
def question(tmp_path):
    path = tmp_path / "q.md"
    path.write_text("Should we ship the cache?\n", encoding="utf-8")
    return path


def _run(capsys, *argv):
    code = steps.main(list(argv))
    out = capsys.readouterr().out
    return code, (json.loads(out) if out.strip() else None)


def _write(path, text):
    Path(path).write_text(text, encoding="utf-8")


def _init(capsys, run_dir, question, *extra):
    return _run(capsys, "init", "--run-dir", str(run_dir), "--question-file", str(question), *extra)


def test_full_delegate_flow_matches_script_route_prompts(tmp_path, question, capsys):
    run_dir = tmp_path / "run"

    code, init = _init(capsys, run_dir, question, "--mode", "design")
    assert code == 0
    assert init["start"] == core.COUNCILS_BY_MODE["design"]
    assert (run_dir / "stage1-prompt.md").read_text(encoding="utf-8") == core.stage1_prompt(
        "Should we ship the cache?"
    )
    for model, path in init["replies"].items():
        _write(path, f"answer from {model}")

    code, rank = _run(capsys, "rank", "--run-dir", str(run_dir))
    assert code == 0
    survivors = rank["rankers"]
    responses = {m: f"answer from {m}" for m in survivors}
    expected = core.ranker_prompt("Should we ship the cache?", survivors, responses)
    assert (run_dir / "stage2-prompt.md").read_text(encoding="utf-8") == expected
    for path in rank["replies"].values():
        _write(path, "FINAL RANKING:\n1. Response B\n2. Response A\n3. Response C\n4. Response D\n")

    code, chair = _run(capsys, "chair", "--run-dir", str(run_dir))
    assert code == 0
    assert chair["chairman"] == "gpt-6-astra"
    assert chair["borda"][0] == [survivors[1], 1.0]
    assert chair["unparsed_rankers"] == []
    _write(chair["reply"], "Ship it.")

    code, finish = _run(capsys, "finish", "--run-dir", str(run_dir))
    md = Path(finish["artifact"]).read_text(encoding="utf-8")
    assert code == 0
    assert finish["synthesis"] == "Ship it."
    assert "# LLM Council: design mode" in md
    assert finish["errors"] == {}


def test_unavailable_member_is_reported_not_replaced(tmp_path, question, capsys):
    run_dir = tmp_path / "run"

    code, init = _init(
        capsys, run_dir, question, "--unavailable", "gpt-6-astra=not in this harness"
    )

    assert code == 0
    assert "gpt-6-astra" not in init["start"]
    assert len(init["start"]) == 3
    assert init["unavailable"] == {"gpt-6-astra": "not in this harness"}
    for path in init["replies"].values():
        _write(path, "answer")
    _run(capsys, "rank", "--run-dir", str(run_dir))
    _, finish = _run(capsys, "finish", "--run-dir", str(run_dir))
    assert finish["errors"]["gpt-6-astra"] == "not in this harness"
    plan = json.loads((run_dir / "plan.json").read_text(encoding="utf-8"))
    assert plan["council"] == core.COUNCILS_BY_MODE["general"]


def test_unavailable_must_name_a_member(tmp_path, question, capsys):
    code, _ = _init(capsys, tmp_path / "run", question, "--unavailable", "gemini-4-argon=down")

    assert code == steps.EXIT_CONFIG


def test_unavailable_needs_model_equals_reason(tmp_path, question, capsys):
    code = steps.main(
        [
            "init",
            "--run-dir",
            str(tmp_path / "run"),
            "--question-file",
            str(question),
            "--unavailable",
            "gpt-6-astra",
        ]
    )

    assert code == steps.EXIT_CONFIG
    assert "MODEL=REASON" in capsys.readouterr().err


def test_too_few_answers_stops_before_ranking(tmp_path, question, capsys):
    run_dir = tmp_path / "run"
    _, init = _init(capsys, run_dir, question)
    for path in list(init["replies"].values())[:2]:
        _write(path, "answer")

    code, _ = _run(capsys, "rank", "--run-dir", str(run_dir))

    assert code == steps.EXIT_TOO_FEW
    assert not (run_dir / "stage2-prompt.md").exists()


def test_missing_chairman_reply_is_recorded_as_failure(tmp_path, question, capsys):
    run_dir = tmp_path / "run"
    _, init = _init(capsys, run_dir, question)
    for path in init["replies"].values():
        _write(path, "answer")
    _run(capsys, "rank", "--run-dir", str(run_dir))

    _, finish = _run(capsys, "finish", "--run-dir", str(run_dir))

    assert finish["synthesis"] == "[Chairman synthesis failed: no reply]"


def test_unparsed_ranker_is_listed(tmp_path, question, capsys):
    run_dir = tmp_path / "run"
    _, init = _init(capsys, run_dir, question)
    for path in init["replies"].values():
        _write(path, "answer")
    _, rank = _run(capsys, "rank", "--run-dir", str(run_dir))
    first, *rest = rank["replies"].items()
    _write(first[1], "I refuse to rank.")
    for _, path in rest:
        _write(path, "FINAL RANKING:\n1. Response A\n2. Response B\n3. Response C\n4. Response D\n")

    _, chair = _run(capsys, "chair", "--run-dir", str(run_dir))

    assert chair["unparsed_rankers"] == [first[0]]


def test_empty_question_is_config_error(tmp_path, capsys):
    empty = tmp_path / "q.md"
    _write(empty, "  \n")

    code, _ = _init(capsys, tmp_path / "run", empty)

    assert code == steps.EXIT_CONFIG


def test_step_without_plan_is_config_error(tmp_path, capsys):
    code, _ = _run(capsys, "rank", "--run-dir", str(tmp_path / "nothing"))

    assert code == steps.EXIT_CONFIG


def _answered(capsys, run_dir, question, count=None):
    _, init = _init(capsys, run_dir, question)
    paths = list(init["replies"].items())
    for _, path in paths[:count]:
        _write(path, "answer")
    return paths


def test_late_stage1_reply_does_not_break_the_ranking(tmp_path, question, capsys):
    run_dir = tmp_path / "run"
    paths = _answered(capsys, run_dir, question, count=3)
    _, rank = _run(capsys, "rank", "--run-dir", str(run_dir))
    for path in rank["replies"].values():
        _write(path, "FINAL RANKING:\n1. Response A\n2. Response B\n3. Response C\n")
    late_model, late_path = paths[3]
    _write(late_path, "late answer")

    _, chair = _run(capsys, "chair", "--run-dir", str(run_dir))
    _, finish = _run(capsys, "finish", "--run-dir", str(run_dir))

    assert chair["unparsed_rankers"] == []
    assert len(chair["borda"]) == 3
    assert finish["errors"][late_model] == "replied after ranking started"
    assert "late answer" not in (run_dir / "stage3-prompt.md").read_text(encoding="utf-8")


def test_init_refuses_a_reused_run_dir(tmp_path, question, capsys):
    run_dir = tmp_path / "run"
    _init(capsys, run_dir, question)

    code, _ = _init(capsys, run_dir, question)

    assert code == steps.EXIT_CONFIG


@pytest.mark.parametrize("command", ["chair", "finish"])
def test_chair_and_finish_need_rank_first(tmp_path, question, capsys, command):
    run_dir = tmp_path / "run"
    _answered(capsys, run_dir, question)

    capsys.readouterr()

    code = steps.main([command, "--run-dir", str(run_dir)])

    assert code == steps.EXIT_CONFIG
    assert "run `rank`" in capsys.readouterr().err


def test_missing_stage2_ranker_is_reported(tmp_path, question, capsys):
    # Regression for Sol round 1 S3: a ranker that never replied must not vanish.
    run_dir = tmp_path / "run"
    _answered(capsys, run_dir, question)
    _, rank = _run(capsys, "rank", "--run-dir", str(run_dir))
    first, *rest = rank["replies"].items()
    for _, path in rest:
        _write(path, "FINAL RANKING:\n1. Response A\n2. Response B\n3. Response C\n4. Response D\n")

    _, chair = _run(capsys, "chair", "--run-dir", str(run_dir))
    _, finish = _run(capsys, "finish", "--run-dir", str(run_dir))

    assert chair["missing_rankers"] == [first[0]]
    assert finish["errors"] == {first[0]: "no Stage 2 ranking"}
    assert "no Stage 2 ranking" in Path(finish["artifact"]).read_text(encoding="utf-8")


def test_second_rank_is_refused(tmp_path, question, capsys):
    run_dir = tmp_path / "run"
    _answered(capsys, run_dir, question)
    _run(capsys, "rank", "--run-dir", str(run_dir))

    code = steps.main(["rank", "--run-dir", str(run_dir)])

    assert code == steps.EXIT_CONFIG
    assert "already ran" in capsys.readouterr().err


def test_unavailable_chairman_is_reported_not_replaced(tmp_path, question, capsys):
    run_dir = tmp_path / "run"
    _, init = _init(capsys, run_dir, question, "--unavailable", "gpt-6-astra=not in this harness")
    for path in init["replies"].values():
        _write(path, "answer")
    _run(capsys, "rank", "--run-dir", str(run_dir))

    _, chair = _run(capsys, "chair", "--run-dir", str(run_dir))
    _, finish = _run(capsys, "finish", "--run-dir", str(run_dir))

    assert chair["chairman_unavailable"] == "not in this harness"
    assert finish["synthesis"] == "[Chairman unavailable: not in this harness]"


# --min-responses floor and member slug collisions


def _init_args(run_dir, question):
    return ["init", "--run-dir", str(run_dir), "--question-file", str(question)]


@pytest.mark.parametrize("value", ["0", "-1"])
def test_init_rejects_min_responses_below_one(tmp_path, question, capsys, value):
    run_dir = tmp_path / "run"

    code = steps.main([*_init_args(run_dir, question), "--min-responses", value])

    assert code == steps.EXIT_CONFIG == 2
    assert f"--min-responses must be at least 1, got {value}" in capsys.readouterr().err
    assert not run_dir.exists()


def test_init_accepts_min_responses_of_one(tmp_path, question, capsys):
    code, _ = _init(capsys, tmp_path / "run", question, "--min-responses", "1")

    assert code == 0
    plan = json.loads((tmp_path / "run" / "plan.json").read_text(encoding="utf-8"))
    assert plan["min_responses"] == 1


def test_init_rejects_members_whose_reply_files_collide(tmp_path, question, capsys):
    run_dir = tmp_path / "run"

    code = steps.main([*_init_args(run_dir, question), "--models", "openai/gpt-4.1,openai_gpt-4.1"])

    assert code == 2
    err = capsys.readouterr().err
    assert "'openai/gpt-4.1'" in err
    assert "'openai_gpt-4.1'" in err
    assert not run_dir.exists()


@pytest.mark.parametrize("models", [",", " , ,"])
def test_init_rejects_models_that_name_no_ids(tmp_path, question, capsys, models):
    run_dir = tmp_path / "run"

    code = steps.main([*_init_args(run_dir, question), "--models", models])

    assert code == 2
    assert "the council is empty" in capsys.readouterr().err
    assert not run_dir.exists()


def test_init_accepts_members_with_distinct_reply_files(tmp_path, question, capsys):
    code, init = _init(
        capsys, tmp_path / "run", question, "--models", "openai/gpt-4.1,openai/gpt-4.2"
    )

    assert code == 0
    assert len(set(init["replies"].values())) == 2
