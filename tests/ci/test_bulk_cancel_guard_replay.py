"""Manifest replay and path-filter blocking at the CLI (issue #4835).

Split out of ``tests/ci/test_bulk_cancel_guard.py`` when that file crossed the
500-line taste ceiling. Both halves drive the same entry point; this one covers
what happens after a plan has been written, and the shared corpus writers live
in ``tests/ci/bulk_cancel_cli_fixtures.py``.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts import bulk_cancel_guard
from scripts.bulk_cancel_guard import (
    EXIT_BLOCKED,
    EXIT_CONFIG,
    EXIT_EXTERNAL,
    EXIT_OK,
    main,
)
from tests.ci.bulk_cancel_cli_fixtures import (
    HEALTHY_TYPES,
    argv,
    write_runs,
    write_workflows,
)
from tests.ci.bulk_cancel_fixtures import OPTIONAL_WORKFLOW, incident_runs
from tests.ci.test_workflow_runs import FakeClient


class TestManifestRoundTrip:
    """The manifest this tool writes must be an input this tool accepts.

    ``_execute`` tells the operator to retry after a partial cancellation. It
    used to say "re-run with the same manifest", and the manifest's JSON shape
    (top-level ``entries``, per-entry ``workflow`` / ``pull_request`` /
    ``required_contexts``) did not match what ``--runs-file`` parsed (top-level
    ``runs``, per-entry ``workflow_name`` / ``pr_number`` / ``contexts``), so an
    operator following that instruction mid-incident got exit 2.
    """

    def test_a_written_manifest_is_accepted_back_as_a_runs_file(
        self, tmp_path: Path, workflows: Path
    ):
        runs_file = write_runs(tmp_path / "runs.json", incident_runs(pr_count=2))
        manifest_path = tmp_path / "recovery.json"
        first = main(
            argv(
                runs_file,
                workflows,
                "--recovery-event",
                "reopened",
                "--manifest",
                str(manifest_path),
            ),
            client=FakeClient(),
        )
        assert first == EXIT_OK, "precondition: the first plan must validate"

        second = main(
            argv(manifest_path, workflows, "--recovery-event", "reopened"),
            client=FakeClient(),
        )

        assert second == EXIT_OK

    def test_the_replayed_manifest_names_the_same_runs_and_contexts(
        self, tmp_path: Path, workflows: Path
    ):
        """Exit 0 alone would also be produced by a manifest that parsed into
        zero runs, so pin the reconstructed inventory rather than the code.
        """
        original = incident_runs(pr_count=2)
        runs_file = write_runs(tmp_path / "runs.json", original)
        manifest_path = tmp_path / "recovery.json"
        main(
            argv(
                runs_file,
                workflows,
                "--recovery-event",
                "reopened",
                "--manifest",
                str(manifest_path),
            ),
            client=FakeClient(),
        )

        replayed = bulk_cancel_guard.load_runs_file(manifest_path)

        assert {run.run_id for run in replayed} == {run.run_id for run in original}
        assert {run.contexts for run in replayed} == {run.contexts for run in original}
        assert {run.branch for run in replayed} == {run.branch for run in original}

    def test_the_retry_instruction_names_the_manifest_as_a_runs_file(
        self, tmp_path: Path, workflows: Path, capsys
    ):
        runs = incident_runs(pr_count=1)
        runs_file = write_runs(tmp_path / "runs.json", runs)
        manifest_path = tmp_path / "recovery.json"
        client = FakeClient()
        client.post_failures[
            f"repos/rjmurillo/ai-agents/actions/runs/{runs[1].run_id}/cancel"
        ] = RuntimeError("409 Conflict")

        code = main(
            argv(
                runs_file,
                workflows,
                "--recovery-event",
                "reopened",
                "--manifest",
                str(manifest_path),
                "--confirm",
            ),
            client=client,
        )

        out = capsys.readouterr().out
        assert code == EXIT_EXTERNAL
        assert f"--runs-file {manifest_path}" in out

    def test_an_unverified_run_stays_unverified_across_the_round_trip(
        self, tmp_path: Path, workflows: Path
    ):
        """A run whose jobs never materialized is blocked, and replaying the
        manifest must not hand that trust back. Without ``jobs_verified`` in the
        manifest the reload defaults to trusted and the same run clears.
        """
        manifest_path = tmp_path / "recovery.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "entries": [
                        {
                            "run_id": 55,
                            "pull_request": 3,
                            "branch": "feat/queued",
                            "workflow": OPTIONAL_WORKFLOW,
                            "event": "synchronize",
                            "status": "queued",
                            "required_contexts": [],
                            "other_contexts": [],
                            "jobs_verified": False,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        code = main(argv(manifest_path, workflows), client=FakeClient())

        assert code == EXIT_BLOCKED

    def test_a_manifest_whose_entries_are_not_a_list_exits_config(
        self, tmp_path: Path, workflows: Path
    ):
        broken = tmp_path / "recovery.json"
        broken.write_text(json.dumps({"version": 1, "entries": "nope"}), encoding="utf-8")

        assert main(argv(broken, workflows), client=FakeClient()) == EXIT_CONFIG

    def test_a_manifest_entry_missing_a_key_exits_config(
        self, tmp_path: Path, workflows: Path, capsys
    ):
        broken = tmp_path / "recovery.json"
        broken.write_text(
            json.dumps({"version": 1, "entries": [{"run_id": 1}]}), encoding="utf-8"
        )

        code = main(argv(broken, workflows), client=FakeClient())

        assert code == EXIT_CONFIG
        assert "malformed recovery manifest entry" in capsys.readouterr().err


class TestPathFilteredWorkflowBlocksTheCli:
    """A path-filtered workflow reaches the operator as a blocked run.

    The planner-level case lives in ``test_recovery_manifest.py``; this proves
    the CLI is wired to it and that the reason reaches stdout, which is the only
    place the operator reads it.
    """

    def test_a_path_filtered_required_workflow_blocks_a_reopen_plan(
        self, tmp_path: Path, capsys
    ):
        filtered = write_workflows(
            tmp_path / "filtered", HEALTHY_TYPES, paths=["docs/**"]
        )
        runs_file = write_runs(tmp_path / "runs.json", incident_runs(pr_count=1))

        code = main(
            argv(runs_file, filtered, "--recovery-event", "reopened"),
            client=FakeClient(),
        )

        assert code == EXIT_BLOCKED
        assert "declares trigger path filters" in capsys.readouterr().out

    def test_control_the_same_workflows_without_paths_verify(
        self, tmp_path: Path, workflows: Path
    ):
        runs_file = write_runs(tmp_path / "runs.json", incident_runs(pr_count=1))

        code = main(
            argv(runs_file, workflows, "--recovery-event", "reopened"),
            client=FakeClient(),
        )

        assert code == EXIT_OK
