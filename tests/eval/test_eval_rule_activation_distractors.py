"""Distractor option for the skill route arm of eval-rule-activation.py.

No model is called and no network is used. Skills live in a temp directory
that stands in for `.claude/skills`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests.eval.test_eval_rule_activation import eval_mod

TARGET_DESC = "Write specs and requirements documents for features"


def _write_skill(root: Path, name: str, description: str, body: str = "body") -> Path:
    skill_dir = root / name
    skill_dir.mkdir(parents=True)
    path = skill_dir / "SKILL.md"
    path.write_text(f"---\nname: {name}\ndescription: {description}\n---\n{body}\n", "utf-8")
    return path


@pytest.fixture
def skills(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "skills"
    target = _write_skill(root, "spec", TARGET_DESC, "Router body")
    refs = target.parent / "references"
    refs.mkdir()
    (refs / "a.md").write_text("REF A BODY\n", "utf-8")
    (refs / "b.md").write_text("REF B BODY\n", "utf-8")
    _write_skill(root, "plan", "Plan work and write requirements documents for features")
    _write_skill(root, "zeta", "Write specs and requirements documents")
    _write_skill(root, "alpha", "Write specs and requirements documents")
    _write_skill(root, "build", "Implement code in vertical slices with tests")
    monkeypatch.setattr(eval_mod, "SKILLS_DIR", root.resolve())
    monkeypatch.setattr(eval_mod, "REPO_ROOT", tmp_path.resolve())
    return root


def _rule(skills: Path, distractors: int) -> dict[str, Any]:
    target = skills / "spec" / "SKILL.md"
    rule = eval_mod.parse_skill_reference(target, skills / "spec" / "references" / "a.md")
    return eval_mod._attach_distractors(rule, distractors, skills / "spec" / "references" / "a.md")


def _route(
    monkeypatch: pytest.MonkeyPatch,
    rule: dict[str, Any],
    selection: dict[str, Any] | None,
    reference: dict[str, Any] | None = None,
):
    """Run the description arm with canned replies.

    `selection` answers the catalog call (K>0 only), `reference` answers the
    single-skill route call. Returns (cell, systems, kinds), where `kinds`
    lists the call types in order.
    """
    systems: list[str] = []
    kinds: list[str] = []

    def fake_api(*_a: Any, system: str = "", **_k: Any) -> str:
        prompt = _a[1][0]["content"]
        if prompt.startswith("Pick the skill"):
            kinds.append("selection")
            return json.dumps(selection)
        if prompt.startswith("Route the user request"):
            kinds.append("route")
            return json.dumps(reference if reference is not None else selection)
        kinds.append("answer")
        systems.append(system)
        return "answer"

    monkeypatch.setattr(eval_mod, "_call_api", fake_api)
    monkeypatch.setattr(
        eval_mod,
        "score_response",
        lambda *a, **k: {
            "activation_score": 4,
            "citation_score": 4,
            "behavior_score": 4,
            "judge_failed": False,
        },
    )
    monkeypatch.setattr(eval_mod, "RATE_LIMIT_SLEEP_SEC", 0)
    result = eval_mod.eval_one_scenario(
        "",
        rule,
        "spec",
        {"id": "S1", "input": "write a spec", "expected_gate": "g"},
        "m",
        dry_run=False,
        arms=("description",),
    )
    return result["mechanisms"]["description"], systems, kinds


class TestSelection:
    def test_picks_nearest_by_jaccard_ties_by_name(self, skills: Path) -> None:
        picked = eval_mod.select_distractors("spec", TARGET_DESC, 3, skills)
        # alpha and zeta tie at 5/7 and sort by name; plan scores 6/9.
        assert [name for name, _ in picked] == ["alpha", "zeta", "plan"]

    def test_target_excluded_and_k_bounds_result(self, skills: Path) -> None:
        picked = eval_mod.select_distractors("SPEC", TARGET_DESC, 2, skills)
        assert [name for name, _ in picked] == ["alpha", "zeta"]
        assert eval_mod.select_distractors("spec", TARGET_DESC, 0, skills) == []

    def test_short_tokens_are_dropped(self) -> None:
        assert eval_mod._description_tokens("An Ox is in the BARN") == {"the", "barn"}

    def test_default_root_is_the_patched_skills_dir(self, skills: Path) -> None:
        assert [n for n, _ in eval_mod.select_distractors("spec", TARGET_DESC, 1)] == ["alpha"]


class TestPrompts:
    def test_k0_prompts_are_unchanged(self, skills: Path) -> None:
        rule = _rule(skills, 0)
        assert "distractors" not in rule
        system = eval_mod.build_system_prompt("description", rule, "spec")
        assert system == (
            "Project skills are available on demand. Available skill:\n\n"
            f"  - spec: {TARGET_DESC}\n\n"
            "Decide whether to select this skill based on the user's request. "
            "If selected, open the skill router and then the smallest matching "
            "reference before advising the user."
        )
        route = eval_mod.build_skill_route_prompt(rule, {"input": "hi"})
        assert route.startswith("Route the user request through the available skill catalog.")
        assert "Available skill:\n- spec:" in route
        assert "Router body" in route

    def test_k_positive_lists_all_sorted_by_name(self, skills: Path) -> None:
        rule = _rule(skills, 2)
        for prompt in (
            eval_mod.build_system_prompt("description", rule, "spec"),
            eval_mod.build_skill_selection_prompt(rule, {"input": "hi"}),
        ):
            order = [prompt.index(f"- {n}:") for n in ("alpha", "spec", "zeta")]
            assert order == sorted(order)
            assert "plan:" not in prompt
            assert "build:" not in prompt

    def test_target_is_not_always_first(self, skills: Path) -> None:
        names = [n for n, _ in eval_mod._skill_catalog(_rule(skills, 2))]
        assert names == ["alpha", "spec", "zeta"]
        assert names[0] != "spec"

    def test_selection_prompt_has_no_router_body(self, skills: Path) -> None:
        prompt = eval_mod.build_skill_selection_prompt(_rule(skills, 2), {"input": "hi"})
        assert "Router body" not in prompt
        assert "Router for" not in prompt
        assert "selected_reference" not in prompt
        assert "selected_skill" in prompt

    def test_reference_route_prompt_is_single_skill_even_with_distractors(
        self, skills: Path
    ) -> None:
        with_k = eval_mod.build_skill_route_prompt(_rule(skills, 2), {"input": "hi"})
        without = eval_mod.build_skill_route_prompt(_rule(skills, 0), {"input": "hi"})
        assert with_k == without
        assert "alpha" not in with_k
        assert "Router body" in with_k

    def test_prompts_are_deterministic(self, skills: Path) -> None:
        a = eval_mod.build_skill_selection_prompt(_rule(skills, 2), {"input": "x"})
        b = eval_mod.build_skill_selection_prompt(_rule(skills, 2), {"input": "x"})
        assert a == b


SPEC_A = {"selected_skill": "spec", "selected_reference": "references/a.md"}
PICK_SPEC = {"selected_skill": "spec", "reasoning": "r"}


class TestRouting:
    def test_distractor_pick_makes_one_call_and_no_reference(
        self, skills: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cell, systems, kinds = _route(
            monkeypatch, _rule(skills, 2), {"selected_skill": "alpha", "reasoning": "r"}
        )
        routing = cell["routing"]
        assert kinds == ["selection", "answer"]
        assert routing["reference_matched"] is False
        assert routing["selected_skill"] == "alpha"
        assert routing["selected_reference"] is None
        assert routing["distractors"] == ["alpha", "zeta"]
        assert routing["selection"]["selected_skill"] == "alpha"
        assert "reference_route" not in routing
        assert systems == [""]

    def test_null_selection_skips_the_reference_call(
        self, skills: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cell, systems, kinds = _route(
            monkeypatch, _rule(skills, 2), {"selected_skill": None, "reasoning": "r"}
        )
        assert kinds == ["selection", "answer"]
        assert cell["routing"]["reference_matched"] is False
        assert cell["routing"]["selected_skill"] is None
        assert systems == [""]

    def test_target_pick_then_right_reference_matches(
        self, skills: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cell, systems, kinds = _route(monkeypatch, _rule(skills, 2), PICK_SPEC, SPEC_A)
        routing = cell["routing"]
        assert kinds == ["selection", "route", "answer"]
        assert routing["reference_matched"] is True
        assert routing["selection"]["selected_skill"] == "spec"
        assert routing["reference_route"]["selected_reference"] == "references/a.md"
        assert "REF A BODY" in systems[0]

    def test_target_pick_then_wrong_reference_is_a_miss(
        self, skills: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cell, systems, _ = _route(
            monkeypatch,
            _rule(skills, 2),
            PICK_SPEC,
            {"selected_skill": "spec", "selected_reference": "references/b.md"},
        )
        assert cell["routing"]["reference_matched"] is False
        assert "REF B BODY" in systems[0]

    @pytest.mark.parametrize("declined", [None, "", "alpha"])
    def test_step_two_declining_the_skill_is_a_miss(
        self, skills: Path, monkeypatch: pytest.MonkeyPatch, declined: str | None
    ) -> None:
        # Step one picks the target, step two names the right reference but
        # declines or swaps the skill. That route is not a hit.
        cell, _, kinds = _route(
            monkeypatch,
            _rule(skills, 2),
            PICK_SPEC,
            {"selected_skill": declined, "selected_reference": "references/a.md"},
        )
        assert kinds == ["selection", "route", "answer"]
        assert cell["routing"]["reference_matched"] is False
        assert cell["routing"]["reference_route"]["selected_skill"] == declined

    @pytest.mark.parametrize("spelling", ["/spec", "  SPEC ", "/Spec\n"])
    def test_slash_case_and_whitespace_are_normalized(
        self, skills: Path, monkeypatch: pytest.MonkeyPatch, spelling: str
    ) -> None:
        cell, _, kinds = _route(
            monkeypatch,
            _rule(skills, 2),
            {"selected_skill": spelling, "reasoning": "r"},
            SPEC_A,
        )
        assert kinds == ["selection", "route", "answer"]
        assert cell["routing"]["reference_matched"] is True

    def test_selection_parse_failure_is_a_route_failure(
        self, skills: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(eval_mod, "_call_api", lambda *a, **k: "not json")
        monkeypatch.setattr(eval_mod, "RATE_LIMIT_SLEEP_SEC", 0)
        result = eval_mod.eval_one_scenario(
            "",
            _rule(skills, 2),
            "spec",
            {"id": "S1", "input": "x", "expected_gate": "g"},
            "m",
            dry_run=False,
            arms=("description",),
        )
        cell = result["mechanisms"]["description"]
        assert cell["error"] == "route parse failure"
        assert cell["routing"]["route_failed"] is True
        assert cell["routing"]["reference_matched"] is False

    def test_k0_uses_one_route_call_and_does_not_compare_the_name(
        self, skills: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cell, systems, kinds = _route(
            monkeypatch,
            _rule(skills, 0),
            {"selected_skill": "alpha", "selected_reference": "references/a.md"},
        )
        assert kinds == ["route", "answer"]
        assert cell["routing"]["reference_matched"] is True
        assert "distractors" not in cell["routing"]
        assert "REF A BODY" in systems[0]


class TestRuleTargetsAndMetadata:
    def test_rule_target_ignores_distractors(self, skills: Path) -> None:
        rule = {"description": "d", "body": "b"}
        assert eval_mod._attach_distractors(rule, 3, None) is rule

    def test_rule_target_prompt_is_unchanged(self) -> None:
        rule = {"description": "d", "body": "b"}
        assert "Available rule:" in eval_mod.build_system_prompt("description", rule, "r")

    def test_flag_default_and_value(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("sys.argv", ["x", "--scenarios", "a.json"])
        assert eval_mod._parse_args().distractors == 0
        monkeypatch.setattr("sys.argv", ["x", "--scenarios", "a.json", "--distractors", "4"])
        assert eval_mod._parse_args().distractors == 4

    def test_help_says_rule_targets_ignore_it(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr("sys.argv", ["x", "--help"])
        with pytest.raises(SystemExit):
            eval_mod._parse_args()
        assert "Rule targets (rule_path) ignore this flag" in " ".join(
            capsys.readouterr().out.split()
        )

    def test_run_metadata_records_k(self) -> None:
        import argparse

        for k in (0, 3):
            args = argparse.Namespace(model="m", scenarios=[], distractors=k)
            assert eval_mod._build_run_provenance(args)["distractors"] == k


class TestLoadTarget:
    def _args(self, k: int) -> Any:
        import argparse

        return argparse.Namespace(distractors=k)

    def test_skill_without_reference_warns_when_k_positive(
        self, skills: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        rule = eval_mod._load_target(skills / "spec" / "SKILL.md", None, self._args(3))
        assert "distractors" not in rule
        assert "--distractors 3 ignored" in capsys.readouterr().err

    def test_skill_without_reference_is_quiet_at_k0(
        self, skills: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        eval_mod._load_target(skills / "spec" / "SKILL.md", None, self._args(0))
        assert capsys.readouterr().err == ""

    def test_rule_target_is_quiet(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        rule_path = tmp_path / "r.md"
        rule_path.write_text("---\ndescription: d\n---\nbody\n", "utf-8")
        eval_mod._load_target(rule_path, None, self._args(3))
        assert capsys.readouterr().err == ""

    def test_skill_with_reference_gets_distractors(self, skills: Path) -> None:
        rule = eval_mod._load_target(
            skills / "spec" / "SKILL.md",
            skills / "spec" / "references" / "a.md",
            self._args(2),
        )
        assert [n for n, _ in rule["distractors"]] == ["alpha", "zeta"]
