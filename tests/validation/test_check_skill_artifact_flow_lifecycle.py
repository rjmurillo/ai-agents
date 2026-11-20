"""Tests for the skill artifact flow gate: credit walk, lifecycle order, Handoff, and CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.validation.artifact_flow_fixtures import (  # noqa: F401
    _DEFAULTS,
    _PLAIN_KEY,
    _REPO_ROOT,
    _VALIDATION,
    Overrides,
    _block_yaml,
    _corpus,
    _handoff,
    _in,
    _keyed,
    _out,
    _run,
    _scalar,
    _write_skill,
    gate,
)


@pytest.fixture
def corpus(tmp_path: Path) -> Path:
    return _corpus(tmp_path)


# --- invoker walk and credit ------------------------------------------------


def test_invoker_cycle_containing_a_skill_with_outputs_is_reported(
    corpus: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_skill(corpus, "cycle-a", invoker="cycle-b", outputs=[_out("cycle-note")])
    _write_skill(corpus, "cycle-b", invoker="cycle-a")

    code, _, err = _run(corpus, capsys)

    assert code == 1
    assert (
        "invoker cycle cycle-a -> cycle-b -> cycle-a contains a skill that declares outputs" in err
    )


def test_invoker_cycle_is_reported_once_when_both_members_declare_outputs(
    corpus: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_skill(corpus, "cycle-a", invoker="cycle-b", outputs=[_out("note-a")])
    _write_skill(corpus, "cycle-b", invoker="cycle-a", outputs=[_out("note-b")])

    code, _, err = _run(corpus, capsys)

    assert code == 1
    assert err.count("invoker cycle") == 1


def test_invoker_cycle_without_outputs_is_not_reported(
    corpus: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_skill(corpus, "cycle-a", invoker="cycle-b")
    _write_skill(corpus, "cycle-b", invoker="cycle-a")
    _write_skill(corpus, "feeder", invoker="cycle-a", outputs=[_out("feeder-note")])

    code, _, err = _run(corpus, capsys)

    assert code == 0, err


def test_helper_walk_stops_at_the_first_lifecycle_skill(corpus: Path) -> None:
    _corpus(corpus, {"test": {"invoker": "plan"}})
    _write_skill(corpus, "chain-helper", invoker="test", outputs=[_out("test-report")])

    result = gate.survey(corpus)

    assert result.credit["chain-helper"] == "test"


def test_two_hop_helper_is_credited_to_the_lifecycle_skill(corpus: Path) -> None:
    _write_skill(corpus, "hop-a", invoker="plan")
    _write_skill(corpus, "hop-b", invoker="hop-a", outputs=[_out("hop-note")])

    result = gate.survey(corpus)

    assert result.credit["hop-b"] == "plan"


def test_shipped_helper_walk_stops_at_a_repo_local_invoker(corpus: Path) -> None:
    _write_skill(corpus, "local-parent", invoker="plan", repo_local=True)
    _write_skill(corpus, "shipped-child", invoker="local-parent", outputs=[_out("child-note")])

    result = gate.survey(corpus)

    assert result.credit["shipped-child"] is None


def test_repo_local_helper_is_not_credited_to_a_shipped_lifecycle_skill(corpus: Path) -> None:
    _write_skill(
        corpus, "local-child", invoker="plan", repo_local=True, outputs=[_out("child-note")]
    )

    result = gate.survey(corpus)

    assert result.credit["local-child"] is None


# --- lifecycle connectivity -------------------------------------------------


@pytest.mark.parametrize(
    "plan_inputs",
    [[], [_in("requirements-spec", source="user")]],
    ids=["no-inputs", "only-user-sourced"],
)
def test_lifecycle_skill_with_no_input_from_an_earlier_skill_is_rejected(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], plan_inputs: list[object]
) -> None:
    _corpus(tmp_path, {"plan": {"inputs": plan_inputs}})

    code, _, err = _run(tmp_path, capsys)

    assert code == 1
    assert "lifecycle skill `plan` declares no input credited to an earlier lifecycle skill" in err


def test_lifecycle_skill_requiring_data_from_a_later_skill_is_rejected(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _corpus(
        tmp_path,
        {"build": {"inputs": [_in("execution-plan"), _in("review-marker", required=True)]}},
    )

    code, _, err = _run(tmp_path, capsys)

    assert code == 1
    assert "`build` requires `review-marker`, credited to the later lifecycle skill `review`" in err


def test_lifecycle_skill_may_optionally_read_data_from_a_later_skill(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _corpus(
        tmp_path,
        {"build": {"inputs": [_in("execution-plan"), _in("review-marker", required=False)]}},
    )

    code, _, err = _run(tmp_path, capsys)

    assert code == 0, err


def test_missing_lifecycle_template_is_rejected(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _corpus(tmp_path, {"test": None})

    code, _, err = _run(tmp_path, capsys)

    assert code == 1
    assert "lifecycle skill `test` has no template under templates/skills" in err


# --- handoff ----------------------------------------------------------------


def test_missing_handoff_section_is_rejected(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _corpus(tmp_path, {"ship": {"handoff": None}})

    code, _, err = _run(tmp_path, capsys)

    assert code == 1
    assert "lifecycle skill has no `## Handoff` section" in err


@pytest.mark.parametrize(
    "line",
    [
        "Writes: execution-plan. Next: `/build`.",
        "Writes: `execution-plan`.",
        "Writes: `execution-plan`. Next: build.",
        "Writes: `execution-plan`. Next: `/build`",
        "",
    ],
    ids=["no-backticks", "no-next", "bare-next", "no-period", "empty"],
)
def test_malformed_handoff_line_is_rejected(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], line: str
) -> None:
    _corpus(tmp_path, {"plan": {"handoff": line}})

    code, _, err = _run(tmp_path, capsys)

    assert code == 1
    assert f"Handoff line {line!r} must read" in err


def test_handoff_that_omits_its_own_output_is_rejected(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _corpus(tmp_path, {"plan": {"handoff": _handoff([], "build")}})

    code, _, err = _run(tmp_path, capsys)

    assert code == 1
    assert "Handoff line omits its own output `execution-plan`" in err


def test_handoff_that_names_an_uncredited_artifact_is_rejected(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _corpus(tmp_path, {"plan": {"handoff": _handoff(["execution-plan", "phantom-note"], "build")}})

    code, _, err = _run(tmp_path, capsys)

    assert code == 1
    assert "Handoff line names `phantom-note`, which is not credited to `plan`" in err


def test_handoff_may_name_an_output_credited_through_a_helper(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _corpus(tmp_path, {"plan": {"handoff": _handoff(["execution-plan", "plan-notes"], "build")}})
    _write_skill(tmp_path, "plan-helper", invoker="plan", outputs=[_out("plan-notes")])

    code, _, err = _run(tmp_path, capsys)

    assert code == 0, err


@pytest.mark.parametrize(
    ("skill", "line", "expected"),
    [
        ("plan", _handoff(["execution-plan"], "test"), "Handoff `Next:` must be `/build`"),
        ("ship", _handoff([], "spec"), "Handoff `Next:` must be none"),
        ("test", _handoff([], None), "Handoff `Next:` must be `/review`"),
    ],
    ids=["skips-a-step", "ship-must-end", "test-must-continue"],
)
def test_handoff_next_step_must_follow_lifecycle_order(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], skill: str, line: str, expected: str
) -> None:
    _corpus(tmp_path, {skill: {"handoff": line}})

    code, _, err = _run(tmp_path, capsys)

    assert code == 1
    assert expected in err


# --- config errors ----------------------------------------------------------


def test_missing_repository_root_is_a_config_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, _, err = _run(tmp_path / "does-not-exist", capsys)

    assert code == 2
    assert "Invalid repository root" in err


def test_absent_template_directory_is_a_config_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, _, err = _run(tmp_path, capsys)

    assert code == 2
    assert "templates/skills does not exist" in err


def test_template_directory_with_no_templates_is_a_config_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / gate.TEMPLATE_DIR).mkdir(parents=True)
    (tmp_path / gate.TEMPLATE_DIR / "README.md").write_text("not a template\n", encoding="utf-8")

    code, _, err = _run(tmp_path, capsys)

    assert code == 2
    assert "holds no *.SKILL.md.tmpl files" in err


# --- output formats ---------------------------------------------------------


def test_json_format_lists_an_artifact_with_its_producers_and_consumers(
    corpus: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, err = _run(corpus, capsys, "--format", "json")

    data = json.loads(out)
    plan_artifact = data["artifacts"]["execution-plan"]
    assert code == 0, err
    assert data["lifecycle_order"] == ["spec", "plan", "build", "test", "review", "ship"]
    assert plan_artifact["producers"] == [
        {"skill": "plan", "path": "plans/active/", "credited_to": "plan"}
    ]
    assert plan_artifact["consumers"] == [{"skill": "build", "source": "skill", "required": True}]


def test_report_flag_lists_artifacts_that_nobody_consumes(
    corpus: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_skill(corpus, "extra-skill", invoker="harness", outputs=[_out("orphan-note")])

    code, out, err = _run(corpus, capsys, "--report")

    assert code == 0, err
    assert "no consumer: 1" in out
    assert "no consumer orphan-note" in out


# --- committed corpus -------------------------------------------------------


def test_committed_template_corpus_satisfies_the_gate(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, err = _run(_REPO_ROOT, capsys)

    assert code == 0, f"{out}\n{err}"
