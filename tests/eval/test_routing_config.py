"""Tests for the routing benchmark config and the A-F strategy invariants (issue #5424)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests.eval._routing_runner_test_support import (
    config_dict,
    config_mod,
    parse,
    scenario_mod,
)

RoutingConfigError = config_mod.RoutingConfigError
Difficulty = scenario_mod.DifficultyClass


def _strategy_doc(document: dict[str, Any], arm: str) -> dict[str, Any]:
    return next(item for item in document["strategies"] if item["arm"] == arm)


def test_checked_in_config_expresses_all_six_arms_on_two_harnesses() -> None:
    config = parse(config_dict())

    assert [item.arm for item in config.strategies] == ["A", "B", "C", "D", "E", "F"]
    assert [ref.harness for ref in config.harnesses] == ["codex", "copilot"]


def test_arm_topologies_and_routes_come_from_the_config() -> None:
    config = parse(config_dict())
    by_arm = {item.arm: item for item in config.strategies}

    assert by_arm["A"].topology is config_mod.Topology.FAN_OUT
    assert by_arm["C"].workers[Difficulty.ORDINARY_BOUNDED].model == "gpt-5.6-luna"
    assert by_arm["D"].workers[Difficulty.ORDINARY_BOUNDED].model == "gpt-5.6-terra"
    assert by_arm["E"].topology is config_mod.Topology.SINGLE_AGENT and not by_arm["E"].workers
    assert by_arm["F"].handoff_artifact == "implementation-plan.md"
    assert by_arm["B"].reviewer is not None and by_arm["B"].reviewer.isolated


def test_a_new_model_needs_no_code_change() -> None:
    document = config_dict()
    _strategy_doc(document, "B")["workers"]["ordinary_bounded"]["model"] = "gpt-9-luna"

    config = parse(document)

    assert (
        config.strategy_for("B", "codex").workers[Difficulty.ORDINARY_BOUNDED].model == "gpt-9-luna"
    )


def test_a_harness_override_resolves_per_harness() -> None:
    document = config_dict()
    for arm in ("A", "C", "D"):
        _strategy_doc(document, arm)["harness_overrides"] = {"copilot": {"max_concurrency": 2}}

    config = parse(document)

    assert config.strategy_for("A", "codex").max_concurrency == 3
    assert config.strategy_for("A", "copilot").max_concurrency == 2


@pytest.mark.parametrize(
    ("arm", "edit", "message"),
    [
        ("A", lambda s: s["orchestrator"].update(effort="high"), "A needs a Sol medium parent"),
        (
            "A",
            lambda s: s["workers"]["ordinary_bounded"].update(model="gpt-5.6-luna"),
            "A needs a Sol medium parent",
        ),
        (
            "A",
            lambda s: s.update(
                reviewer={"model": "gpt-5.6-sol", "effort": "low", "isolated": True}
            ),
            "no reviewer",
        ),
        ("A", lambda s: s.update(max_concurrency=4), "max_concurrency exceeds 3"),
        ("A", lambda s: s["workers"].pop("fallback_reasoning"), "both difficulty classes"),
        ("A", lambda s: s.update(handoff_artifact="plan.md"), "no implementer, handoff"),
        ("A", lambda s: s.update(topology="single_agent"), "requires topology fan_out"),
        ("B", lambda s: s.pop("reviewer"), "isolated reviewer"),
        ("B", lambda s: s["reviewer"].update(isolated=False), "isolated reviewer"),
        (
            "B",
            lambda s: s["workers"]["ordinary_bounded"].update(model="gpt-5.6-sol"),
            "Luna ordinary workers",
        ),
        (
            "B",
            lambda s: s["workers"]["fallback_reasoning"].update(model="gpt-5.6-luna"),
            "Terra fallback",
        ),
        ("C", lambda s: s["workers"]["ordinary_bounded"].update(effort="low"), "luna high"),
        (
            "C",
            lambda s: s["workers"]["ordinary_bounded"].update(model="gpt-5.6-terra"),
            "luna high",
        ),
        ("D", lambda s: s["workers"]["ordinary_bounded"].update(effort="medium"), "terra high"),
        ("E", lambda s: s["orchestrator"].update(model="gpt-5.6-luna"), "E needs a Sol"),
        (
            "E",
            lambda s: s.update(
                workers={"ordinary_bounded": {"model": "gpt-5.6-sol", "effort": "low"}}
            ),
            "no worker or reviewer",
        ),
        ("E", lambda s: s.update(max_concurrency=2), "must be 1"),
        ("E", lambda s: s.update(fresh_context_boundary=True), "no implementer, handoff"),
        ("F", lambda s: s.pop("implementer"), "needs an implementer"),
        ("F", lambda s: s.update(fresh_context_boundary=False), "fresh-context boundary"),
        ("F", lambda s: s.update(handoff_artifact="notes.md"), "implementation-plan.md"),
        (
            "F",
            lambda s: s["implementer"].update(model="gpt-5.6-luna"),
            "Sol planner and Sol implementer",
        ),
        ("F", lambda s: s.update(work_packages=2), "must be 1"),
    ],
)
def test_arm_invariant_violations_are_refused(arm: str, edit: Any, message: str) -> None:
    document = config_dict()
    edit(_strategy_doc(document, arm))

    with pytest.raises(RoutingConfigError, match=message):
        parse(document)


@pytest.mark.parametrize(
    ("arm", "edit", "message"),
    [
        ("C", lambda s: s.update(max_concurrency=2), "C differs from A in max_concurrency"),
        (
            "D",
            lambda s: s.update(max_correction_rounds=5),
            "D differs from A in max_correction_rounds",
        ),
        (
            "C",
            lambda s: s["orchestrator"].update(effort="high"),
            "C differs from A in orchestrator",
        ),
        ("D", lambda s: s.update(work_packages=3), "D differs from A in work_packages"),
        (
            "C",
            lambda s: s["workers"]["fallback_reasoning"].update(effort="high"),
            "C differs from A in the fallback worker",
        ),
    ],
)
def test_c_and_d_hold_everything_but_the_ordinary_worker_constant(
    arm: str, edit: Any, message: str
) -> None:
    document = config_dict()
    edit(_strategy_doc(document, arm))

    with pytest.raises(RoutingConfigError, match=message):
        parse(document)


@pytest.mark.parametrize("arm", ["C", "D"])
def test_c_and_d_need_arm_a_in_the_same_config(arm: str) -> None:
    document = config_dict()
    document["strategies"] = [s for s in document["strategies"] if s["arm"] in {arm, "E"}]

    with pytest.raises(RoutingConfigError, match=f"arm {arm} needs arm A"):
        parse(document)


def test_a_harness_override_that_breaks_an_invariant_is_refused() -> None:
    document = config_dict()
    _strategy_doc(document, "B")["harness_overrides"] = {
        "copilot": {"reviewer": {"model": "gpt-5.6-sol", "effort": "medium", "isolated": False}}
    }

    with pytest.raises(RoutingConfigError, match="arm B on copilot: B needs an isolated reviewer"):
        parse(document)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda d: d.update(schema_version=2), "schema_version"),
        (lambda d: d.update(extra=1), "unknown key"),
        (lambda d: d.pop("strategies"), "missing required key"),
        (lambda d: d.update(strategies=[]), "non-empty list"),
        (lambda d: d.update(harnesses=[]), "non-empty list"),
        (lambda d: d["harnesses"].append(dict(d["harnesses"][0])), "duplicate harness"),
        (lambda d: d["harnesses"][0].pop("version"), "missing required key"),
        (lambda d: d["harnesses"][0].update(version=" "), "non-empty string"),
        (lambda d: d["strategies"].append(dict(d["strategies"][0])), "duplicate arm"),
        (lambda d: d["strategies"][0].update(arm="Z"), "is not one of"),
        (lambda d: d["strategies"][0].update(topology="ring"), "not in"),
        (lambda d: d["strategies"][0].update(surprise=True), "unknown key"),
        (lambda d: d["strategies"][0].update(max_concurrency=True), "expected an int"),
        (lambda d: d["strategies"][0].update(max_concurrency=0), "expected an int >= 1"),
        (lambda d: d["strategies"][0].update(max_correction_rounds=-1), "expected an int >= 0"),
        (lambda d: d["strategies"][0].update(work_packages=0), "work_packages"),
        (lambda d: d["strategies"][0].update(fresh_context_boundary="yes"), "expected a bool"),
        (lambda d: d["strategies"][0]["orchestrator"].pop("effort"), "missing required key"),
        (lambda d: d["strategies"][0]["orchestrator"].update(model=""), "non-empty string"),
        (
            lambda d: d["strategies"][0]["workers"].update(hard={"model": "m", "effort": "e"}),
            "is not one of",
        ),
        (lambda d: d["strategies"][1]["reviewer"].update(isolated="true"), "expected a bool"),
        (
            lambda d: d["strategies"][0].update(harness_overrides={"gemini": {}}),
            "not a configured harness",
        ),
        (
            lambda d: d["strategies"][0].update(harness_overrides={"codex": {"arm": "B"}}),
            "unknown key",
        ),
    ],
)
def test_malformed_config_is_refused(mutate: Any, message: str) -> None:
    document = config_dict()
    mutate(document)

    with pytest.raises(RoutingConfigError, match=message):
        parse(document)


def test_non_object_documents_are_refused() -> None:
    with pytest.raises(RoutingConfigError, match="expected an object"):
        config_mod.parse_config([])


def test_load_config_reports_unreadable_and_invalid_files(tmp_path: Path) -> None:
    with pytest.raises(RoutingConfigError, match="cannot read"):
        config_mod.load_config(tmp_path / "absent.json")
    broken = tmp_path / "broken.json"
    broken.write_text("{nope", encoding="utf-8")
    with pytest.raises(RoutingConfigError, match="invalid JSON"):
        config_mod.load_config(broken)


def test_load_config_reads_the_checked_in_example() -> None:
    path = Path(config_mod.__file__).parent / "examples" / "routing-benchmark-config.json"

    assert len(config_mod.load_config(path).strategies) == 6
    assert json.loads(path.read_text(encoding="utf-8"))["schema_version"] == 1


def test_a_harness_override_on_c_alone_breaks_the_held_constant_rule() -> None:
    document = config_dict()
    _strategy_doc(document, "C")["harness_overrides"] = {"copilot": {"max_concurrency": 2}}

    with pytest.raises(RoutingConfigError, match="arm C on copilot: C differs from A in max_conc"):
        parse(document)
