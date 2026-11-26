"""Every split leg restores the newest pytest-split durations cache before pytest.

Nobody maintains a durations file; the Actions cache carries the map.
"""

from __future__ import annotations

from scripts.ci import run_pytest_partition as runner
from tests.ci.pytest_split_workflow_helpers import KEY_PREFIX, steps_using, workflow_jobs

# The one cache save the test job may hold. tests/ci/test_pytest_bytecode_cache_wiring.py
# pins its exact shape.
BYTECODE_KEY_PREFIX = "pytest-bytecode-"


def _restore() -> dict:
    (step,) = [
        step
        for step in steps_using("test", "actions/cache/restore")
        if step["with"]["key"].startswith(KEY_PREFIX)
    ]
    return step


class TestRestoreOnEverySplitLeg:
    def test_restores_to_the_path_the_runner_reads(self) -> None:
        assert _restore()["with"]["path"] == runner.DURATIONS_RESTORE_PATH

    def test_restore_keys_is_the_prefix_so_the_newest_cache_wins(self) -> None:
        assert _restore()["with"]["restore-keys"] == KEY_PREFIX
        assert _restore()["with"]["key"].startswith(KEY_PREFIX)

    def test_the_condition_selects_the_split_legs_and_no_other(self) -> None:
        assert _restore()["if"] == "startsWith(matrix.partition, 'split-')"
        matrix = workflow_jobs()["test"]["strategy"]["matrix"]["include"]
        split_legs = [leg["partition"] for leg in matrix if leg["partition"].startswith("split-")]
        assert split_legs == runner.split_names()

    def test_the_restore_runs_before_pytest(self) -> None:
        names = [s.get("name") for s in workflow_jobs()["test"]["steps"]]
        assert names.index("Restore pytest-split durations") < names.index("Run pytest")

    def test_no_split_leg_job_saves_any_cache_but_the_bytecode_cache(self) -> None:
        """The bytecode save is the one save this job may hold; any other key fails."""
        other_saves = [
            step["with"]["key"]
            for step in steps_using("test", "actions/cache/save")
            if not step["with"]["key"].startswith(BYTECODE_KEY_PREFIX)
        ]
        assert other_saves == [], f"unexpected cache saves in the test job: {other_saves}"
