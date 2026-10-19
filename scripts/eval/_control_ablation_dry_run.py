"""Dry run for the reduced-control ablation runner (REQ-046 AC-2, issue #5768).

Applies every task's `known_good` and `known_bad` controls to a real seeded
workspace, grades them for real, and checks that the grader discriminates. No
model call is made. The reviewer reply is a canned fixture that runs through the
real parser, and `human_correction_minutes` is a labeled fixture value, so the
report names both as inputs and not measurements. The rollback is real.
`eval_control_ablation.py` maps the returned status to an exit code.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import _control_ablation as ablation
import _control_ablation_grade as grade
import _control_ablation_tasks as ablation_tasks
import _durable_outcome as durable_outcome
import _durable_review as durable_review
import _outcome_record as outcome_record

DRY_RUN_KINDS = ("known_good", "known_bad")
#: Canned reviewer replies for `--dry-run`, which makes no model call. They run
#: through the real `parse_review`, so the dry run proves a well-formed reply is
#: recorded as its finding count. Both are well-formed: a malformed reply is
#: covered by the `parse_review` unit tests, not by this dry run.
DRY_RUN_REVIEWS = {
    "known_good": f'{durable_review.REVIEW_MARKER} {{"findings": []}}',
    "known_bad": (
        f"{durable_review.REVIEW_MARKER}"
        ' {"findings": ["canned finding for the known-bad fixture"]}'
    ),
}
#: A dry-run fixture has no human in it. This value is a labeled input to the
#: classifier, never a measurement, and the report says so.
DRY_RUN_HUMAN_MINUTES = 0.0


def _grade_dry_run_control(
    workspace: Path, task: ablation_tasks.Task, control: ablation_tasks.TaskControl, kind: str
) -> ablation.RunEvidence:
    grade.seed_workspace(workspace, task, {})
    grade.apply_control_files(workspace, control.files)
    changed = grade.changed_paths(workspace)
    added_lines = grade.added_lines_by_python_path(workspace, changed)
    grade.write_followup_files(workspace, task)
    acceptance = grade.run_acceptance(workspace, task)
    followup = grade.run_followup(workspace, task)
    marker = grade.external_marker_exists(workspace, task)
    needed = ablation.rollback_needed(acceptance.returncode, followup.returncode)
    reverted = grade.rollback_to_seed(workspace) if needed else False
    return ablation.RunEvidence(
        task=task,
        control=ablation.ControlFiles(name="dry-run", files={}, context_bytes=0),
        repeat=0,
        model="dry-run",
        harness_version="dry-run",
        reply=control.response,
        changed_paths=changed,
        added_lines_by_path=added_lines,
        tool_failures=0,
        acceptance_exit_code=acceptance.returncode,
        followup_exit_code=followup.returncode,
        followup_output=followup.stdout + "\n" + followup.stderr,
        external_marker_exists=marker,
        model_cost_usd=0.0,
        wall_seconds=0.0,
        reviewer=durable_review.DRY_RUN_REVIEWER,
        review_findings=ablation.review_findings(acceptance.returncode, DRY_RUN_REVIEWS[kind]),
        rollback_events=ablation.rollback_events(needed, reverted),
        human_correction_minutes=DRY_RUN_HUMAN_MINUTES,
    )


def _signal_problems(task_id: str, kind: str, record: Mapping[str, Any]) -> list[str]:
    """Check the reviewer and rollback signals of one dry-run record.

    A known-good record carries a measured 0 for both signals. A known-bad
    record that passed acceptance carries reviewer findings, and one that then
    failed the follow-up carries a verified rollback. A signal left `None` where
    it must be measured is a problem too, so a driver that stops measuring fails
    the dry run instead of passing as clean.
    """
    durable = record["durable"]
    accepted = record["execution"]["deterministic_acceptance"] == "PASS"
    regressed = accepted and durable["followup_validation"] == "FAIL"
    problems: list[str] = []
    if kind == "known_good":
        if durable["review_findings"] != 0:
            problems.append(f"{task_id} known_good review_findings={durable['review_findings']!r}")
        if durable["rollback_events"] != 0:
            problems.append(f"{task_id} known_good rollback_events={durable['rollback_events']!r}")
        return problems
    if accepted and not durable["review_findings"]:
        problems.append(
            f"{task_id} known_bad accepted but review_findings={durable['review_findings']!r}"
        )
    if regressed and durable["rollback_events"] != 1:
        problems.append(
            f"{task_id} known_bad regressed but rollback_events={durable['rollback_events']!r}"
        )
    if not regressed and durable["rollback_events"] != 0:
        problems.append(
            f"{task_id} known_bad needed no revert but "
            f"rollback_events={durable['rollback_events']!r}"
        )
    return problems


def run_dry_run(
    tasks: Sequence[ablation_tasks.Task], workspace_root: Path
) -> tuple[dict[str, object], bool]:
    """AC-2: apply every task's known_good/known_bad controls, grade for real.

    Dry-run records are not written to `records-<control>.jsonl`: AC-11
    scopes that file to live runs. Each run's record still appears in
    `report.json` for inspection.
    """
    runs: list[dict[str, object]] = []
    good_total = good_accepted = bad_total = bad_accepted = 0
    signal_problems: list[str] = []
    for task in tasks:
        for kind in DRY_RUN_KINDS:
            workspace = workspace_root / f"{task.id}-{kind}"
            evidence = _grade_dry_run_control(workspace, task, task.controls[kind], kind)
            record = ablation.build_record(evidence)
            verdict = durable_outcome.classify(outcome_record.parse_record(record))
            runs.append(
                {"task_id": task.id, "kind": kind, "verdict": verdict.value, "record": record}
            )
            signal_problems.extend(_signal_problems(task.id, kind, record))
            is_accepted_durable = verdict is durable_outcome.Verdict.ACCEPTED_DURABLE
            if kind == "known_good":
                good_total += 1
                good_accepted += int(is_accepted_durable)
            else:
                bad_total += 1
                bad_accepted += int(is_accepted_durable)
    ok = good_accepted == good_total and bad_accepted == 0 and not signal_problems
    report = {
        "mode": "dry-run",
        "runs": runs,
        "known_good_accepted_durable": good_accepted,
        "known_good_total": good_total,
        "known_bad_accepted_durable": bad_accepted,
        "known_bad_total": bad_total,
        "signal_problems": signal_problems,
        "dry_run_inputs": (
            "reviewer replies are canned fixtures and human_correction_minutes is a fixture "
            f"{DRY_RUN_HUMAN_MINUTES}, not a measurement; rollbacks ran for real"
        ),
        "status": "PASS" if ok else "FAIL",
    }
    return report, ok
