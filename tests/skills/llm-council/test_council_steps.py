"""Tests for council_steps.py, the delegate route used with T3 or harness subagents.

Drives init, rank, chair, and finish through main(argv) on a run directory,
writing the replies a delegate would return.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script

steps = import_skill_script(
    ".claude/skills/llm-council/scripts/council_steps.py", module_name="council_steps_t"
)
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
    code, _ = _init(capsys, tmp_path / "run", question, "--unavailable", "gpt-6-astra")

    assert code == steps.EXIT_CONFIG


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
