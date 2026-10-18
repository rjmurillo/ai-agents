"""Tests for the reviewer arm and rollback path of the live durable driver (issue #5768).

A fake process runner stands in for `claude`. These tests prove the reviewer launch
is independent (fresh copy, read-only tools, one text for every control), that its
reply becomes a finding count or missing evidence, and that an accepted change which
fails follow-up is reverted and counted. They do not prove a real reviewer or a real
model behaves as the canned streams do.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from tests.eval._durable_live_test_support import (
    BASE,
    CLEAN_REVIEW,
    FOUND_REVIEW,
    GOOD_TASK,
    Verdict,
    classify,
    compare,
    fake_runner,
    grader_mod,
    live_mod,
    load,
    record_mod,
    review_mod,
    reviewed_case,
    reviewer_settings,
    run_case,
    stream_text,
    timed,
)


def _capturing(inner: Any) -> tuple[Any, list[dict[str, Any]]]:
    """Wrap a fake runner and keep what each launch saw at call time."""
    seen: list[dict[str, Any]] = []

    def runner(argv: list[str], **kwargs: Any) -> Any:
        cwd = Path(kwargs["cwd"])
        control = Path(argv[argv.index("--append-system-prompt-file") + 1])
        seen.append(
            {
                "argv": list(argv),
                "files": sorted(p.name for p in cwd.rglob("*") if p.is_file()),
                "control_text": control.read_text(encoding="utf-8"),
            }
        )
        return inner(argv, **kwargs)

    return runner, seen


class TestReviewerArm:
    def test_the_arm_is_off_by_default_and_the_record_is_unverified(self, tmp_path: Path) -> None:
        run, runner, _ = run_case(GOOD_TASK, ["known_good"], tmp_path)
        assert run.record is not None and len(runner.calls) == 1
        assert run.record.config.reviewer == "none"
        assert run.record.durable.review_findings is None
        assert classify(timed(run.record)) is Verdict.UNVERIFIED

    def test_a_clean_review_records_zero_findings_and_the_reviewer_identity(
        self, tmp_path: Path
    ) -> None:
        run, _, _ = reviewed_case(GOOD_TASK, ["known_good"], tmp_path, CLEAN_REVIEW)
        assert run.record is not None
        assert run.record.durable.review_findings == 0
        assert run.record.config.reviewer == "claude:haiku:low"

    def test_findings_are_counted_from_the_reviewer_reply(self, tmp_path: Path) -> None:
        run, _, _ = reviewed_case(GOOD_TASK, ["known_good"], tmp_path, FOUND_REVIEW)
        assert run.record is not None
        assert run.record.durable.review_findings == 2
        assert classify(timed(run.record)) is Verdict.ACCEPTED_DURABLE

    @pytest.mark.parametrize(
        "reply",
        [
            "Looks fine to me.",
            f"{review_mod.REVIEW_MARKER} not json",
            f'{review_mod.REVIEW_MARKER} {{"findings": "none"}}',
            f'{review_mod.REVIEW_MARKER} {{"findings": [], "extra": 1}}',
        ],
    )
    def test_a_malformed_reply_is_missing_evidence_not_zero_findings(
        self, reply: str, tmp_path: Path
    ) -> None:
        run, _, _ = reviewed_case(GOOD_TASK, ["known_good"], tmp_path, reply)
        assert run.record is not None and run.record.durable.review_findings is None
        assert classify(timed(run.record)) is Verdict.UNVERIFIED

    def test_a_failed_reviewer_process_leaves_the_record_unverified_not_dropped(
        self, tmp_path: Path
    ) -> None:
        run, _, _ = run_case(
            GOOD_TASK,
            ["known_good"],
            tmp_path,
            reviewer_settings(),
            stdout=lambda _i: stream_text(text=f"Done.\n{CLEAN_REVIEW}"),
            returncodes=[0, 2],
        )
        assert run.record is not None and run.record.durable.review_findings is None
        assert classify(timed(run.record)) is Verdict.UNVERIFIED

    def test_a_rejected_run_launches_no_reviewer(self, tmp_path: Path) -> None:
        run, runner, _ = reviewed_case(GOOD_TASK, ["known_bad"], tmp_path, CLEAN_REVIEW)
        assert run.record is not None and len(runner.calls) == 2
        assert run.record.durable.review_findings is None
        assert run.record.config.reviewer == "claude:haiku:low"
        assert classify(run.record) is Verdict.REJECTED

    def test_the_review_is_not_a_retry_and_not_rework(self, tmp_path: Path) -> None:
        run, _, _ = reviewed_case(GOOD_TASK, ["known_good"], tmp_path, CLEAN_REVIEW)
        assert run.record is not None
        assert run.record.execution.retries == 0
        assert run.record.durable.rework_minutes == 0.0

    def test_review_cost_is_part_of_the_price_of_the_result(self, tmp_path: Path) -> None:
        run, _, _ = run_case(
            GOOD_TASK,
            ["known_good"],
            tmp_path,
            reviewer_settings(),
            stdout=lambda _i: stream_text(text=f"Done.\n{CLEAN_REVIEW}", cost=0.05),
        )
        assert run.record is not None
        assert run.record.economics.model_cost_usd == pytest.approx(0.10)
        assert len(run.invocations) == 2

    def test_the_reviewer_is_independent_of_the_control_and_cannot_edit(
        self, tmp_path: Path
    ) -> None:
        scenario = load(GOOD_TASK)
        control_file = tmp_path / "control.md"
        control_file.write_text("PRODUCER-ONLY-CONTROL-TEXT", encoding="utf-8")
        inner = fake_runner(
            scenario, ["known_good"], stdout=lambda _i: stream_text(text=CLEAN_REVIEW)
        )
        runner, seen = _capturing(inner)
        live_mod.run_task(
            scenario,
            "current",
            control_file,
            BASE,
            reviewer_settings(),
            live_mod.InvocationBudget(10),
            runner=runner,
        )
        producer, reviewer = seen
        assert producer["control_text"] == "PRODUCER-ONLY-CONTROL-TEXT"
        assert reviewer["control_text"] == review_mod.REVIEWER_INSTRUCTIONS
        tail = reviewer["argv"][reviewer["argv"].index("--allowedTools") + 1 :]
        allowed = tail[: next(i for i, item in enumerate(tail) if item.startswith("--"))]
        assert allowed == ["Read", "Glob", "Grep"]
        # `--allowedTools` only pre-approves prompts. `--tools` removes the edit tools.
        assert reviewer["argv"][reviewer["argv"].index("--tools") + 1] == "Read,Glob,Grep"
        producer_tail = producer["argv"][producer["argv"].index("--allowedTools") + 1 :]
        assert "Edit" in producer_tail and "Edit" not in allowed
        assert "--tools" not in producer["argv"]
        assert reviewer["argv"][2].startswith("Review the accepted change")
        assert scenario.requirement in reviewer["argv"][2]

    def test_a_symlink_the_agent_planted_never_reaches_the_reviewer_copy(
        self, tmp_path: Path
    ) -> None:
        scenario = load(GOOD_TASK)
        workdir = tmp_path / "work"
        live_mod.materialize(scenario, workdir)
        secret = tmp_path / "host-secret.txt"
        secret.write_text("HOST-SECRET-CONTENT\n", encoding="utf-8")
        core = workdir / "slugger" / "core.py"
        core.unlink()
        core.symlink_to(secret)
        (workdir / "slugger" / "added.py").write_text("x = 1\n", encoding="utf-8")
        changed = grader_mod.changed_paths(scenario, workdir)
        assert {"slugger/core.py", "slugger/added.py"} <= set(changed)
        session = SimpleNamespace(grades=[SimpleNamespace(changed_paths=changed)], invocations=[])
        control_file = tmp_path / "control.md"
        control_file.write_text("rules", encoding="utf-8")
        copies: list[dict[str, str]] = []
        inner = fake_runner(scenario, [None], stdout=lambda _i: stream_text(text=CLEAN_REVIEW))

        def watching(argv: list[str], **kwargs: Any) -> Any:
            cwd = Path(kwargs["cwd"])
            copies.append(
                {
                    str(p.relative_to(cwd)): p.read_text(encoding="utf-8", errors="replace")
                    for p in cwd.rglob("*")
                    if p.is_file()
                }
            )
            return inner(argv, **kwargs)

        live_mod._run_review(
            scenario,
            "current",
            session,
            workdir,
            reviewer_settings(),
            live_mod.InvocationBudget(10),
            watching,
        )

        assert len(copies) == 1
        assert not any("HOST-SECRET-CONTENT" in text for text in copies[0].values())
        assert "added.py" in {Path(name).name for name in copies[0]}
        assert "def slugify" in copies[0]["slugger/core.py"]

    def test_two_controls_share_one_reviewer_config_so_the_pair_compares(
        self, tmp_path: Path
    ) -> None:
        scenario = load(GOOD_TASK)
        result = live_mod.run_experiment(
            [scenario],
            {"current": "a", "reduced": "b"},
            reviewer_settings(),
            live_mod.InvocationBudget(10),
            runner=fake_runner(
                scenario, ["known_good"], stdout=lambda _i: stream_text(text=CLEAN_REVIEW)
            ),
        )
        configs = {c: r[0].config for c, r in result.records.items()}
        assert configs["current"].reviewer == configs["reduced"].reviewer == "claude:haiku:low"
        timed_records = {c: tuple(timed(x) for x in r) for c, r in result.records.items()}
        comparison = compare(timed_records["current"], timed_records["reduced"])
        assert comparison["result"] != "UNVERIFIED"
        assert len(result.invocations) == 4

    def test_a_cross_harness_reviewer_is_refused(self) -> None:
        scenario = load(GOOD_TASK)
        spec = review_mod.ReviewerSpec("codex", "m", "low")
        settings = live_mod.RunSettings("haiku", "low", reviewer=spec)
        with pytest.raises(live_mod.LiveRunError, match="reviewer harness"):
            live_mod.run_experiment(
                [scenario], {"current": "a"}, settings, live_mod.InvocationBudget(10)
            )

    def test_the_review_launch_counts_against_the_budget(self, tmp_path: Path) -> None:
        scenario = load(GOOD_TASK)
        control_file = tmp_path / "c.md"
        control_file.write_text("x", encoding="utf-8")
        runner = fake_runner(scenario, ["known_good"], stdout=lambda _i: stream_text())
        with pytest.raises(live_mod.LiveRunError, match="cap 1"):
            live_mod.run_task(
                scenario,
                "current",
                control_file,
                BASE,
                reviewer_settings(),
                live_mod.InvocationBudget(1),
                runner=runner,
            )
        assert len(runner.calls) == 1


class TestRollbackHelpers:
    def _worked(self, tmp_path: Path, overlay: str) -> tuple[Any, Path, tuple[str, ...]]:
        scenario = load(GOOD_TASK)
        workdir = tmp_path / "work"
        live_mod.materialize(scenario, workdir, overlay)
        return scenario, workdir, grader_mod.changed_paths(scenario, workdir)

    def test_rollback_restores_initial_and_verifies_it(self, tmp_path: Path) -> None:
        scenario, workdir, changed = self._worked(tmp_path, "known_good")
        assert changed
        assert record_mod.rollback_change(scenario, workdir, changed) is True
        assert grader_mod.changed_paths(scenario, workdir) == ()

    def test_rollback_deletes_a_file_the_agent_added(self, tmp_path: Path) -> None:
        scenario, workdir, _ = self._worked(tmp_path, "known_good")
        extra = workdir / "extra" / "new.py"
        extra.parent.mkdir()
        extra.write_text("x = 1\n", encoding="utf-8")
        changed = grader_mod.changed_paths(scenario, workdir)
        assert "extra/new.py" in changed
        assert record_mod.rollback_change(scenario, workdir, changed) is True
        assert not extra.exists()

    def test_rollback_restores_a_file_the_agent_deleted(self, tmp_path: Path) -> None:
        scenario = load(GOOD_TASK)
        workdir = tmp_path / "work"
        live_mod.materialize(scenario, workdir)
        victim = workdir / "slugger" / "__init__.py"
        victim.unlink()
        assert record_mod.rollback_change(scenario, workdir, ("slugger/__init__.py",)) is True
        assert victim.is_file()

    def test_rollback_does_not_write_through_a_symlink_the_agent_planted(
        self, tmp_path: Path
    ) -> None:
        scenario = load(GOOD_TASK)
        workdir = tmp_path / "work"
        live_mod.materialize(scenario, workdir)
        outside = tmp_path / "outside.txt"
        outside.write_text("OUTSIDE-ORIGINAL\n", encoding="utf-8")
        victim = workdir / "slugger" / "__init__.py"
        victim.unlink()
        victim.symlink_to(outside)
        changed = grader_mod.changed_paths(scenario, workdir)
        assert "slugger/__init__.py" in changed
        assert record_mod.rollback_change(scenario, workdir, changed) is True
        assert not victim.is_symlink() and victim.is_file()
        assert outside.read_text(encoding="utf-8") == "OUTSIDE-ORIGINAL\n"

    def test_rollback_does_not_write_through_a_symlinked_directory(self, tmp_path: Path) -> None:
        scenario = load(GOOD_TASK)
        workdir = tmp_path / "work"
        live_mod.materialize(scenario, workdir)
        outside = tmp_path / "outside_dir"
        outside.mkdir()
        (outside / "__init__.py").write_text("OUTSIDE-ORIGINAL\n", encoding="utf-8")
        package = workdir / "slugger"
        for child in sorted(package.iterdir()):
            child.unlink()
        package.rmdir()
        package.symlink_to(outside, target_is_directory=True)
        changed = grader_mod.changed_paths(scenario, workdir)
        assert "slugger/__init__.py" in changed
        # Children first, so no earlier entry has unlinked the directory link.
        assert record_mod.rollback_change(scenario, workdir, tuple(reversed(changed))) is True
        assert not package.is_symlink() and package.is_dir()
        assert (outside / "__init__.py").read_text(encoding="utf-8") == "OUTSIDE-ORIGINAL\n"
        assert list(outside.iterdir()) == [outside / "__init__.py"]

    def test_a_revert_that_leaves_a_difference_is_not_a_recovery(self, tmp_path: Path) -> None:
        scenario, workdir, changed = self._worked(tmp_path, "known_good")
        assert len(changed) >= 1
        # The change list omits a differing path, so the tree cannot match initial/.
        assert record_mod.rollback_change(scenario, workdir, ()) is False

    def test_no_revert_is_needed_when_the_follow_up_passed(self, tmp_path: Path) -> None:
        scenario, workdir, changed = self._worked(tmp_path, "known_good")
        count = record_mod.rollback_events(
            scenario, workdir, changed, accepted=True, followup_ok=True
        )
        assert count == 0
        assert grader_mod.changed_paths(scenario, workdir) == changed

    def test_no_revert_is_needed_for_a_change_that_was_never_accepted(self, tmp_path: Path) -> None:
        scenario, workdir, changed = self._worked(tmp_path, "known_bad")
        count = record_mod.rollback_events(
            scenario, workdir, changed, accepted=False, followup_ok=False
        )
        assert count == 0
        assert grader_mod.changed_paths(scenario, workdir) == changed

    def test_an_accepted_change_that_fails_follow_up_is_reverted_once(self, tmp_path: Path) -> None:
        scenario, workdir, changed = self._worked(tmp_path, "known_good")
        count = record_mod.rollback_events(
            scenario, workdir, changed, accepted=True, followup_ok=False
        )
        assert count == 1
        assert grader_mod.changed_paths(scenario, workdir) == ()

    def test_an_unverifiable_revert_is_null_not_zero(self, tmp_path: Path) -> None:
        scenario, workdir, _ = self._worked(tmp_path, "known_good")
        count = record_mod.rollback_events(scenario, workdir, (), accepted=True, followup_ok=False)
        assert count is None

    def test_a_clean_run_records_a_measured_zero_rollback(self, tmp_path: Path) -> None:
        run, _, _ = reviewed_case(GOOD_TASK, ["known_good"], tmp_path, CLEAN_REVIEW)
        assert run.record is not None and run.record.durable.rollback_events == 0
