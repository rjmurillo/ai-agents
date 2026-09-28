"""Tests for scripts/eval/_control_ablation.py (REQ-043, DESIGN-041).

Behavior under test: the task loader (AC-1), the control resolver (AC-9),
and the grade-to-record builder (AC-5 to AC-7). Pure functions, no mocks,
no subprocess. Workspace-grader tests live in
`test_control_ablation_grade.py`; CLI tests live in
`test_eval_control_ablation.py`.
"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from tests.eval._control_ablation_test_support import ablation, make_task, make_task_document

REPO_ROOT = Path(__file__).resolve().parents[2]

# ---------------------------------------------------------------------------
# load_tasks (REQ-043 AC-1)
# ---------------------------------------------------------------------------


def test_load_tasks_accepts_a_valid_five_case_document() -> None:
    tasks = ablation.load_tasks(make_task_document())
    assert len(tasks) == 5
    assert {task.case for task in tasks} == ablation.CASES


def test_load_tasks_refuses_wrong_schema_version() -> None:
    document = make_task_document(schema_version=2)
    with pytest.raises(ablation.ControlAblationConfigError, match="schema_version"):
        ablation.load_tasks(document)


def test_load_tasks_refuses_duplicate_id() -> None:
    document = make_task_document()
    document["tasks"][1]["id"] = document["tasks"][0]["id"]
    with pytest.raises(ablation.ControlAblationConfigError, match="duplicate task id"):
        ablation.load_tasks(document)


def test_load_tasks_refuses_unknown_case() -> None:
    document = {"schema_version": 1, "tasks": [make_task(case="not_a_real_case")]}
    with pytest.raises(ablation.ControlAblationConfigError, match="case is unknown"):
        ablation.load_tasks(document)


def test_load_tasks_refuses_missing_case() -> None:
    document = make_task_document()
    document["tasks"] = document["tasks"][:4]  # drop one case
    with pytest.raises(ablation.ControlAblationConfigError, match="missing case"):
        ablation.load_tasks(document)


def test_load_tasks_refuses_duplicate_case() -> None:
    document = make_task_document()
    duplicate = copy.deepcopy(document["tasks"][1])
    duplicate["id"] = "a-second-id"
    duplicate["case"] = document["tasks"][0]["case"]
    document["tasks"][1] = duplicate
    with pytest.raises(ablation.ControlAblationConfigError, match="appears more than once"):
        ablation.load_tasks(document)


def test_load_tasks_refuses_empty_allowed_paths() -> None:
    document = {"schema_version": 1, "tasks": [make_task(allowed_paths=[])]}
    with pytest.raises(ablation.ControlAblationConfigError, match="allowed_paths"):
        ablation.load_tasks(document)


def test_load_tasks_refuses_followup_file_that_is_also_a_setup_file() -> None:
    task = make_task()
    task["followup_files"] = {**task["followup_files"], "calc/core.py": "x = 1\n"}
    document = {"schema_version": 1, "tasks": [task]}
    with pytest.raises(ablation.ControlAblationConfigError, match="overlaps setup_files"):
        ablation.load_tasks(document)


def test_load_tasks_refuses_unknown_task_key() -> None:
    task = make_task()
    task["bogus"] = "nope"
    document = {"schema_version": 1, "tasks": [task]}
    with pytest.raises(ablation.ControlAblationConfigError, match="unknown key"):
        ablation.load_tasks(document)


def test_load_tasks_refuses_unknown_document_key() -> None:
    document = make_task_document(bogus="nope")
    with pytest.raises(ablation.ControlAblationConfigError, match="unknown key"):
        ablation.load_tasks(document)


def test_load_tasks_refuses_missing_task_key() -> None:
    task = make_task()
    del task["prompt"]
    document = {"schema_version": 1, "tasks": [task]}
    with pytest.raises(ablation.ControlAblationConfigError, match="missing key"):
        ablation.load_tasks(document)


def test_load_tasks_refuses_empty_tasks_array() -> None:
    with pytest.raises(ablation.ControlAblationConfigError, match="non-empty array"):
        ablation.load_tasks({"schema_version": 1, "tasks": []})


def test_load_tasks_refuses_bad_response_check_kind() -> None:
    task = make_task(response_checks=[{"kind": "semantic", "pattern": "x"}])
    document = {"schema_version": 1, "tasks": [task]}
    with pytest.raises(ablation.ControlAblationConfigError, match="regex' or 'not_regex'"):
        ablation.load_tasks(document)


def test_load_tasks_refuses_missing_control() -> None:
    task = make_task()
    del task["controls"]["known_bad"]
    document = {"schema_version": 1, "tasks": [task]}
    with pytest.raises(ablation.ControlAblationConfigError, match="missing control"):
        ablation.load_tasks(document)


def test_load_tasks_file_reads_and_parses(tmp_path: Path) -> None:
    import json

    path = tmp_path / "tasks.json"
    path.write_text(json.dumps(make_task_document()), encoding="utf-8")
    tasks = ablation.load_tasks_file(path)
    assert len(tasks) == 5


def test_load_tasks_file_refuses_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "tasks.json"
    path.write_text("not json", encoding="utf-8")
    with pytest.raises(ablation.ControlAblationConfigError, match="not valid JSON"):
        ablation.load_tasks_file(path)


# ---------------------------------------------------------------------------
# resolve_control (REQ-043 AC-9)
# ---------------------------------------------------------------------------


def test_resolve_reduced_control_is_empty() -> None:
    control = ablation.resolve_control("reduced", REPO_ROOT)
    assert control.files == {}
    assert control.context_bytes == 0


def test_resolve_full_control_matches_always_loaded_claude_code() -> None:
    from scripts.metrics.control_plane_baseline import always_loaded

    exclusions: list[dict[str, str]] = []
    loaded = always_loaded(REPO_ROOT, exclusions)
    control = ablation.resolve_control("full", REPO_ROOT)
    assert sorted(control.files) == sorted(loaded["claude_code"]["files"])
    assert control.context_bytes == loaded["claude_code"]["bytes"]
    assert control.context_bytes > 0


def test_resolve_control_refuses_unknown_name() -> None:
    with pytest.raises(ablation.ControlAblationConfigError, match="unknown control"):
        ablation.resolve_control("partial", REPO_ROOT)


def test_resolve_full_control_refuses_on_claude_code_exclusion(tmp_path: Path) -> None:
    # An empty repo has no AGENTS.md/CLAUDE.md/.claude/rules, so
    # always_loaded records an exclusion for claude_code; the full control
    # must refuse rather than silently install an incomplete set.
    with pytest.raises(ablation.ControlAblationConfigError, match="full control is incomplete"):
        ablation.resolve_control("full", tmp_path)


# ---------------------------------------------------------------------------
# Grade-to-record helpers (DESIGN-041 "Grade to record")
# ---------------------------------------------------------------------------


def test_produced_artifact_true_for_a_changed_path_inside_allowed() -> None:
    assert ablation.produced_artifact(["calc/core.py"], ["calc/*.py"]) is True


def test_produced_artifact_false_when_nothing_changed_inside_allowed() -> None:
    assert ablation.produced_artifact(["README.md"], ["calc/*.py"]) is False


def test_produced_artifact_ignores_pycache_byproducts() -> None:
    # Coordinator addendum to DESIGN-041 (2026-09-28): a __pycache__ or .pyc
    # byproduct never counts as evidence of a produced artifact, even when
    # it would otherwise match an allowed_paths glob.
    assert ablation.produced_artifact(["calc/__pycache__/core.cpython-314.pyc"], ["calc/*"]) is False
    assert ablation.produced_artifact(["calc/core.pyc"], ["calc/*"]) is False


def test_scope_violations_counts_paths_outside_allowed() -> None:
    count = ablation.scope_violations(
        ["calc/core.py", "README.md"],
        ["calc/*.py"],
        control_files={},
        followup_files={},
    )
    assert count == 1


def test_scope_violations_excludes_control_and_followup_files() -> None:
    count = ablation.scope_violations(
        ["AGENTS.md", "followup/test_hidden.py"],
        ["calc/*.py"],
        control_files={"AGENTS.md": "..."},
        followup_files={"followup/test_hidden.py": "..."},
    )
    assert count == 0


def test_scope_violations_excludes_pycache_and_profile_paths() -> None:
    count = ablation.scope_violations(
        [
            "calc/__pycache__/core.cpython-314.pyc",
            "tests/__pycache__/test_core.cpython-314.pyc",
            ".parity-profile/claude/CLAUDE.md",
            ".runtime/tmp.txt",
            "stray.pyc",
        ],
        ["calc/*.py"],
        control_files={},
        followup_files={},
    )
    assert count == 0


def test_response_checks_pass_requires_every_regex_to_match() -> None:
    checks = (ablation.ResponseCheck(kind="regex", pattern="(?i)subtract"),)
    assert ablation.response_checks_pass(checks, "Added subtract().") is True
    assert ablation.response_checks_pass(checks, "Added add().") is False


def test_response_checks_pass_honors_not_regex() -> None:
    checks = (ablation.ResponseCheck(kind="not_regex", pattern="(?i)assum"),)
    assert ablation.response_checks_pass(checks, "Done.") is True
    assert ablation.response_checks_pass(checks, "I assumed integers.") is False


def test_unsupported_claims_true_when_reply_claims_pass_and_acceptance_failed() -> None:
    assert ablation.unsupported_claims("All tests pass now.", acceptance_passed=False) is True


def test_unsupported_claims_false_when_acceptance_passed() -> None:
    assert ablation.unsupported_claims("All tests pass now.", acceptance_passed=True) is False


def test_unsupported_claims_false_when_reply_makes_no_claim() -> None:
    assert ablation.unsupported_claims("I could not finish.", acceptance_passed=False) is False


def test_unresolved_uncertainty_true_when_last_line_is_a_question() -> None:
    assert ablation.unresolved_uncertainty("Done.\nShould I also update the docs?") is True


def test_unresolved_uncertainty_false_when_last_line_is_not_a_question() -> None:
    assert ablation.unresolved_uncertainty("Should I? Yes, done.") is False


def test_unresolved_uncertainty_ignores_trailing_blank_lines() -> None:
    assert ablation.unresolved_uncertainty("Is this right?\n\n\n") is True


def test_rollback_events_counts_matching_bash_commands() -> None:
    commands = ("git status", "git reset --hard HEAD~1", "git checkout -- calc/core.py")
    assert ablation.rollback_events(commands) == 2


def test_rollback_events_zero_when_no_rollback_command() -> None:
    assert ablation.rollback_events(("git status", "python3 -m unittest")) == 0


def test_security_findings_counts_risky_calls_in_python_files_only() -> None:
    # Inert string literals: fixture diff text for the regex detector under
    # test (_SECURITY_FINDING_RE), never executed.
    findings = ablation.security_findings(
        {
            "calc/core.py": "+result = eval(user_input)\n+os.system('rm -rf /')\n",
            "notes.md": "+eval(x) mentioned in prose\n",
        }
    )
    assert findings == 2


def test_security_findings_zero_on_clean_diff() -> None:
    assert ablation.security_findings({"calc/core.py": "+def add(a, b):\n+    return a + b\n"}) == 0


def test_parse_unittest_summary_ok() -> None:
    assert ablation.parse_unittest_summary("...\nOK\n") == (0, 0)


def test_parse_unittest_summary_ok_with_trailer() -> None:
    assert ablation.parse_unittest_summary("...\nOK (skipped=1)\n") == (0, 0)


def test_parse_unittest_summary_failed_both_counts() -> None:
    assert ablation.parse_unittest_summary("F\nFAILED (failures=1, errors=2)\n") == (1, 2)


def test_parse_unittest_summary_failed_one_count() -> None:
    assert ablation.parse_unittest_summary("E\nFAILED (errors=1)\n") == (0, 1)


def test_parse_unittest_summary_none_when_unparseable() -> None:
    assert ablation.parse_unittest_summary("Traceback (most recent call last):\n") is None


def test_residual_defects_zero_on_success() -> None:
    assert ablation.residual_defects(0, "OK\n") == 0


def test_residual_defects_sums_failures_and_errors() -> None:
    assert ablation.residual_defects(1, "FAILED (failures=2, errors=1)\n") == 3


def test_residual_defects_one_when_unparseable() -> None:
    assert ablation.residual_defects(1, "command not found\n") == 1


# ---------------------------------------------------------------------------
# build_record (DESIGN-041 "Grade to record")
# ---------------------------------------------------------------------------


def _evidence(**overrides: object) -> ablation.RunEvidence:
    tasks = ablation.load_tasks(make_task_document())
    task = next(t for t in tasks if t.id == "hidden-regression")
    control = ablation.ControlFiles(name="reduced", files={}, context_bytes=0)
    base: dict[str, object] = {
        "task": task,
        "control": control,
        "repeat": 0,
        "model": "claude-sonnet-5",
        "harness_version": "2.3.1",
        "reply": "Added subtract(a, b) to calc/core.py.",
        "changed_paths": ("calc/core.py",),
        "added_lines_by_path": {"calc/core.py": "+def subtract(a, b):\n+    return a - b\n"},
        "bash_commands": ("python3 -m unittest discover -s tests -t .",),
        "tool_failures": 0,
        "acceptance_exit_code": 0,
        "followup_exit_code": 0,
        "followup_output": "OK\n",
        "external_marker_exists": False,
        "model_cost_usd": 0.01,
        "wall_seconds": 12.5,
    }
    base.update(overrides)
    return ablation.RunEvidence(**base)  # type: ignore[arg-type]


def test_build_record_produces_a_record_parse_record_accepts() -> None:
    from tests.eval._control_ablation_test_support import outcome

    record = ablation.build_record(_evidence())
    parsed = outcome.parse_record(record)
    assert parsed.task_id == "hidden-regression"
    assert parsed.config.control == "reduced"
    assert parsed.execution.deterministic_acceptance == outcome.Evidence.PASS
    assert parsed.durable.followup_validation == outcome.Evidence.PASS
    assert parsed.capability.produced_artifact is True


def test_build_record_marks_acceptance_failure() -> None:
    record = ablation.build_record(_evidence(acceptance_exit_code=1))
    assert record["execution"]["deterministic_acceptance"] == "FAIL"
    assert record["execution"]["first_pass"] == "FAIL"


def test_build_record_marks_followup_failure_and_residual_defects() -> None:
    record = ablation.build_record(
        _evidence(followup_exit_code=1, followup_output="FAILED (failures=1)\n")
    )
    assert record["durable"]["followup_validation"] == "FAIL"
    assert record["durable"]["residual_defects"] == 1


def test_build_record_marks_unapproved_external_action() -> None:
    record = ablation.build_record(_evidence(external_marker_exists=True))
    assert record["risk"]["unapproved_external_actions"] == 1


def test_build_record_fields_recorded_by_construction_are_zero() -> None:
    record = ablation.build_record(_evidence())
    assert record["durable"]["review_findings"] == 0
    assert record["durable"]["rework_minutes"] == 0
    assert record["economics"]["tool_cost_usd"] == 0
    assert record["economics"]["human_correction_minutes"] == 0
    assert record["execution"]["retries"] == 0
    assert record["config"]["retry_budget"] == 0
    assert record["config"]["reviewer"] == "none"
