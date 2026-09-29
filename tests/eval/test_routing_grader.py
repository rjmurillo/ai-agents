"""Tests for the deterministic routing grader and its control checks (issue #5425)."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

from tests.eval._routing_corpus_test_support import (
    BOUNDED,
    INVESTIGATE,
    MULTI_FILE,
    PLAUSIBLE,
    REAL_CORPUS,
    SCOPE,
    copy_corpus,
    edit_scenario,
    grader,
    scenario_mod,
)

ALL_IDS = sorted(item.name for item in REAL_CORPUS.iterdir() if item.is_dir())


@pytest.fixture
def corpus(tmp_path: Path) -> Path:
    return copy_corpus(tmp_path)


def _load(root: Path, scenario_id: str) -> scenario_mod.Scenario:
    return scenario_mod.load_scenario(root / scenario_id)


def _swap_good_and_bad(root: Path, scenario_id: str) -> None:
    base = root / scenario_id
    (base / "known_good").rename(base / "tmp_swap")
    (base / "known_bad").rename(base / "known_good")
    (base / "tmp_swap").rename(base / "known_bad")


@pytest.mark.parametrize("scenario_id", ALL_IDS)
def test_known_good_passes_and_known_bad_fails(scenario_id: str) -> None:
    item = _load(REAL_CORPUS, scenario_id)

    assert grader.grade_overlay(item, "known_good").verdict is grader.Verdict.PASS
    assert grader.grade_overlay(item, "known_bad").verdict is grader.Verdict.FAIL


@pytest.mark.parametrize("scenario_id", ALL_IDS)
def test_every_control_holds_for_the_real_corpus(scenario_id: str) -> None:
    report = grader.verify_controls(_load(REAL_CORPUS, scenario_id))

    assert report.ok, [check for check in report.checks if not check.ok]


@pytest.mark.parametrize("scenario_id", ALL_IDS)
def test_untouched_initial_state_is_graded_fail(scenario_id: str) -> None:
    result = grader.grade_overlay(_load(REAL_CORPUS, scenario_id))

    assert result.verdict is grader.Verdict.FAIL
    assert result.missing_expected


def test_scope_expansion_known_bad_passes_tests_but_fails_on_scope() -> None:
    result = grader.grade_overlay(_load(REAL_CORPUS, SCOPE), "known_bad")

    assert all(command.passed for command in result.commands)
    assert result.scope_violations == ("pager/__init__.py", "pager/labels.py")
    assert result.verdict is grader.Verdict.FAIL


def test_scope_expansion_known_good_changes_only_the_expected_path() -> None:
    result = grader.grade_overlay(_load(REAL_CORPUS, SCOPE), "known_good")

    assert result.changed_paths == ("pager/paginate.py",)
    assert result.scope_violations == () and result.missing_expected == ()


def test_plausible_known_bad_passes_the_visible_check_and_names_the_finding() -> None:
    item = _load(REAL_CORPUS, PLAUSIBLE)
    result = grader.grade_overlay(item, "known_bad")

    assert item.reviewer_finding is not None
    assert grader._self_check_passes(item, "known_bad")
    assert item.reviewer_finding.evidence_marker in result.output
    assert result.verdict is grader.Verdict.FAIL


def test_symptom_patch_in_the_investigation_scenario_fails_the_root_cause_check() -> None:
    result = grader.grade_overlay(_load(REAL_CORPUS, INVESTIGATE), "known_bad")

    assert result.verdict is grader.Verdict.FAIL
    assert "gate_does_not_read_the_report_text" in result.output


def test_cross_file_invariant_is_what_fails_the_superficial_multi_file_change() -> None:
    result = grader.grade_overlay(_load(REAL_CORPUS, MULTI_FILE), "known_bad")

    assert result.verdict is grader.Verdict.FAIL
    assert "report_balance_always_equals_ledger_balance" in result.output


def test_materialize_resets_from_scratch_and_applies_overlays(tmp_path: Path) -> None:
    item = _load(REAL_CORPUS, BOUNDED)
    first = tmp_path / "first"
    second = tmp_path / "second"

    grader.materialize(item, first)
    grader.materialize(item, second, "known_good")

    assert not (tmp_path / "third").exists()
    assert "NotImplementedError" in (first / "slugger" / "core.py").read_text("utf-8")
    assert "NotImplementedError" not in (second / "slugger" / "core.py").read_text("utf-8")
    assert not list(first.rglob("*.fixture"))


def test_materialize_refuses_a_non_empty_destination(tmp_path: Path) -> None:
    (tmp_path / "stale.txt").write_text("left over", encoding="utf-8")

    with pytest.raises(ValueError, match="empty or absent"):
        grader.materialize(_load(REAL_CORPUS, BOUNDED), tmp_path)


def test_hidden_files_never_reach_the_driver_state(tmp_path: Path) -> None:
    item = _load(REAL_CORPUS, BOUNDED)
    grader.materialize(item, tmp_path / "work", "known_good")

    assert not list((tmp_path / "work").rglob("check_hidden_*"))


def test_grade_leaves_the_driver_directory_untouched(tmp_path: Path) -> None:
    item = _load(REAL_CORPUS, BOUNDED)
    workdir = tmp_path / "work"
    grader.materialize(item, workdir, "known_good")
    before = grader.manifest(workdir)

    grader.grade(item, workdir)

    assert grader.manifest(workdir) == before


def test_manifest_ignores_bytecode_and_cache_directories(tmp_path: Path) -> None:
    (tmp_path / "pkg" / "__pycache__").mkdir(parents=True)
    (tmp_path / "pkg" / "__pycache__" / "m.cpython-314.pyc").write_bytes(b"x")
    (tmp_path / "pkg" / "stray.pyc").write_bytes(b"x")
    (tmp_path / "pkg" / "m.py").write_text("x = 1\n", encoding="utf-8")

    assert list(grader.manifest(tmp_path)) == ["pkg/m.py"]


def test_changed_paths_reports_added_modified_and_deleted_files(tmp_path: Path) -> None:
    item = _load(REAL_CORPUS, BOUNDED)
    workdir = tmp_path / "work"
    grader.materialize(item, workdir)
    (workdir / "slugger" / "core.py").write_text("changed\n", encoding="utf-8")
    (workdir / "slugger" / "extra.py").write_text("new\n", encoding="utf-8")
    (workdir / "tests" / "check_visible_slugify.py").unlink()

    assert grader.changed_paths(item, workdir) == (
        "slugger/core.py",
        "slugger/extra.py",
        "tests/check_visible_slugify.py",
    )


def test_a_deleted_file_outside_the_allowed_scope_is_a_scope_violation(tmp_path: Path) -> None:
    item = _load(REAL_CORPUS, BOUNDED)
    workdir = tmp_path / "work"
    grader.materialize(item, workdir, "known_good")
    (workdir / "slugger" / "__init__.py").unlink()

    result = grader.grade(item, workdir)

    assert result.scope_violations == ("slugger/__init__.py",)
    assert result.verdict is grader.Verdict.FAIL


def test_scope_and_expected_path_helpers_use_glob_semantics() -> None:
    item = _load(REAL_CORPUS, MULTI_FILE)

    assert grader.scope_violations(item, ["ledger/store.py", "ledger/sub/x.py"]) == ()
    assert grader.scope_violations(item, ["README.md", "tests/check_visible_ledger.py"]) == (
        "README.md",
        "tests/check_visible_ledger.py",
    )
    assert grader.missing_expected(item, ["ledger/models.py"]) == (
        "ledger/store.py",
        "ledger/report.py",
    )


def test_a_forbidden_path_wins_over_an_allowed_glob(corpus: Path) -> None:
    edit_scenario(
        corpus,
        BOUNDED,
        allowed_scope={"paths": ["slugger/*.py"], "forbidden": ["slugger/core.py"]},
    )

    item = _load(corpus, BOUNDED)

    assert grader.scope_violations(item, ["slugger/core.py", "slugger/other.py"]) == (
        "slugger/core.py",
    )


def test_a_judge_dimension_cannot_override_a_failing_deterministic_check(corpus: Path) -> None:
    edit_scenario(
        corpus,
        BOUNDED,
        grading={"method": "deterministic", "judge_dimensions": ["readability"]},
    )
    item = _load(corpus, BOUNDED)

    assert item.judge_dimensions == ("readability",)
    assert grader.grade_overlay(item, "known_bad").verdict is grader.Verdict.FAIL


def test_a_timed_out_command_fails_the_grade(corpus: Path) -> None:
    slow = {"commands": [["python", "-c", "import time; time.sleep(30)"]], "timeout_seconds": 1}
    edit_scenario(corpus, BOUNDED, validation=slow)

    result = grader.grade_overlay(_load(corpus, BOUNDED), "known_good")

    assert result.commands[0].timed_out and not result.commands[0].passed
    assert result.verdict is grader.Verdict.FAIL


def test_a_failing_command_fails_even_when_paths_are_clean(corpus: Path) -> None:
    edit_scenario(
        corpus,
        BOUNDED,
        validation={"commands": [["python", "-c", "raise SystemExit(3)"]], "timeout_seconds": 5},
    )

    result = grader.grade_overlay(_load(corpus, BOUNDED), "known_good")

    assert result.scope_violations == () and result.missing_expected == ()
    assert result.commands[0].returncode == 3
    assert result.verdict is grader.Verdict.FAIL


def test_commands_run_on_the_current_interpreter_without_inherited_secrets(
    corpus: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ROUTING_SECRET_PROBE", "leaked")
    probe = "import os, sys; print(sys.executable); print(os.environ.get('ROUTING_SECRET_PROBE'))"
    edit_scenario(
        corpus,
        BOUNDED,
        validation={"commands": [["python", "-c", probe]], "timeout_seconds": 5},
    )

    output = grader.grade_overlay(_load(corpus, BOUNDED), "known_good").output

    assert sys.executable in output
    assert "leaked" not in output and output.strip().endswith("None")


def test_command_output_is_truncated_to_the_limit(corpus: Path) -> None:
    noisy = f"print('x' * {grader.OUTPUT_LIMIT_CHARS * 3})"
    edit_scenario(
        corpus,
        BOUNDED,
        validation={"commands": [["python", "-c", noisy]], "timeout_seconds": 5},
    )

    result = grader.grade_overlay(_load(corpus, BOUNDED), "known_good")

    assert len(result.commands[0].output) == grader.OUTPUT_LIMIT_CHARS


@pytest.mark.parametrize("scenario_id", ALL_IDS)
def test_swapping_good_and_bad_makes_the_controls_fail(corpus: Path, scenario_id: str) -> None:
    _swap_good_and_bad(corpus, scenario_id)

    report = grader.verify_controls(_load(corpus, scenario_id))

    assert not report.ok
    names = {check.name for check in report.checks if not check.ok}
    assert {"known_good_passes", "known_bad_fails"} & names


def test_a_grader_that_always_passes_is_caught_by_the_known_bad_control(corpus: Path) -> None:
    always = {"commands": [["python", "-c", "pass"]], "timeout_seconds": 5}
    edit_scenario(corpus, BOUNDED, validation=always)

    report = grader.verify_controls(_load(corpus, BOUNDED))

    assert {check.name for check in report.checks if not check.ok} == {"known_bad_fails"}


def test_reviewer_marker_that_the_grader_never_prints_fails_the_control(corpus: Path) -> None:
    finding = {"summary": "s", "evidence_marker": "NEVER_PRINTED_MARKER"}
    edit_scenario(corpus, PLAUSIBLE, reviewer_finding=finding)

    report = grader.verify_controls(_load(corpus, PLAUSIBLE))

    failed = {check.name for check in report.checks if not check.ok}
    assert failed == {"known_bad_evidence_matches_finding"}


def test_a_known_bad_that_fails_the_visible_check_is_not_plausible(corpus: Path) -> None:
    target = corpus / PLAUSIBLE / "known_bad" / "phrases" / "detect.py.fixture"
    target.write_text("def has_contradiction(text):\n    raise RuntimeError('boom')\n", "utf-8")

    report = grader.verify_controls(_load(corpus, PLAUSIBLE))

    failed = {check.name for check in report.checks if not check.ok}
    assert "known_bad_passes_self_check" in failed


def test_scope_expansion_control_fails_when_known_bad_stays_in_scope(corpus: Path) -> None:
    shutil.rmtree(corpus / SCOPE / "known_bad" / "pager")
    (corpus / SCOPE / "known_bad" / "pager").mkdir()
    shutil.copyfile(
        corpus / SCOPE / "known_good" / "pager" / "paginate.py.fixture",
        corpus / SCOPE / "known_bad" / "pager" / "paginate.py.fixture",
    )

    report = grader.verify_controls(_load(corpus, SCOPE))

    failed = {check.name for check in report.checks if not check.ok}
    assert "known_bad_flags_scope_violation" in failed


def test_materialize_refuses_an_overlay_name_that_is_not_a_control_fixture(tmp_path: Path) -> None:
    item = _load(REAL_CORPUS, BOUNDED)

    for name in ("hidden", "initial", "known_bad/../hidden", "../x"):
        with pytest.raises(ValueError, match="unknown overlay"):
            grader.materialize(item, tmp_path / "work", name)
    assert not (tmp_path / "work").exists()


def test_a_symlink_in_the_driver_directory_fails_grading_without_following_it(
    tmp_path: Path,
) -> None:
    item = _load(REAL_CORPUS, BOUNDED)
    workdir = tmp_path / "work"
    grader.materialize(item, workdir, "known_good")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "host.txt").write_text("host secret", encoding="utf-8")
    (workdir / "leak.txt").symlink_to(outside / "host.txt")
    (workdir / "leakdir").symlink_to(outside, target_is_directory=True)

    result = grader.grade(item, workdir)

    assert result.verdict is grader.Verdict.FAIL
    assert "symlink:leak.txt" in result.scope_violations
    assert "symlink:leakdir" in result.scope_violations
    assert result.commands == ()
    assert grader.manifest(workdir)["leak.txt"] == "symlink"


def test_a_known_good_that_lowercases_before_filtering_is_rejected_by_the_hidden_checks(
    corpus: Path,
) -> None:
    target = corpus / BOUNDED / "known_good" / "slugger" / "core.py.fixture"
    target.write_text(
        '"""Text helpers."""\n\nimport re\n\n_NON_ALNUM = re.compile(r"[^a-z0-9]+")\n\n\n'
        'def slugify(text: str) -> str:\n    return _NON_ALNUM.sub("-", text.lower()).strip("-")\n',
        encoding="utf-8",
    )

    result = grader.grade_overlay(_load(corpus, BOUNDED), "known_good")

    assert result.verdict is grader.Verdict.FAIL
    assert "letters_that_lowercase_into_ascii" in result.output
