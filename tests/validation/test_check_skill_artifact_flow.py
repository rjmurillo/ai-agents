"""Tests for the skill artifact flow gate (ADR-123).

Every fixture repository is built in `tmp_path`. `_corpus` writes the smallest
valid tree: the six lifecycle skills plus one helper, with data that connects.
Each negative test changes one thing in that tree and asserts the exit code and
the gate's own message, so a test cannot pass for the wrong reason.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_VALIDATION = _REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION) not in sys.path:
    sys.path.insert(0, str(_VALIDATION))

import check_skill_artifact_flow as gate

Overrides = Mapping[str, Mapping[str, object] | None]


def _handoff(writes: list[str], next_skill: str | None) -> str:
    names = ", ".join(f"`{name}`" for name in writes) or "none"
    target = f"`/{next_skill}`" if next_skill else "none"
    return f"Writes: {names}. Next: {target}."


def _in(artifact: str, **extra: object) -> dict[str, object]:
    return {"artifact": artifact, **extra}


def _out(artifact: str, **extra: object) -> dict[str, object]:
    return {"artifact": artifact, **extra}


# Lifecycle chain: spec-helper -> requirements-spec (credited to spec) ->
# plan -> execution-plan -> build -> implementation-change -> test, review ->
# review-marker -> ship.
_DEFAULTS: dict[str, dict[str, object]] = {
    "spec": {"handoff": _handoff(["requirements-spec"], "plan")},
    "spec-helper": {"invoker": "spec", "outputs": [_out("requirements-spec")]},
    "plan": {
        "inputs": [_in("requirements-spec", required=False)],
        "outputs": [_out("execution-plan", path="plans/active/")],
        "handoff": _handoff(["execution-plan"], "build"),
    },
    "build": {
        "inputs": [_in("execution-plan")],
        "outputs": [_out("implementation-change")],
        "handoff": _handoff(["implementation-change"], "test"),
    },
    "test": {
        "inputs": [_in("implementation-change")],
        "handoff": _handoff([], "review"),
    },
    "review": {
        "inputs": [_in("implementation-change")],
        "outputs": [_out("review-marker")],
        "handoff": _handoff(["review-marker"], "ship"),
    },
    "ship": {
        "inputs": [_in("review-marker")],
        "handoff": _handoff([], None),
    },
}


def _write_skill(
    root: Path,
    name: str,
    *,
    invoker: str = "autoplan",
    inputs: list[object] | None = None,
    outputs: list[object] | None = None,
    repo_local: bool = False,
    handoff: str | None = None,
) -> Path:
    """Write one skill template. `handoff=None` omits the `## Handoff` section."""
    routing = {"role": "front-door", "invoker": invoker, "trigger": "explicit", "user-facing": True}
    lines = [
        "---",
        f"name: {name}",
        f"description: {json.dumps(f'Use when you say {name}.')}",
        "metadata:",
        f"  routing: {json.dumps(routing)}",
    ]
    if inputs:
        lines.append(f"  inputs: {json.dumps(inputs)}")
    if outputs:
        lines.append(f"  outputs: {json.dumps(outputs)}")
    if repo_local:
        lines.append("  distribution: repo-local")
    lines += ["---", "", f"# {name}", "", "Body text."]
    if handoff is not None:
        lines += ["", "## Handoff", "", handoff]
    path = root / gate.TEMPLATE_DIR / f"{name}{gate.TEMPLATE_SUFFIX}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _corpus(root: Path, overrides: Overrides | None = None) -> Path:
    """Write the valid corpus. An override value of None drops that skill."""
    overrides = overrides or {}
    for name, params in _DEFAULTS.items():
        if name in overrides and overrides[name] is None:
            continue
        _write_skill(root, name, **{**params, **(overrides.get(name) or {})})  # type: ignore[arg-type]
    return root


def _run(root: Path, capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, str, str]:
    code = gate.main(["--repo-root", str(root), *args])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


@pytest.fixture
def corpus(tmp_path: Path) -> Path:
    return _corpus(tmp_path)


# --- positive ---------------------------------------------------------------


def test_valid_corpus_passes_and_reports_the_template_count(
    corpus: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, err = _run(corpus, capsys)

    assert code == 0, err
    assert "examined 7 skill templates" in out
    assert "0 violation(s)" in out


def test_valid_corpus_credits_each_output_to_its_lifecycle_skill(corpus: Path) -> None:
    result = gate.survey(corpus)

    assert result.credit == {
        "spec-helper": "spec",
        "plan": "plan",
        "build": "build",
        "review": "review",
    }


# --- entry shape ------------------------------------------------------------


def test_bare_string_input_entry_is_rejected(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _corpus(tmp_path, {"build": {"inputs": ["execution-plan"]}})

    code, _, err = _run(tmp_path, capsys)

    assert code == 1
    assert "inputs[0] must be a mapping with `artifact`, not str" in err


def test_unknown_key_in_output_entry_is_rejected(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _corpus(tmp_path, {"build": {"outputs": [_out("implementation-change", paths="x/")]}})

    code, _, err = _run(tmp_path, capsys)

    assert code == 1
    assert "outputs[0] has unknown key `paths`" in err


def test_non_list_outputs_are_rejected(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _corpus(tmp_path)
    _write_skill(tmp_path, "scalar-outputs", invoker="harness")
    path = tmp_path / gate.TEMPLATE_DIR / f"scalar-outputs{gate.TEMPLATE_SUFFIX}"
    path.write_text(
        path.read_text(encoding="utf-8").replace("metadata:\n", "metadata:\n  outputs: nope\n"),
        encoding="utf-8",
    )

    code, _, err = _run(tmp_path, capsys)

    assert code == 1
    assert "outputs must be a list of mappings, not str" in err


@pytest.mark.parametrize(
    "bad_name",
    ["Bad_Name", "UPPER", "1leading", "double--dash", "trailing-", "requirements-ledger\n"],
    ids=[
        "underscore",
        "upper",
        "leading-digit",
        "double-dash",
        "trailing-dash",
        "trailing-newline",
    ],
)
def test_artifact_name_must_be_lowercase_kebab_case(
    corpus: Path, capsys: pytest.CaptureFixture[str], bad_name: str
) -> None:
    _write_skill(corpus, "extra-skill", invoker="harness", outputs=[_out(bad_name)])

    code, _, err = _run(corpus, capsys)

    assert code == 1
    assert "must be lowercase kebab case" in err


@pytest.mark.parametrize(
    "bad_path",
    ["../x", "a/../b", "/etc", "C:\\x", "~/x", "$HOME/x", ".git/hooks", "plans/\n"],
    ids=[
        "parent",
        "embedded-parent",
        "absolute",
        "drive-letter",
        "home",
        "env-var",
        "dot-git",
        "trailing-newline",
    ],
)
def test_hostile_output_path_is_rejected(
    corpus: Path, capsys: pytest.CaptureFixture[str], bad_path: str
) -> None:
    _write_skill(
        corpus, "extra-skill", invoker="harness", outputs=[_out("scratch-note", path=bad_path)]
    )

    code, _, err = _run(corpus, capsys)

    assert code == 1
    assert "must be a lowercase path relative to the artifact root" in err


def test_relative_directory_output_path_is_accepted(
    corpus: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_skill(
        corpus,
        "extra-skill",
        invoker="harness",
        outputs=[_out("scratch-note", path="plans/active/")],
    )

    code, _, err = _run(corpus, capsys)

    assert code == 0, err


def test_string_required_flag_is_rejected(corpus: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write_skill(
        corpus,
        "extra-skill",
        invoker="harness",
        inputs=[_in("requirements-spec", required="yes")],
    )

    code, _, err = _run(corpus, capsys)

    assert code == 1
    assert "required must be true or false" in err


def test_list_valued_source_is_rejected_without_crashing(
    corpus: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_skill(
        corpus,
        "extra-skill",
        invoker="harness",
        inputs=[_in("requirements-spec", source=["skill"])],
    )

    code, _, err = _run(corpus, capsys)

    assert code == 1
    assert "must be one of skill, user, repo" in err


def test_unknown_source_value_is_rejected(corpus: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write_skill(
        corpus,
        "extra-skill",
        invoker="harness",
        inputs=[_in("requirements-spec", source="network")],
    )

    code, _, err = _run(corpus, capsys)

    assert code == 1
    assert "source 'network' must be one of skill, user, repo" in err


# --- producers and consumers ------------------------------------------------


def test_two_producers_of_one_artifact_are_rejected(
    corpus: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_skill(corpus, "second-writer", invoker="harness", outputs=[_out("execution-plan")])

    code, _, err = _run(corpus, capsys)

    assert code == 1
    assert "artifact `execution-plan` has 2 producers (plan, second-writer)" in err
    assert "ADR-123 allows one" in err


def test_skill_sourced_input_without_a_producer_is_rejected(
    corpus: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_skill(corpus, "extra-skill", invoker="harness", inputs=[_in("ghost-artifact")])

    code, _, err = _run(corpus, capsys)

    assert code == 1
    assert "input `ghost-artifact` has no producing skill" in err


@pytest.mark.parametrize("source", ["user", "repo"])
def test_user_or_repo_sourced_input_needs_no_producer(
    corpus: Path, capsys: pytest.CaptureFixture[str], source: str
) -> None:
    _write_skill(
        corpus, "extra-skill", invoker="harness", inputs=[_in("ghost-artifact", source=source)]
    )

    code, _, err = _run(corpus, capsys)

    assert code == 0, err


def test_shipped_consumer_of_a_repo_local_producer_is_rejected(
    corpus: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_skill(
        corpus, "local-writer", invoker="harness", repo_local=True, outputs=[_out("local-note")]
    )
    _write_skill(corpus, "shipped-reader", invoker="harness", inputs=[_in("local-note")])

    code, _, err = _run(corpus, capsys)

    assert code == 1
    assert "shipped skill reads `local-note`, which only a repo-local skill produces" in err


def test_repo_local_consumer_of_a_repo_local_producer_is_accepted(
    corpus: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_skill(
        corpus, "local-writer", invoker="harness", repo_local=True, outputs=[_out("local-note")]
    )
    _write_skill(
        corpus, "local-reader", invoker="harness", repo_local=True, inputs=[_in("local-note")]
    )

    code, _, err = _run(corpus, capsys)

    assert code == 0, err


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


# --- frontmatter ------------------------------------------------------------


def test_unparseable_frontmatter_is_a_defect(
    corpus: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = corpus / gate.TEMPLATE_DIR / f"broken{gate.TEMPLATE_SUFFIX}"
    path.write_text("---\nname: broken\nmetadata: [unclosed\n---\n\nBody.\n", encoding="utf-8")

    code, _, err = _run(corpus, capsys)

    assert code == 1
    assert "broken.SKILL.md.tmpl: frontmatter does not parse" in err


def test_duplicate_frontmatter_key_is_a_defect_not_a_crash(
    corpus: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = corpus / gate.TEMPLATE_DIR / f"dupe{gate.TEMPLATE_SUFFIX}"
    path.write_text("---\nname: x\nname: y\n---\n\nBody.\n", encoding="utf-8")

    code, _, err = _run(corpus, capsys)

    assert code == 1
    assert "dupe.SKILL.md.tmpl: frontmatter does not parse" in err
    assert "duplicate key" in err


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
