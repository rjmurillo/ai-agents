"""The durations cache is saved only from a push to main.

Actions scopes a cache to the ref that saved it. A pull request reads the base
branch's caches but cannot write one, so it cannot plant timings that later legs
restore. That holds only while the one save step stays gated on a push to main.
"""

from __future__ import annotations

from tests.ci.pytest_split_workflow_helpers import (
    WORKFLOW,
    durations_saves,
    steps_using,
    workflow_jobs,
)


class TestSaveOnlyFromMain:
    def test_exactly_one_step_saves_the_durations_cache(self) -> None:
        assert [job for job, _ in durations_saves()] == ["test-durations"]

    def test_the_save_is_gated_on_a_push_to_main(self) -> None:
        ((_, step),) = durations_saves()
        assert "github.event_name == 'push'" in step["if"]
        assert "github.ref == 'refs/heads/main'" in step["if"]

    def test_no_save_condition_names_a_pull_request_or_merge_group(self) -> None:
        for job in workflow_jobs():
            for step in steps_using(job, "actions/cache/save"):
                condition = str(step.get("if", ""))
                assert "pull_request" not in condition, job
                assert "merge_group" not in condition, job

    def test_a_workflow_comment_states_why_a_pull_request_cannot_write_it(self) -> None:
        comments = " ".join(
            line.strip().removeprefix("#").strip()
            for line in WORKFLOW.read_text(encoding="utf-8").splitlines()
            if line.strip().startswith("#")
        )
        assert "a pull request cannot plant timings" in comments
        assert "Never save from pull_request or merge_group" in comments
