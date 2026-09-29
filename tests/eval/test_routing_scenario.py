"""Tests for the routing scenario contract and corpus loader (issue #5425)."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest

from tests.eval._routing_corpus_test_support import (
    ARCHITECTURE,
    BOUNDED,
    INVESTIGATE,
    MULTI_FILE,
    PLAUSIBLE,
    REAL_CORPUS,
    SCOPE,
    copy_corpus,
    edit_scenario,
    fixtures_mod,
    read_scenario,
    scenario_mod,
)

Category = scenario_mod.Category
RoutingCorpusError = scenario_mod.RoutingCorpusError


@pytest.fixture
def corpus(tmp_path: Path) -> Path:
    return copy_corpus(tmp_path)


def test_real_corpus_covers_each_category_exactly_once() -> None:
    scenarios = scenario_mod.load_corpus(REAL_CORPUS)

    assert sorted(item.category.value for item in scenarios) == sorted(c.value for c in Category)
    assert len({item.scenario_id for item in scenarios}) == len(scenarios) == 6


def test_real_corpus_scenarios_carry_the_contract_fields() -> None:
    for item in scenario_mod.load_corpus(REAL_CORPUS):
        assert item.allowed_paths and item.expected_changed_paths
        assert item.invariants and item.acceptance_criteria
        assert item.validation.commands and item.provenance.kind in {"synthetic", "adapted"}


def test_category_specific_fields_appear_only_where_required() -> None:
    by_id = {item.scenario_id: item for item in scenario_mod.load_corpus(REAL_CORPUS)}

    assert by_id[PLAUSIBLE].reviewer_finding is not None and by_id[PLAUSIBLE].self_check is not None
    assert by_id[ARCHITECTURE].architecture is not None
    assert by_id[SCOPE].forbidden_paths
    for scenario_id in (BOUNDED, MULTI_FILE, INVESTIGATE):
        assert by_id[scenario_id].reviewer_finding is None
        assert by_id[scenario_id].architecture is None


def test_architecture_decision_is_separate_from_the_driver_contract() -> None:
    item = {s.scenario_id: s for s in scenario_mod.load_corpus(REAL_CORPUS)}[ARCHITECTURE]
    architecture = item.architecture

    assert architecture is not None
    assert architecture.resolved_decision != architecture.driver_contract
    assert architecture.driver_contract != item.requirement
    assert architecture.resolved_decision.casefold() not in item.requirement.casefold()


def test_historical_adaptations_cite_files_that_exist_in_tree() -> None:
    repo_root = REAL_CORPUS.parents[2]
    adapted = [s for s in scenario_mod.load_corpus(REAL_CORPUS) if s.provenance.kind == "adapted"]

    assert {s.scenario_id for s in adapted} == {INVESTIGATE, PLAUSIBLE}
    for item in adapted:
        assert (repo_root / item.provenance.source).is_file()


def test_missing_category_is_refused(corpus: Path) -> None:
    shutil.move(corpus / SCOPE, corpus.parent / "moved")

    with pytest.raises(RoutingCorpusError, match="missing required categories.*scope_expansion"):
        scenario_mod.load_corpus(corpus)


def test_duplicate_scenario_id_is_refused(corpus: Path) -> None:
    shutil.copytree(corpus / BOUNDED, corpus / "RB-99-copy")

    with pytest.raises(RoutingCorpusError, match="duplicate scenario id"):
        scenario_mod.load_corpus(corpus)


def test_directory_name_must_equal_the_scenario_id(corpus: Path) -> None:
    shutil.move(corpus / BOUNDED, corpus / "RB-01-renamed")

    with pytest.raises(RoutingCorpusError, match="directory name must equal scenario id"):
        scenario_mod.load_corpus(corpus)


def test_corpus_root_must_be_a_directory(tmp_path: Path) -> None:
    with pytest.raises(RoutingCorpusError, match="not a directory"):
        scenario_mod.load_corpus(tmp_path / "absent")


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"validation": None}, "missing required key"),
        ({"expected_changed_paths": None}, "missing required key"),
        ({"surprise": 1}, "unknown key"),
        ({"schema_version": 2}, "schema_version"),
        ({"category": "made_up"}, "is not one of"),
        ({"difficulty": "hard"}, "is not one of"),
        ({"requirement": "   "}, "non-empty string"),
        ({"invariants": []}, "non-empty list"),
        ({"acceptance_criteria": ["ok", 3]}, "non-empty string"),
    ],
)
def test_malformed_top_level_metadata_is_refused(
    corpus: Path, changes: dict[str, Any], message: str
) -> None:
    edit_scenario(corpus, BOUNDED, **changes)

    with pytest.raises(RoutingCorpusError, match=message):
        scenario_mod.load_scenario(corpus / BOUNDED)


@pytest.mark.parametrize(
    "scope",
    [
        {"paths": []},
        {"paths": ["/etc/passwd"]},
        {"paths": ["../outside.py"]},
        {"paths": ["a\\b.py"]},
        {"paths": ["slugger/core.py"], "forbidden": "not-a-list"},
        {"paths": ["slugger/core.py"], "extra": []},
        {"forbidden": []},
    ],
)
def test_malformed_scope_is_refused(corpus: Path, scope: dict[str, Any]) -> None:
    edit_scenario(corpus, BOUNDED, allowed_scope=scope)

    with pytest.raises(RoutingCorpusError):
        scenario_mod.load_scenario(corpus / BOUNDED)


@pytest.mark.parametrize(
    "validation",
    [
        {"commands": [], "timeout_seconds": 5},
        {"commands": [["pytest", "-q"]], "timeout_seconds": 5},
        {"commands": [["python", "-c", "pass"]], "timeout_seconds": 0},
        {"commands": [["python", "-c", "pass"]], "timeout_seconds": 301},
        {"commands": [["python", "-c", "pass"]], "timeout_seconds": True},
        {"commands": [["python", "-c", "pass"]]},
        {"commands": ["python -c pass"], "timeout_seconds": 5},
    ],
)
def test_malformed_validation_metadata_is_refused(corpus: Path, validation: dict[str, Any]) -> None:
    edit_scenario(corpus, BOUNDED, validation=validation)

    with pytest.raises(RoutingCorpusError):
        scenario_mod.load_scenario(corpus / BOUNDED)


@pytest.mark.parametrize(
    "provenance",
    [
        {"kind": "synthetic"},
        {"kind": "adapted", "source": "evals/x.json"},
        {"kind": "adapted", "source": "../x.json", "reference": "issue 1"},
        {"kind": "invented", "reason": "x"},
    ],
)
def test_malformed_provenance_is_refused(corpus: Path, provenance: dict[str, Any]) -> None:
    edit_scenario(corpus, BOUNDED, provenance=provenance)

    with pytest.raises(RoutingCorpusError):
        scenario_mod.load_scenario(corpus / BOUNDED)


def test_grading_method_other_than_deterministic_is_refused(corpus: Path) -> None:
    edit_scenario(corpus, BOUNDED, grading={"method": "model_judge"})

    with pytest.raises(RoutingCorpusError, match="only 'deterministic'"):
        scenario_mod.load_scenario(corpus / BOUNDED)


def test_reset_method_other_than_fresh_copy_is_refused(corpus: Path) -> None:
    edit_scenario(corpus, BOUNDED, reset={"method": "git_clean", "notes": "x"})

    with pytest.raises(RoutingCorpusError, match="only 'fresh_copy'"):
        scenario_mod.load_scenario(corpus / BOUNDED)


def test_invalid_json_and_missing_scenario_file_are_refused(corpus: Path) -> None:
    (corpus / BOUNDED / "scenario.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(RoutingCorpusError, match="invalid JSON"):
        scenario_mod.load_scenario(corpus / BOUNDED)

    (corpus / BOUNDED / "scenario.json").unlink()
    with pytest.raises(RoutingCorpusError, match="cannot read"):
        scenario_mod.load_scenario(corpus / BOUNDED)


@pytest.mark.parametrize("name", ["initial", "hidden", "known_good", "known_bad"])
def test_missing_fixture_directory_is_refused(corpus: Path, name: str) -> None:
    shutil.move(corpus / BOUNDED / name, corpus.parent / f"gone-{name}")

    with pytest.raises(RoutingCorpusError, match=f"missing fixture directory {name}/"):
        scenario_mod.load_scenario(corpus / BOUNDED)


def test_empty_fixture_directory_is_refused(corpus: Path) -> None:
    for path in (corpus / BOUNDED / "known_bad").rglob("*.fixture"):
        path.unlink()

    with pytest.raises(RoutingCorpusError, match="known_bad/ must hold files"):
        scenario_mod.load_scenario(corpus / BOUNDED)


def test_fixture_file_without_the_suffix_is_refused(corpus: Path) -> None:
    (corpus / BOUNDED / "initial" / "live.py").write_text("x = 1\n", encoding="utf-8")

    with pytest.raises(RoutingCorpusError, match="must end with .fixture"):
        scenario_mod.load_scenario(corpus / BOUNDED)


def test_hidden_file_shadowing_an_initial_file_is_refused(corpus: Path) -> None:
    source = corpus / BOUNDED / "initial" / "tests" / "check_visible_slugify.py.fixture"
    shutil.copyfile(
        source, corpus / BOUNDED / "hidden" / "tests" / "check_visible_slugify.py.fixture"
    )

    with pytest.raises(RoutingCorpusError, match="hidden/ shadows initial/"):
        scenario_mod.load_scenario(corpus / BOUNDED)


@pytest.mark.parametrize("name", ["Codex", "claude", "GPT", "sol", "Terra", "luna", "copilot"])
def test_model_name_in_the_requirement_is_refused(corpus: Path, name: str) -> None:
    edit_scenario(corpus, BOUNDED, requirement=f"Implement slugify. Ask {name} for hints.")

    with pytest.raises(RoutingCorpusError, match="model-agnostic"):
        scenario_mod.load_scenario(corpus / BOUNDED)


def test_model_name_in_a_driver_visible_fixture_is_refused(corpus: Path) -> None:
    target = corpus / BOUNDED / "initial" / "slugger" / "core.py.fixture"
    target.write_text(target.read_text("utf-8") + "# tuned for opus\n", encoding="utf-8")

    with pytest.raises(RoutingCorpusError, match="initial/slugger/core.py.*opus"):
        scenario_mod.load_scenario(corpus / BOUNDED)


def test_model_word_inside_a_longer_word_is_not_a_model_name(corpus: Path) -> None:
    edit_scenario(corpus, BOUNDED, title="Solve solar terrain problems with clauded text")

    assert scenario_mod.load_scenario(corpus / BOUNDED).scenario_id == BOUNDED


def test_known_good_line_visible_to_the_driver_is_an_answer_leak(corpus: Path) -> None:
    answer = '    return _NON_ALNUM.sub("-", text).strip("-").lower()'
    target = corpus / BOUNDED / "initial" / "slugger" / "__init__.py.fixture"
    target.write_text(target.read_text("utf-8") + f"# hint\n#{answer}\n", encoding="utf-8")

    with pytest.raises(RoutingCorpusError, match="answer-key leak"):
        scenario_mod.load_scenario(corpus / BOUNDED)


def test_resolved_decision_in_driver_text_is_an_answer_leak(corpus: Path) -> None:
    data = read_scenario(corpus, ARCHITECTURE)
    decision = data["architecture"]["resolved_decision"]
    edit_scenario(corpus, ARCHITECTURE, requirement=f"Add a limiter. {decision}")

    with pytest.raises(RoutingCorpusError, match="resolved_decision"):
        scenario_mod.load_scenario(corpus / ARCHITECTURE)


@pytest.mark.parametrize(
    ("scenario_id", "changes", "message"),
    [
        (PLAUSIBLE, {"reviewer_finding": None}, "reviewer_finding is required"),
        (PLAUSIBLE, {"self_check": None}, "self_check is required"),
        (
            BOUNDED,
            {"reviewer_finding": {"summary": "x", "evidence_marker": "y"}},
            "reviewer_finding",
        ),
        (ARCHITECTURE, {"architecture": None}, "architecture is required"),
        (
            BOUNDED,
            {
                "architecture": {
                    "question": "q",
                    "context_path": "a",
                    "resolved_decision": "d",
                    "driver_contract": "c",
                }
            },
            "architecture is required",
        ),
        (SCOPE, {"allowed_scope": {"paths": ["pager/paginate.py"]}}, "at least one forbidden path"),
    ],
)
def test_category_specific_fields_are_enforced(
    corpus: Path, scenario_id: str, changes: dict[str, Any], message: str
) -> None:
    edit_scenario(corpus, scenario_id, **changes)

    with pytest.raises(RoutingCorpusError, match=message):
        scenario_mod.load_scenario(corpus / scenario_id)


def test_architecture_context_must_exist_in_initial_state(corpus: Path) -> None:
    data = read_scenario(corpus, ARCHITECTURE)
    data["architecture"]["context_path"] = "docs/absent.md"
    edit_scenario(corpus, ARCHITECTURE, architecture=data["architecture"])

    with pytest.raises(RoutingCorpusError, match="not in initial/"):
        scenario_mod.load_scenario(corpus / ARCHITECTURE)


def test_driver_contract_equal_to_the_requirement_is_refused(corpus: Path) -> None:
    data = read_scenario(corpus, ARCHITECTURE)
    data["architecture"]["driver_contract"] = data["requirement"]
    edit_scenario(corpus, ARCHITECTURE, architecture=data["architecture"])

    with pytest.raises(RoutingCorpusError, match="must differ from the requirement"):
        scenario_mod.load_scenario(corpus / ARCHITECTURE)


def test_fixture_files_strip_the_suffix_and_reject_unreadable_text(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "m.py.fixture").write_bytes(b"\xff\xfe\x00bad")

    files = scenario_mod.fixture_files(tmp_path)

    assert list(files) == ["a/m.py"]
    with pytest.raises(RoutingCorpusError, match="cannot read fixture"):
        fixtures_mod.read_fixture_text(files["a/m.py"])


def test_a_symlink_inside_a_fixture_tree_is_refused(corpus: Path) -> None:
    outside = corpus.parent / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    (corpus / BOUNDED / "initial" / "link.txt.fixture").symlink_to(outside)

    with pytest.raises(RoutingCorpusError, match="symlinks"):
        scenario_mod.load_scenario(corpus / BOUNDED)


def test_a_second_scenario_in_one_category_is_refused(corpus: Path) -> None:
    shutil.copytree(corpus / BOUNDED, corpus / "RB-07-second-bounded")
    edit_scenario(corpus, "RB-07-second-bounded", id="RB-07-second-bounded")

    with pytest.raises(RoutingCorpusError, match="one primary scenario per category.*bounded"):
        scenario_mod.load_corpus(corpus)


@pytest.mark.parametrize("field", ["invariants", "acceptance_criteria"])
def test_known_good_line_in_driver_visible_metadata_is_an_answer_leak(
    corpus: Path, field: str
) -> None:
    answer = 'return _NON_ALNUM.sub("-", text).strip("-").lower()'
    edit_scenario(corpus, BOUNDED, **{field: ["Keep it short.", answer]})

    with pytest.raises(RoutingCorpusError, match="answer-key leak"):
        scenario_mod.load_scenario(corpus / BOUNDED)


def test_known_good_line_in_the_driver_contract_is_an_answer_leak(corpus: Path) -> None:
    data = read_scenario(corpus, ARCHITECTURE)
    data["architecture"]["driver_contract"] += (
        " Use window_index = int(self._clock() // self._window)."
    )
    edit_scenario(corpus, ARCHITECTURE, architecture=data["architecture"])

    with pytest.raises(RoutingCorpusError, match="answer-key leak"):
        scenario_mod.load_scenario(corpus / ARCHITECTURE)
